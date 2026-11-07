"""
tools/sim.py - fast in-process match simulator that mirrors judge_engine.py.

A "bot" is any Python file with the three agent.py functions:
    new_half(config, memory), choose_action(obs, memory), on_hand_end(result, memory)
(agent.py, everything in baseline-bots/ and tools/opponents/ qualify).

No HTTP: the bots run in this process, but the match itself is played by the
real judge code (judge_engine.play_half + combine_halves), so verdicts, error
counting, forfeits and the time bank behave like the tournament:
  * each half loads every bot file fresh (new module object => module globals
    reset, memory dict wiped), like the tournament's fresh server per half;
  * observations / hand results go through to_dict()/from_dict(), like the wire;
  * on_hand_end runs for every finished hand just before the bot's next
    decision (batched like the judge), crashes there count as errors;
  * 8 s thinking per half (first 1 ms of each call free), 1 s per call,
    5 errors = forfeit = match loss, empty bank = check/fold for the rest.
  * every call is charged its compute time + 0.5 ms simulated HTTP overhead
    (--overhead-ms), minus the judge's 1 ms grace. "think" in the output is
    that judge-style charge; "raw" is the bot's pure compute time.
  Not mirrored: a slow call cannot be interrupted in-process (the judge would
  move on after 1 s while the bot keeps computing), and the tournament machine
  may be slower than yours: use --time-bank 4 to test with a safety margin.

Usage:
    python tools/sim.py A.py B.py --deals 1000 --seeds 5 --procs 8
    python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --procs 8
    python tools/sim.py --round-robin tools/opponents/*.py baseline-bots/*.py --seeds 2 --procs 8
    ... --json out.json      # save every match + the summary

Python:
    from sim import run_match      # with tools/ on sys.path
    r = run_match("agent.py", "baseline-bots/baseline_random.py", deals=1000, seed="s1")
    r["bb_per_deal"], r["ci"], r["verdict"]
"""

from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import math
import multiprocessing as mp
import os
import statistics
import sys
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import judge_engine as je  # noqa: E402
from evaluator import warmup  # noqa: E402
from game import (  # noqa: E402
    ACTION_TIMEOUT_SECONDS,
    CHOP_Z,
    ERROR_LIMIT,
    NETWORK_GRACE_SECONDS,
    STARTUP_TIMEOUT_SECONDS,
    TIME_BANK_SECONDS,
    Action,
    AgentConfig,
    HandResult,
    Observation,
    default_action,
)

# Modules shared by all bots (pure helpers); never reloaded between halves.
_SHARED_MODULES = {"game", "evaluator", "judge_engine", "sim", "__main__", "__mp_main__"}
_counter = itertools.count()
# Per-request HTTP + JSON cost a real bot pays on top of its own code (measured
# with judge_engine against local uvicorn bots: 0.18 ms for tiny observations,
# ~0.4 ms avg for full-length hands; 0.5 ms reproduced the judge's time-bank
# charge for MC bots within ~5%). Added to every timed call,
# so time-bank charging (elapsed - 1 ms grace) matches the judge.
HTTP_OVERHEAD_SECONDS = 0.0005
_BASELINE_MODULES = set(sys.modules)  # imported before any bot: never purged

VERDICT_FOR_A = {je.AGENT1_WIN: "A_WIN", je.AGENT2_WIN: "B_WIN", je.CHOP: "CHOP",
                 je.BOTH_FORFEIT: "BOTH_FORFEIT"}


# ---------------------------------------------------------------------------
# Loading bots fresh
# ---------------------------------------------------------------------------

def _is_local_module(name: str, mod: Any) -> bool:
    """True for modules that come from the repo (e.g. a bot's `bot/` package),
    excluding the shared game/evaluator/judge modules and installed packages."""
    if name in _SHARED_MODULES or name in _BASELINE_MODULES or name.startswith("_simbot_"):
        return False
    f = getattr(mod, "__file__", None)
    if not f:
        return False
    f = os.path.abspath(f)
    if not f.startswith(REPO + os.sep):
        return False
    return "site-packages" not in f and os.sep + ".venv" + os.sep not in f


def _purge_local_modules() -> None:
    """Forget repo-local helper modules so the next bot import re-executes
    them (fresh globals, and two bots never share a helper package's state)."""
    for name, mod in list(sys.modules.items()):
        if mod is not None and _is_local_module(name, mod):
            del sys.modules[name]


def load_bot(path: str):
    """Import a bot file as a brand-new module (unique name)."""
    path = os.path.abspath(path)
    _purge_local_modules()
    bot_dir = os.path.dirname(path)
    if bot_dir not in sys.path:
        sys.path.insert(1, bot_dir)
    name = f"_simbot_{os.getpid()}_{next(_counter)}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    for fn in ("new_half", "choose_action", "on_hand_end"):
        if not callable(getattr(module, fn, None)):
            raise AttributeError(f"{path} has no function {fn}()")
    return module


def _error_info(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"


def _wire_answer(action: Any) -> Any:
    """What agent.py's /act route would send back for this return value."""
    if isinstance(action, Action):
        answer: Any = action.name
    elif action is None or isinstance(action, (str, int, float, bool)):
        answer = action
    else:
        answer = repr(action)
    try:
        return json.loads(json.dumps(answer))
    except (TypeError, ValueError):
        return repr(answer)


# ---------------------------------------------------------------------------
# An in-process stand-in for judge_engine.HttpAgentHandle
# ---------------------------------------------------------------------------

@dataclass
class SimStats(je.AgentStats):
    """AgentStats plus decision timing details."""

    decisions: int = 0                 # choose_action requests actually sent
    decision_seconds: float = 0.0      # wall time of those requests (incl. on_hand_end)
    max_call_seconds: float = 0.0      # slowest single request (any kind)
    load_seconds: float = 0.0          # module import time (startup, not charged)

    def to_dict(self, include_timing: bool = True) -> dict[str, Any]:
        d = super().to_dict(include_timing)
        d["decisions"] = self.decisions
        if include_timing:
            d["decision_seconds"] = round(self.decision_seconds, 6)
            d["max_call_seconds"] = round(self.max_call_seconds, 6)
            d["load_seconds"] = round(self.load_seconds, 6)
        return d


_FAIL = object()


class InProcessAgent:
    """Duck-types HttpAgentHandle so judge_engine.play_half can drive it."""

    def __init__(self, path: str, config: AgentConfig,
                 grace: float = NETWORK_GRACE_SECONDS, overhead: float = HTTP_OVERHEAD_SECONDS) -> None:
        self.path = os.path.abspath(path)
        self.config = config
        self.grace = grace
        self.overhead = overhead
        self.stats = SimStats()
        self.module = None
        self.memory: dict = {}
        self._pending: list[dict[str, Any]] = []
        self.name = os.path.splitext(os.path.basename(path))[0]

    # --- bookkeeping copied from HttpAgentHandle ---------------------------
    def _record_error(self, message: str) -> None:
        self.stats.errors += 1
        if len(self.stats.error_messages) < je.MAX_STORED_ERRORS:
            self.stats.error_messages.append(message)
        if self.stats.errors >= ERROR_LIMIT:
            self.stats.forfeited = True

    def _remaining_bank(self) -> float:
        return self.config.time_bank_seconds - self.stats.time_seconds

    def _usable(self) -> bool:
        if self.stats.forfeited:
            return False
        if self._remaining_bank() <= 0:
            self.stats.timed_out = True
            self.stats.skipped_calls += 1
            return False
        return True

    def _request(self, label: str, fn: Callable[[], Any], results: list[dict[str, Any]],
                 is_decision: bool = False) -> Any:
        """One 'HTTP request': deliver hand results, run fn, charge the time.
        Returns fn's value, or _FAIL after recording an error / timeout."""
        bank_left = self._remaining_bank() + self.grace
        limited_by_bank = bank_left < ACTION_TIMEOUT_SECONDS
        timeout = max(0.001, min(ACTION_TIMEOUT_SECONDS, bank_left))
        hand_end_errors: list[str] = []
        crash: Optional[str] = None
        value = None
        start = time.perf_counter()
        for raw in results:
            try:
                self.module.on_hand_end(HandResult.from_dict(raw), self.memory)
            except Exception as exc:
                hand_end_errors.append(_error_info(exc))
        try:
            value = fn()
        except Exception as exc:
            crash = _error_info(exc)
        compute = time.perf_counter() - start        # the bot's own code
        elapsed = compute + self.overhead              # what the judge would measure

        st = self.stats
        charged = min(elapsed, timeout)
        st.wall_seconds += compute
        st.time_seconds += max(0.0, charged - self.grace)
        st.calls += 1
        st.max_call_seconds = max(st.max_call_seconds, compute)
        if is_decision:
            st.decisions += 1
            st.decision_seconds += compute

        if elapsed > timeout:  # the judge would have given up on this request
            if limited_by_bank:
                st.timed_out = True
            else:
                self._record_error(f"{label} took longer than {ACTION_TIMEOUT_SECONDS:g}s "
                                   f"({elapsed:.3f}s)")
            return _FAIL
        for info in hand_end_errors:
            self._record_error(f"on_hand_end raised {info}")
        if crash is not None:
            self._record_error(f"{label} raised {crash}")
            return _FAIL
        return value

    # --- what play_half calls ------------------------------------------------
    def describe(self) -> str:
        return self.name

    def start_half(self) -> None:
        self.stats = SimStats()
        self._pending = []
        self.memory = {}
        self.module = None
        t0 = time.perf_counter()
        try:
            self.module = load_bot(self.path)
        except Exception as exc:
            self.stats.load_seconds = time.perf_counter() - t0
            self._record_error(f"loading the bot failed: {_error_info(exc)}")
            self.stats.forfeited = True
            return
        self.stats.load_seconds = time.perf_counter() - t0
        if self.stats.load_seconds > STARTUP_TIMEOUT_SECONDS:
            self._record_error(f"startup took {self.stats.load_seconds:.1f}s "
                               f"(> {STARTUP_TIMEOUT_SECONDS:g}s)")
            self.stats.forfeited = True
            return
        cfg = self.config.to_dict()
        r = self._request("new_half",
                          lambda: self.module.new_half(AgentConfig.from_dict(cfg), self.memory), [])
        if r is _FAIL:
            self.stats.forfeited = True

    def act(self, obs: Observation) -> Action:
        fallback = default_action(obs.to_call)
        if not self._usable():
            return fallback
        results, self._pending = self._pending, []
        wire = obs.to_dict()
        reply = self._request(
            "choose_action",
            lambda: self.module.choose_action(Observation.from_dict(wire), self.memory),
            results, is_decision=True)
        if reply is _FAIL:
            return fallback
        answer = _wire_answer(reply)
        action = je.coerce_action(answer)
        if action is None:
            self._record_error(f"choose_action returned {answer!r}, which is not an Action")
            return fallback
        if action not in obs.legal_actions:
            legal = ", ".join(a.name for a in obs.legal_actions)
            self._record_error(f"choose_action returned illegal action {action.name} (legal: {legal})")
            return fallback
        return action

    def hand_end(self, result: HandResult) -> None:
        if not self.stats.forfeited:
            self._pending.append(result.to_dict())

    def flush_hand_results(self) -> None:
        results, self._pending = self._pending, []
        if results and self._usable():
            self._request("on_hand_end", lambda: None, results)
        self.module = None  # drop this half's module (next half loads fresh)
        _purge_local_modules()


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------

def _timing(s: SimStats) -> dict[str, Any]:
    return {
        "think_s": round(s.time_seconds, 4),
        "wall_s": round(s.wall_seconds, 4),
        "decisions": s.decisions,
        "mean_decision_ms": round(1000 * s.decision_seconds / s.decisions, 4) if s.decisions else 0.0,
        "max_call_ms": round(1000 * s.max_call_seconds, 3),
        "load_s": round(s.load_seconds, 3),
        "skipped_calls": s.skipped_calls,
    }


def run_match(bot_a: str, bot_b: str, deals: int = 1000, seed: Any = "sim",
              time_bank: float = TIME_BANK_SECONDS, grace: float = NETWORK_GRACE_SECONDS,
              overhead: float = None,
              keep_paired: bool = True, keep_logs: bool = False) -> dict[str, Any]:
    """Play one duplicate match (2 halves, same seed, seats swapped).
    A = agent1 (seat 0 in half 1). All numbers are from A's point of view."""
    warmup()
    config = AgentConfig(num_hands=deals, time_bank_seconds=time_bank)
    overhead = HTTP_OVERHEAD_SECONDS if overhead is None else overhead
    a = InProcessAgent(bot_a, config, grace, overhead)
    b = InProcessAgent(bot_b, config, grace, overhead)
    t0 = time.perf_counter()
    h1 = je.play_half(a, b, seed, 1, deals, keep_logs=keep_logs)
    h2 = je.play_half(a, b, seed, 2, deals, keep_logs=keep_logs)
    m = je.combine_halves(h1, h2)
    elapsed = time.perf_counter() - t0
    sa = m.agent_stats["agent1"]
    sb = m.agent_stats["agent2"]
    out: dict[str, Any] = {
        "bot_a": os.path.relpath(a.path, REPO) if a.path.startswith(REPO) else a.path,
        "bot_b": os.path.relpath(b.path, REPO) if b.path.startswith(REPO) else b.path,
        "name_a": a.name,
        "name_b": b.name,
        "seed": str(seed),
        "deals": deals,
        "bb_per_deal": m.mean_bb,
        "std_bb": m.std_bb,
        "stderr_bb": m.stderr_bb,
        "ci": [m.ci[0], m.ci[1]],
        "verdict": VERDICT_FOR_A[m.verdict],
        "judge_verdict": m.verdict,
        "points_a": m.points["agent1"],
        "points_b": m.points["agent2"],
        "reason": m.reason,
        "half_chips": {h: {"a": t["agent1"], "b": t["agent2"]} for h, t in m.half_totals.items()},
        "errors": {"a": [s.errors for s in sa], "b": [s.errors for s in sb]},
        "forfeited": {"a": [s.forfeited for s in sa], "b": [s.forfeited for s in sb]},
        "timed_out": {"a": [s.timed_out for s in sa], "b": [s.timed_out for s in sb]},
        "error_messages": {"a": [m_ for s in sa for m_ in s.error_messages][:3],
                           "b": [m_ for s in sb for m_ in s.error_messages][:3]},
        "timing": {"a": [_timing(s) for s in sa], "b": [_timing(s) for s in sb]},
        "elapsed_s": round(elapsed, 3),
    }
    if keep_paired:
        out["paired_bb"] = m.paired_bb
    if keep_logs:
        out["logs"] = m.logs
    return out


def _run_task(task: dict[str, Any]) -> dict[str, Any]:
    """Pool worker: never let one broken match kill the whole run."""
    try:
        return run_match(**task)
    except Exception:
        return {"bot_a": task["bot_a"], "bot_b": task["bot_b"], "seed": str(task["seed"]),
                "crash": traceback.format_exc()}


def run_many(tasks: list[dict[str, Any]], procs: int, on_result=None) -> list[dict[str, Any]]:
    """Run matches in parallel (separate processes); results in task order."""
    results: list[Optional[dict[str, Any]]] = [None] * len(tasks)
    if procs <= 1 or len(tasks) == 1:
        for i, t in enumerate(tasks):
            results[i] = _run_task(t)
            if on_result:
                on_result(results[i])
    else:
        ctx = mp.get_context("spawn")
        with ctx.Pool(min(procs, len(tasks))) as pool:
            jobs = {pool.apply_async(_run_task, (t,)): i for i, t in enumerate(tasks)}
            pending = dict(jobs)
            while pending:
                for job in list(pending):
                    if job.ready():
                        i = pending.pop(job)
                        results[i] = job.get()
                        if on_result:
                            on_result(results[i])
                time.sleep(0.02)
    return results  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def pooled(matches: list[dict[str, Any]], flip: bool = False) -> dict[str, Any]:
    """Pool paired_bb over matches: mean, CI, W/L/C, points (A's view, or B's if flip)."""
    ok = [m for m in matches if "crash" not in m]
    vals: list[float] = []
    for m in ok:
        vals.extend(-x for x in m["paired_bb"]) if flip else vals.extend(m["paired_bb"])
    n = len(vals)
    mean = sum(vals) / n if n else 0.0
    se = statistics.stdev(vals) / math.sqrt(n) if n > 1 else 0.0
    win, loss = ("B_WIN", "A_WIN") if flip else ("A_WIN", "B_WIN")
    pts_key = "points_b" if flip else "points_a"
    return {
        "deals": n, "bb_per_deal": mean, "ci": [mean - CHOP_Z * se, mean + CHOP_Z * se],
        "W": sum(m["verdict"] == win for m in ok),
        "L": sum(m["verdict"] in (loss, "BOTH_FORFEIT") for m in ok),
        "C": sum(m["verdict"] == "CHOP" for m in ok),
        "points": sum(m[pts_key] for m in ok),
        "matches": len(ok), "crashed": len(matches) - len(ok),
    }


def timing_summary(matches: list[dict[str, Any]], side: str) -> dict[str, Any]:
    halves = [h for m in matches if "crash" not in m for h in m["timing"][side]]
    dec = sum(h["decisions"] for h in halves)
    tot_ms = sum(h["mean_decision_ms"] * h["decisions"] for h in halves)
    return {
        "mean_decision_ms": tot_ms / dec if dec else 0.0,
        "max_call_ms": max((h["max_call_ms"] for h in halves), default=0.0),
        "max_half_think_s": max((h["think_s"] for h in halves), default=0.0),
        "max_half_compute_s": max((h["wall_s"] for h in halves), default=0.0),
        "errors": sum(e for m in matches if "crash" not in m for e in m["errors"][side]),
        "forfeits": sum(f for m in matches if "crash" not in m for f in m["forfeited"][side]),
        "timeouts": sum(f for m in matches if "crash" not in m for f in m["timed_out"][side]),
    }


def _flags(t: dict[str, Any]) -> str:
    out = []
    if t["max_half_think_s"] > TIME_BANK_SECONDS:
        out.append(f"OVER {TIME_BANK_SECONDS:g}s BANK")
    elif max(t["max_half_think_s"], t["max_half_compute_s"]) > 0.75 * TIME_BANK_SECONDS:
        out.append("near bank limit")
    if t["max_call_ms"] > 1000 * ACTION_TIMEOUT_SECONDS:
        out.append(f"OVER {ACTION_TIMEOUT_SECONDS:g}s/DECISION")
    elif t["max_call_ms"] > 750 * ACTION_TIMEOUT_SECONDS:
        out.append("near 1s/decision")
    if t["errors"]:
        out.append(f"{t['errors']} ERRORS")
    if t["forfeits"]:
        out.append(f"{t['forfeits']} FORFEITS")
    if t["timeouts"]:
        out.append(f"{t['timeouts']} BANK EMPTY")
    return ", ".join(out) if out else "ok"


def _timing_line(label: str, t: dict[str, Any]) -> str:
    return (f"  {label:<26} mean {t['mean_decision_ms']:7.3f} ms/dec | max call "
            f"{t['max_call_ms']:7.1f} ms | max half think {t['max_half_think_s']:5.2f} s "
            f"(raw {t['max_half_compute_s']:5.2f} s) | "
            f"{_flags(t)}")


def _match_line(m: dict[str, Any]) -> str:
    if "crash" in m:
        return f"  {m['bot_a']} vs {m['bot_b']} seed {m['seed']}: SIM CRASH\n{m['crash']}"
    errs = ""
    if any(m["errors"]["a"]) or any(m["errors"]["b"]):
        errs = f"  errors A {m['errors']['a']} B {m['errors']['b']}"
    return (f"  {m['name_a']} vs {m['name_b']}  seed {m['seed']}: {m['bb_per_deal']:+.3f} bb/deal "
            f"[{m['ci'][0]:+.3f}, {m['ci'][1]:+.3f}] {m['verdict']:<6} ({m['elapsed_s']:.1f}s){errs}")


def _short(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _fmt_ci(p: dict[str, Any]) -> str:
    return f"{p['bb_per_deal']:+7.3f}  [{p['ci'][0]:+.3f}, {p['ci'][1]:+.3f}]"


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def _seeds(base: str, n: int) -> list[str]:
    return [f"{base}-{i}" for i in range(n)]


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="In-process duplicate-match simulator (mirrors judge_engine).")
    p.add_argument("bots", nargs="*", help="two bot files A B (head-to-head mode)")
    p.add_argument("--hero", help="hero bot file (field mode)")
    p.add_argument("--field", nargs="+", help="opponent bot files (field mode)")
    p.add_argument("--round-robin", nargs="+", metavar="BOT", help="every pair of these bots")
    p.add_argument("--deals", type=int, default=1000, help="deals per match (default 1000)")
    p.add_argument("--seeds", type=int, default=1, help="independent matches per pairing")
    p.add_argument("--seed-base", default="sim", help="match seeds are <base>-0, <base>-1, ...")
    p.add_argument("--procs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--time-bank", type=float, default=TIME_BANK_SECONDS,
                   help="seconds per half (lower it to emulate a slower tournament machine)")
    p.add_argument("--overhead-ms", type=float, default=1000 * HTTP_OVERHEAD_SECONDS,
                   help="simulated HTTP/JSON cost charged per call (default %(default)s ms)")
    p.add_argument("--json", metavar="PATH", help="write all match results + summary as JSON")
    p.add_argument("--quiet", action="store_true", help="don't print each match")
    args = p.parse_args(argv)

    common = {"deals": args.deals, "time_bank": args.time_bank, "overhead": args.overhead_ms / 1000}
    seeds = _seeds(args.seed_base, args.seeds)
    show = None if args.quiet else (lambda m: print(_match_line(m), flush=True))
    t0 = time.perf_counter()
    summary: dict[str, Any]

    if args.round_robin:
        bots = list(dict.fromkeys(os.path.abspath(b) for b in args.round_robin))
        pairs = list(itertools.combinations(bots, 2))
        tasks = [{"bot_a": a, "bot_b": b, "seed": s, **common} for a, b in pairs for s in seeds]
        print(f"Round robin: {len(bots)} bots, {len(pairs)} pairings x {len(seeds)} seeds "
              f"x {args.deals} deals, {args.procs} procs", flush=True)
        matches = run_many(tasks, args.procs, show)
        rows = []
        for bot in bots:
            ms_a = [m for m in matches if m.get("bot_a") and os.path.abspath(os.path.join(REPO, m["bot_a"])) == bot]
            ms_b = [m for m in matches if m.get("bot_b") and os.path.abspath(os.path.join(REPO, m["bot_b"])) == bot]
            pa, pb = pooled(ms_a), pooled(ms_b, flip=True)
            n = pa["deals"] + pb["deals"]
            mean = (pa["bb_per_deal"] * pa["deals"] + pb["bb_per_deal"] * pb["deals"]) / n if n else 0.0
            ta, tb = timing_summary(ms_a, "a"), timing_summary(ms_b, "b")
            rows.append({"bot": _short(bot), "points": pa["points"] + pb["points"],
                         "matches": pa["matches"] + pb["matches"], "W": pa["W"] + pb["W"],
                         "L": pa["L"] + pb["L"], "C": pa["C"] + pb["C"], "bb_per_deal": mean,
                         "max_half_think_s": max(ta["max_half_think_s"], tb["max_half_think_s"]),
                         "max_call_ms": max(ta["max_call_ms"], tb["max_call_ms"]),
                         "errors": ta["errors"] + tb["errors"]})
        rows.sort(key=lambda r: (-r["points"], -r["bb_per_deal"]))
        print(f"\n{'bot':<26}{'pts':>6}{'/':>2}{'n':<4}{'W':>4}{'L':>4}{'C':>4}"
              f"{'avg bb/deal':>13}{'max half s':>12}{'max ms':>9}{'errs':>6}")
        for r in rows:
            print(f"{r['bot']:<26}{r['points']:>6.1f}{'/':>2}{r['matches']:<4}{r['W']:>4}{r['L']:>4}{r['C']:>4}"
                  f"{r['bb_per_deal']:>+13.3f}{r['max_half_think_s']:>12.2f}{r['max_call_ms']:>9.1f}"
                  f"{r['errors']:>6}")
        # head-to-head matrix (row bot's bb/deal vs column bot)
        names = [_short(b) for b in bots]
        order = [names.index(r["bot"]) for r in rows]
        print("\nHead-to-head bb/deal (row vs column):")
        w = max(8, max(len(n) for n in names) + 1)
        print(" " * w + "".join(f"{names[j][:7]:>8}" for j in order))
        for i in order:
            cells = []
            for j in order:
                if i == j:
                    cells.append(f"{'-':>8}")
                    continue
                ms = [m for m in matches if "crash" not in m and
                      {m["name_a"], m["name_b"]} == {names[i], names[j]}]
                vals = [m["bb_per_deal"] * (1 if m["name_a"] == names[i] else -1) for m in ms]
                cells.append(f"{(sum(vals) / len(vals) if vals else 0):>+8.2f}")
            print(f"{names[i]:<{w}}" + "".join(cells))
        summary = {"mode": "round_robin", "table": rows}

    elif args.hero:
        hero = os.path.abspath(args.hero)
        field = [f for f in dict.fromkeys(os.path.abspath(f) for f in (args.field or [])) if f != hero]
        if not field:
            p.error("--hero needs --field with at least one other bot")
        tasks = [{"bot_a": hero, "bot_b": opp, "seed": s, **common} for opp in field for s in seeds]
        print(f"Hero {_short(hero)} vs {len(field)} opponents x {len(seeds)} seeds x {args.deals} deals, "
              f"{args.procs} procs", flush=True)
        matches = run_many(tasks, args.procs, show)
        rows = []
        for opp in field:
            ms = [m for m in matches if os.path.abspath(os.path.join(REPO, m["bot_b"])) == opp]
            pr = pooled(ms)
            th, to = timing_summary(ms, "a"), timing_summary(ms, "b")
            rows.append({"opponent": _short(opp), **pr, "hero_timing": th, "opp_timing": to})
        rows.sort(key=lambda r: -r["bb_per_deal"])
        print(f"\n{'opponent':<28}{'bb/deal  [95% CI]':<29}{'W':>3}{'L':>3}{'C':>3}{'pts':>6}"
              f"  hero max-ms/half-s  opp")
        for r in rows:
            th = r["hero_timing"]
            print(f"{r['opponent']:<28}{_fmt_ci(r):<29}{r['W']:>3}{r['L']:>3}{r['C']:>3}"
                  f"{r['points']:>6.1f}  {th['max_call_ms']:7.1f}/{th['max_half_think_s']:5.2f}"
                  f"  {_flags(r['opp_timing'])}")
        allp = pooled(matches)
        total = sum(r["points"] for r in rows)
        nmatch = sum(r["matches"] for r in rows)
        print(f"\nOverall: {total:.1f} / {nmatch} points  (W {allp['W']} L {allp['L']} C {allp['C']}), "
              f"mean {allp['bb_per_deal']:+.3f} bb/deal over all {allp['deals']} deals")
        ht = timing_summary(matches, "a")
        print("Timing:")
        print(_timing_line(_short(hero), ht))
        summary = {"mode": "field", "hero": _short(hero), "table": rows, "points": total,
                   "matches": nmatch, "overall": allp, "hero_timing": ht}

    else:
        if len(args.bots) != 2:
            p.error("give two bot files, or --hero/--field, or --round-robin")
        a, b = (os.path.abspath(x) for x in args.bots)
        tasks = [{"bot_a": a, "bot_b": b, "seed": s, **common} for s in seeds]
        print(f"{_short(a)} (A) vs {_short(b)} (B): {len(seeds)} matches x {args.deals} deals, "
              f"{args.procs} procs", flush=True)
        matches = run_many(tasks, args.procs, show)
        pr = pooled(matches)
        ta, tb = timing_summary(matches, "a"), timing_summary(matches, "b")
        print(f"\nPooled over {pr['deals']} deals: A {_fmt_ci(pr)} bb/deal")
        print(f"Matches (A's view): W {pr['W']}  L {pr['L']}  C {pr['C']}  -> "
              f"{pr['points']:.1f} / {pr['matches']} points")
        print("Timing:")
        print(_timing_line(f"A {_short(a)}", ta))
        print(_timing_line(f"B {_short(b)}", tb))
        summary = {"mode": "pair", "pooled": pr, "timing": {"a": ta, "b": tb}}

    wall = time.perf_counter() - t0
    total_deals = sum(m.get("deals", 0) for m in matches)
    print(f"Done: {len(matches)} matches, {2 * total_deals} hands in {wall:.1f}s "
          f"({total_deals / wall:,.0f} deals/s overall)")
    crashed = [m for m in matches if "crash" in m]
    if crashed:
        print(f"WARNING: {len(crashed)} matches crashed inside the simulator (see above)")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"args": vars(args), "summary": summary, "matches": matches}, f, indent=1)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

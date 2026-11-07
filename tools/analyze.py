"""
tools/analyze.py - leak analysis: where does our bot win and lose chips?

Reads the JSON written by tools/sim.py and breaks the hero's net result down by
street reached, position, preflop percentile decile and the hero's actions,
then lists the most expensive (street, position, bucket, action) situations.

    python tools/analyze.py out.json                 # analyze a sim JSON that has per-hand logs
    python tools/analyze.py out.json --hero agent    # whose view (bot name or file); default bot A
    python tools/analyze.py out.json --generate --hero agent.py \\
        --field tools/opponents/*.py baseline-bots/*.py --deals 200 --seeds 1
                                                     # run the matches first (with logs), then analyze

Input schema
------------
Per-hand records live in matches[i]["logs"] = {"half1": [hand, ...], "half2": [...]},
exactly the records judge_engine._hand_log writes (sim.run_match(keep_logs=True)):

    {"half": 1, "deal_index": 0, "button_seat": 0,
     "hole_cards": [["As","Kd","9h","8h","6c"], [...]],      # by seat
     "board": ["Qs","Jd","7c","Th","6s"], "board_revealed": ["Qs","Jd","7c"],
     "actions": [{"seat": 0, "street": "PREFLOP", "action": "RAISE_POT",
                  "amount": 6, "street_total": 6}, ...],
     "pot": 12, "went_to_showdown": false, "nets": [6, -6]}

Bot A (matches[i]["bot_a"]) sits in seat 0 in half 1 and seat 1 in half 2.
tools/sim.py's CLI does not write logs yet (issue #22 adds `--logs`); until then
use --generate, which runs the same sim.run_match with keep_logs=True.

Columns
-------
hands      hands in the cell (each deal is played twice, once per seat)
bb/hand    hero's mean net per hand in the cell, in big blinds
bb/deal    the cell's contribution to overall bb/deal (cell total / deals);
           the rows of every table sum to the overall bb/deal, the judged number.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Iterator, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for p in (REPO, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

BIG_BLIND = 2
STREETS = ["PREFLOP", "FLOP", "TURN", "RIVER"]
STREET_BY_BOARD = {0: "PREFLOP", 3: "FLOP", 4: "TURN", 5: "RIVER"}
ACTION_SHORT = {"FOLD": "FOLD", "RAISE_HALF": "R_HALF", "RAISE_POT": "R_POT"}

_pct_fn = None


def _percentile(hole: list[str]) -> Optional[float]:
    """Preflop percentile of a hole hand via bot.equity, or None if unavailable."""
    global _pct_fn
    if _pct_fn is None:
        try:
            from evaluator import str_to_card
            from bot.equity import preflop_percentile
            _pct_fn = lambda h: preflop_percentile([str_to_card(c) for c in h])  # noqa: E731
        except Exception as exc:  # equity tables missing: still report everything else
            print(f"warning: no preflop percentiles ({exc})", file=sys.stderr)
            _pct_fn = False
    if not _pct_fn:
        return None
    try:
        return float(_pct_fn(hole))
    except Exception:
        return None


def _bucket(pct: Optional[float]) -> str:
    if pct is None:
        return "?"
    d = min(9, max(0, int(pct * 10)))
    return f"p{d * 10:02d}-{d * 10 + 10}"


def _action_label(a: dict[str, Any]) -> str:
    name = a["action"]
    if name == "CHECK_CALL":
        return "CALL" if a.get("amount", 0) else "CHECK"
    return ACTION_SHORT.get(name, name)


# ---------------------------------------------------------------------------
# Hand extraction
# ---------------------------------------------------------------------------

def _hero_side(match: dict[str, Any], hero: Optional[str]) -> Optional[str]:
    """'a' or 'b' for the hero's side in this match, or None to skip it."""
    if hero is None:
        return "a"
    h = hero.lower()
    for side in ("a", "b"):
        name = str(match.get(f"name_{side}", "")).lower()
        path = str(match.get(f"bot_{side}", "")).lower()
        if h in (name, path, os.path.basename(path), os.path.splitext(os.path.basename(path))[0]):
            return side
    return None


def iter_hands(match: dict[str, Any], side: str) -> Iterator[dict[str, Any]]:
    """Yield one summary dict per hand, from the hero's point of view."""
    logs = match.get("logs") or {}
    opp = match.get("name_b" if side == "a" else "name_a", "?")
    for half_key, hands in sorted(logs.items()):
        half = int(str(half_key)[-1])
        a_seat = 0 if half == 1 else 1
        seat = a_seat if side == "a" else 1 - a_seat
        for h in hands:
            acts = h.get("actions", [])
            n_board = len(h.get("board_revealed", []))
            reached = STREET_BY_BOARD.get(n_board, "RIVER")
            for a in acts:  # an all-in can deal the board without action on it
                if STREETS.index(a["street"]) > STREETS.index(reached):
                    reached = a["street"]
            first: dict[str, str] = {}
            for a in acts:
                if a["seat"] == seat and a["street"] not in first:
                    first[a["street"]] = _action_label(a)
            pct = _percentile(h["hole_cards"][seat])
            yield {
                "street": reached,
                "pos": "BTN" if h["button_seat"] == seat else "BB",
                "bucket": _bucket(pct),
                "first": first,
                "last_act": first.get(reached, "-"),
                "showdown": bool(h.get("went_to_showdown")),
                "bb": h["nets"][seat] / BIG_BLIND,
                "opp": opp,
            }


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

class Cell:
    __slots__ = ("n", "bb")

    def __init__(self) -> None:
        self.n = 0
        self.bb = 0.0

    def add(self, bb: float) -> None:
        self.n += 1
        self.bb += bb


def _table(title: str, cells: dict[str, Cell], deals: int, order: Optional[list[str]] = None) -> None:
    keys = order if order is not None else sorted(cells)
    keys = [k for k in keys if k in cells]
    w = max([len(title)] + [len(k) for k in keys]) + 2
    print(f"\n{title:<{w}}{'hands':>8}{'%hands':>8}{'bb/hand':>10}{'bb/deal':>10}")
    total_n = sum(c.n for c in cells.values()) or 1
    for k in keys:
        c = cells[k]
        print(f"{k:<{w}}{c.n:>8}{100 * c.n / total_n:>7.1f}%{c.bb / c.n:>+10.3f}{c.bb / deals:>+10.3f}")


def analyze(data: dict[str, Any], hero: Optional[str] = None, top: int = 10) -> int:
    matches = [m for m in data.get("matches", []) if "crash" not in m]
    by_street: dict[str, Cell] = defaultdict(Cell)
    by_pos: dict[str, Cell] = defaultdict(Cell)
    by_bucket: dict[str, Cell] = defaultdict(Cell)
    by_opp: dict[str, Cell] = defaultdict(Cell)
    by_first: dict[str, dict[str, Cell]] = {s: defaultdict(Cell) for s in STREETS}
    by_sit: dict[tuple[str, str, str, str], Cell] = defaultdict(Cell)
    deals = 0
    used = 0
    no_logs = 0
    hero_name = None
    paired_total = 0.0
    has_paired = False
    for m in matches:
        side = _hero_side(m, hero)
        if side is None:
            continue
        if not m.get("logs"):
            no_logs += 1
            continue
        used += 1
        hero_name = hero_name or m.get(f"name_{side}")
        deals += int(m.get("deals", 0))
        sign = 1 if side == "a" else -1
        has_paired = has_paired or "paired_bb" in m
        paired_total += sign * sum(m.get("paired_bb", []))
        for h in iter_hands(m, side):
            bb = h["bb"]
            by_street[h["street"] + (" (showdown)" if h["showdown"] else "")].add(bb)
            by_pos[h["pos"]].add(bb)
            by_bucket[h["bucket"]].add(bb)
            by_opp[h["opp"]].add(bb)
            for s, act in h["first"].items():
                by_first[s][act].add(bb)
            by_sit[(h["street"], h["pos"], h["bucket"], h["last_act"])].add(bb)

    if not used:
        why = (f"{no_logs} match(es) have no per-hand 'logs'. Re-run with --generate "
               "(or tools/sim.py --logs once issue #22 lands)." if no_logs
               else "no matches for that hero.")
        print(f"analyze: nothing to analyze: {why}", file=sys.stderr)
        return 1

    total = sum(c.bb for c in by_pos.values())
    n_hands = sum(c.n for c in by_pos.values())
    print(f"Hero {hero_name}: {used} matches, {deals} deals, {n_hands} hands")
    check = f"  (sim paired_bb: {paired_total / deals:+.3f})" if has_paired else ""
    print(f"Overall {total / deals:+.3f} bb/deal{check}")

    street_order = [s + sd for s in STREETS for sd in ("", " (showdown)")]
    _table("street reached", by_street, deals, street_order)
    _table("position", by_pos, deals, ["BTN", "BB"])
    _table("preflop pct", by_bucket, deals)
    if len(by_opp) > 1:
        _table("opponent", by_opp, deals,
               sorted(by_opp, key=lambda k: by_opp[k].bb))
    for s in STREETS:
        if by_first[s]:
            _table(f"{s.lower()} 1st act", by_first[s], deals,
                   sorted(by_first[s], key=lambda k: by_first[s][k].bb))

    worst = sorted(by_sit.items(), key=lambda kv: kv[1].bb)[:top]
    print(f"\n{top} most expensive situations (street reached, position, preflop pct,"
          f"\nhero's first action on that street; '-' = hero did not act there)")
    print(f"{'#':>2}  {'street':<8}{'pos':<5}{'pct':<9}{'action':<8}{'hands':>7}"
          f"{'bb/hand':>10}{'total bb':>10}{'bb/deal':>10}")
    for i, ((st, pos, bk, act), c) in enumerate(worst, 1):
        print(f"{i:>2}  {st:<8}{pos:<5}{bk:<9}{act:<8}{c.n:>7}{c.bb / c.n:>+10.3f}"
              f"{c.bb:>+10.1f}{c.bb / deals:>+10.3f}")
    return 0


# ---------------------------------------------------------------------------
# --generate: run the sim with per-hand logs (stopgap until sim.py --logs, #22)
# ---------------------------------------------------------------------------

def generate(path: str, hero: str, field: list[str], deals: int, seeds: int,
             seed_base: str, procs: int, time_bank: float) -> dict[str, Any]:
    import sim
    hero_abs = os.path.abspath(hero)
    field_abs = [f for f in dict.fromkeys(os.path.abspath(f) for f in field) if f != hero_abs]
    if not field_abs:
        raise SystemExit("--generate needs --hero and at least one --field bot")
    tasks = [{"bot_a": hero_abs, "bot_b": opp, "seed": s, "deals": deals,
              "time_bank": time_bank, "keep_logs": True}
             for opp in field_abs for s in sim._seeds(seed_base, seeds)]
    print(f"generating: {len(tasks)} matches x {deals} deals with per-hand logs ...",
          file=sys.stderr, flush=True)
    matches = sim.run_many(tasks, procs)
    for m in matches:
        if "crash" in m:
            print(f"warning: match crashed: {m['bot_b']} {m['seed']}", file=sys.stderr)
    data = {"args": {"hero": hero, "field": field, "deals": deals, "seeds": seeds,
                     "seed_base": seed_base, "time_bank": time_bank, "logs": True},
            "summary": {"mode": "field", "pooled": sim.pooled(matches)},
            "matches": matches}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"wrote {path}", file=sys.stderr)
    return data


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Break a sim.py JSON down by street, position, "
                                "preflop percentile and action.")
    p.add_argument("json", help="sim JSON to read (or to write first, with --generate)")
    p.add_argument("--hero", help="whose view: bot name or file (default: bot A of each match)")
    p.add_argument("--top", type=int, default=10, help="how many expensive situations to list")
    g = p.add_argument_group("--generate (run matches with per-hand logs, then analyze)")
    g.add_argument("--generate", action="store_true")
    g.add_argument("--field", nargs="+", default=[])
    g.add_argument("--deals", type=int, default=200)
    g.add_argument("--seeds", type=int, default=1)
    g.add_argument("--seed-base", default="sim")
    g.add_argument("--procs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    g.add_argument("--time-bank", type=float, default=4.0)
    args = p.parse_args(argv)

    if args.generate:
        if not args.hero:
            p.error("--generate needs --hero")
        data = generate(args.json, args.hero, args.field, args.deals, args.seeds,
                        args.seed_base, args.procs, args.time_bank)
        hero = os.path.splitext(os.path.basename(args.hero))[0]
    else:
        with open(args.json, encoding="utf-8") as f:
            data = json.load(f)
        hero = args.hero
    return analyze(data, hero, args.top)


if __name__ == "__main__":
    raise SystemExit(main())

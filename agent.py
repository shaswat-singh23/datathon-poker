"""
agent.py - YOUR poker bot. This one file is a complete web server.

Run it:
    python agent.py                  # listens on port 5008
    PORT=5010 python agent.py        # or pick a port

Play a match against a baseline (three windows):
    python agent.py                                 # your bot on port 5008
    python baseline-bots/baseline_random.py         # opponent on port 5009
    python judge_engine.py                          # judge: both halves (uses those two ports)

Check that the tournament can run it:
    python -m pytest -q              # tests in test_agent.py
    ./tools/check_build.sh           # builds and smoke-tests it like the tournament

TODO:
    1. Assign your agent a unique PARTICIPANT and AGENT_NAME below.
    2. Implement the three functions between "YOUR CODE HERE" and "END OF YOUR CODE".

Everything under "SERVER PLUMBING" talks to the judge. You normally never
need to change it, and if you break it the judge can't talk to your bot.
"""

import os
import traceback

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from evaluator import card_rank, card_suit, cards_to_str, omaha_score, warmup  # handy helpers, see evaluator.py
from game import Action, AgentConfig, HandResult, Observation, Street

# Build omaha_score's lookup table now, while the server starts, instead of
# during your first decision (where it would eat into your time bank).
# Do any other slow setup (loading a model, ...) here too: the server must
# answer within 15 seconds of starting.
warmup()

# rename as your team/bot's name
PARTICIPANT = "The Conductors"
AGENT_NAME = "ShortDeckShark"


# ===== YOUR CODE HERE =====
#
# agent.py stays a thin, crash-proof shell. The strategy lives in bot/policy.py
# (same three functions). Everything here exists so that no bug in the
# strategy can ever cost us an error (5 errors = forfeit = match loss):
#   * policy exceptions are caught and replaced with a safe legal action,
#   * anything not in obs.legal_actions is replaced the same way,
#   * thinking time is tracked so the policy can budget it (memory["_time_left"]),
#   * if bot.policy fails to even import, a tiny built-in fallback plays.
import time as _time

try:
    from bot import policy as _policy
    _POLICY_IMPORT_ERROR = None
except Exception as _exc:  # never let a bad import kill the server
    _policy = None
    _POLICY_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"

# The judge also counts request overhead (JSON, FastAPI) beyond the first free
# 1 ms, which our own timer can't see. Charge a fixed extra per decision.
_OVERHEAD_PER_DECISION = 0.0005
_EMERGENCY_RESERVE = 0.25  # seconds; below this, stop calling the policy


def _safe_action(obs: Observation) -> Action:
    """Legal, zero-risk action: check if free, else fold (call if fold illegal)."""
    legal = obs.legal_actions
    if obs.to_call == 0 and Action.CHECK_CALL in legal:
        return Action.CHECK_CALL
    if Action.FOLD in legal:
        return Action.FOLD
    return Action.CHECK_CALL if Action.CHECK_CALL in legal else legal[0]


def new_half(config: AgentConfig, memory: dict) -> None:
    """Called at the start of each half-match (1000 hands). memory is fresh."""
    bank = float(getattr(config, "time_bank_seconds", 8.0) or 8.0)
    memory["_bank"] = bank
    # Hands in this half (1000 in the tournament, fewer in short sim runs) so
    # bot/timing.py spreads the bank over the right count. If the value is
    # missing or bad, leave it unset: timing.py then assumes game.NUM_DEALS.
    try:
        num_hands = int(getattr(config, "num_hands", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        num_hands = 0
    if num_hands > 0:
        memory["_num_hands"] = num_hands
    memory["_spent"] = 0.0
    memory["_time_left"] = bank
    memory["_decisions"] = 0
    memory["_policy_errors"] = []
    memory["_policy_ok"] = _policy is not None
    if _policy is not None:
        try:
            _policy.new_half(config, memory)
        except Exception as exc:
            memory["_policy_ok"] = False
            memory["_policy_errors"].append(f"new_half: {type(exc).__name__}: {exc}")


def choose_action(obs: Observation, memory: dict) -> Action:
    """Called every time it is our turn. Always returns one of obs.legal_actions."""
    start = _time.perf_counter()
    if "_bank" not in memory:  # defensive: new_half somehow skipped
        new_half(AgentConfig(), memory)
    action = None
    if memory.get("_policy_ok") and memory["_time_left"] > _EMERGENCY_RESERVE:
        try:
            action = _policy.choose_action(obs, memory)
        except Exception as exc:
            errs = memory["_policy_errors"]
            if len(errs) < 50:
                errs.append(f"choose_action: {type(exc).__name__}: {exc}")
            action = None
    if not isinstance(action, Action) or action not in obs.legal_actions:
        action = _safe_action(obs)
    spent = _time.perf_counter() - start + _OVERHEAD_PER_DECISION
    memory["_spent"] += spent
    memory["_time_left"] = memory["_bank"] - memory["_spent"]
    memory["_decisions"] += 1
    return action


def on_hand_end(result: HandResult, memory: dict) -> None:
    """Called once per finished hand. Never raises."""
    if not memory.get("_policy_ok"):
        return
    start = _time.perf_counter()
    try:
        _policy.on_hand_end(result, memory)
    except Exception as exc:
        errs = memory.get("_policy_errors")
        if isinstance(errs, list) and len(errs) < 50:
            errs.append(f"on_hand_end: {type(exc).__name__}: {exc}")
    if "_spent" in memory:
        memory["_spent"] += _time.perf_counter() - start
        memory["_time_left"] = memory["_bank"] - memory["_spent"]

# ===== END OF YOUR CODE =====


# ===== SERVER PLUMBING (you normally don't need to edit below) =====
# The judge calls these routes:
#   GET  /           -> who you are (also used as the health check)
#   POST /new-half   -> start a fresh half: memory is wiped
#   POST /act        -> the judge sends any finished hands plus an Observation;
#                       on_hand_end() runs for each hand, then you answer an action
#   POST /hand-end   -> the judge sends the last finished hands of a half
#
# Why "async def"? The routes run on one thread and call your functions
# directly, so your functions never run twice at once. Your own functions
# stay normal "def" (don't make them async).
#
# Keep your per-half state in `memory`. In the tournament every half runs in
# a fresh server process, so everything starts over. When you test locally,
# though, one process can play both halves and only `memory` is wiped, NOT
# other global variables. Using `memory` makes your bot behave the same way
# in both places.

app = FastAPI()
MEMORY: dict = {}                                   # your memory for this half
STATUS = {"started": False}                         # has /new-half been called?
TOKEN = os.environ.get("AGENT_TOKEN") or None       # set by the tournament


async def _read_request(request: Request, path: str) -> tuple[dict, JSONResponse | None]:
    """Check the token (and that the half has started) BEFORE reading the body.

    Checking first means a request without the right token costs your bot
    almost nothing, so nobody else can slow it down by sending junk.
    Returns (body, None) when the request is fine, or ({}, error response).
    """
    if TOKEN and request.headers.get("x-agent-token") != TOKEN:
        return {}, JSONResponse({"error": "bad or missing X-Agent-Token"}, status_code=401)
    if not STATUS["started"] and path != "/new-half":
        return {}, JSONResponse({"error": "call /new-half first"}, status_code=409)
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return {}, JSONResponse({"error": "the request body must be a JSON object"}, status_code=400)
    return body, None


def _error_info(exc: Exception) -> dict:
    """Describe an exception from your code (call this inside `except`)."""
    return {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}


def _crash(exc: Exception, hand_end_errors: list | None = None) -> JSONResponse:
    """Report an exception from your code to the judge (with traceback)."""
    return JSONResponse({**_error_info(exc), "hand_end_errors": hand_end_errors or []},
                        status_code=500)


def _deliver_results(raw_results) -> list:
    """Call on_hand_end() for each finished hand the judge sent.
    Returns a list of error reports (one per hand that crashed)."""
    errors = []
    for raw in raw_results or []:
        try:
            on_hand_end(HandResult.from_dict(raw), MEMORY)
        except Exception as exc:
            errors.append(_error_info(exc))
    return errors


@app.get("/")
async def info():
    """Health check: tells the judge who this bot is."""
    return {"participant": PARTICIPANT, "agent_name": AGENT_NAME}


@app.post("/new-half")
async def route_new_half(request: Request):
    """Wipe memory and call your new_half(). The body is {"config": {...}}."""
    body, refused = await _read_request(request, "/new-half")
    if refused:
        return refused
    MEMORY.clear()
    STATUS["started"] = True
    try:
        new_half(AgentConfig.from_dict(body.get("config", {})), MEMORY)
    except Exception as exc:
        return _crash(exc)
    return {"ok": True}


@app.post("/act")
async def route_act(request: Request):
    """Deliver finished hands, then turn the JSON into an Observation, call
    choose_action(), and send the answer back."""
    body, refused = await _read_request(request, "/act")
    if refused:
        return refused
    hand_end_errors = _deliver_results(body.get("hand_results"))
    try:
        obs = Observation.from_dict(body["observation"])
        action = choose_action(obs, MEMORY)
    except Exception as exc:
        return _crash(exc, hand_end_errors)
    # Send the action's name; anything strange is passed on for the judge to reject.
    if isinstance(action, Action):
        answer = action.name
    elif action is None or isinstance(action, (str, int, float, bool)):
        answer = action
    else:
        answer = repr(action)
    return {"action": answer, "hand_end_errors": hand_end_errors}


@app.post("/hand-end")
async def route_hand_end(request: Request):
    """Call on_hand_end() for the last finished hands of a half."""
    body, refused = await _read_request(request, "/hand-end")
    if refused:
        return refused
    return {"ok": True, "hand_end_errors": _deliver_results(body.get("results"))}


if __name__ == "__main__":
    # The tournament sets PORT as an environment variable, so each bot is compliant to our evaluation platform
    # Locally it defaults to 5008 for your own testing convenience
    port = int(os.environ.get("PORT", "5008"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info", access_log=False)

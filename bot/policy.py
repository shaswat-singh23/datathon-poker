"""bot/policy.py - glue between agent.py's shell and the strategy modules.

Each decision:
    1. the opponent model sees the observation      (bot/opponent_model.py)
    2. preflop:  bot.preflop, given our hand's preflop percentile (bot.equity)
       postflop: bot.timing grants a Monte Carlo budget, bot.postflop decides
Each hand end: the opponent model sees the result.

agent.py catches anything raised here and replaces illegal actions, so this
file stays plain. The opponent model is optional: until bot/opponent_model.py
exists (#4), or after it raises once, play continues without it. Its expected
interface (from #4): OpponentModel() kept in memory["opp_model"], with
observe_action(obs) and observe_result(result). Using its stats to adjust
play is #12.
"""
from game import Street

from bot import equity, postflop, preflop, timing

try:
    from bot import opponent_model as _om
except Exception:  # missing (#4 not merged) or broken: play without it
    _om = None


def _disable_model(memory, where, exc):
    memory["opp_model"] = None
    memory["opp_model_error"] = f"{where}: {type(exc).__name__}: {exc}"


def _observe(memory, method, arg):
    model = memory.get("opp_model")
    if model is None:
        return
    try:
        getattr(model, method)(arg)
    except Exception as exc:
        _disable_model(memory, method, exc)


def new_half(config, memory):
    memory["hands"] = 0
    memory["opp_model"] = None
    if _om is not None:
        try:
            memory["opp_model"] = _om.OpponentModel()
        except Exception as exc:
            _disable_model(memory, "OpponentModel()", exc)


def choose_action(obs, memory):
    _observe(memory, "observe_action", obs)
    if obs.street == Street.PREFLOP:
        return preflop.preflop_action(obs, memory, equity.preflop_percentile(obs.hole_cards))
    return postflop.postflop_action(obs, memory, timing.budget_ms(memory, obs))


def on_hand_end(result, memory):
    memory["hands"] = memory.get("hands", 0) + 1
    _observe(memory, "observe_result", result)

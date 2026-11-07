"""bot/pressure.py - fold-equity betting from the opponent model (#68).

    postflop_action(obs, memory, budget_ms, rng=None) -> Action

A drop-in for bot.postflop.postflop_action. It computes equity once (through
bot.postflop.estimate_equity), lets bot.postflop.decide keep every bet, raise,
call and fold it already makes, and changes exactly one thing: when it is
checked to us (to_call == 0) and decide would check, it bets half pot if the
bet beats checking by expected value against the opponent's measured folding.

    EV(check) ~ eq * pot
    EV(bet)   = pf * pot                                  opponent folds
              + pr * (-b)                                 opponent raises, we give up
              + (1 - pf - pr) * (eq_c * (pot + 2b) - b)   opponent calls
    eq_c = eq - called_shift * pf      (the hands that call are the stronger part
                                        of the range; the more they fold, the
                                        stronger the callers)

pf and pr come from memory["opp_model"] (bot.opponent_model.OpponentModel):
fold_to_bet(street) and raise_vs_bet(street), both shrunk toward heads-up
priors, so early in a half the bet frequency barely moves from the default.
Against a calling station pf is small and nothing changes. Against a bot that
folds to a half-pot bet with 40-60% of its hands (tag, nit) we bet most hands.

PARAMS can be overridden per half through memory["pressure_params"] and, for
sweeps, through the PRESSURE environment variable ("off", or "k=v,k=v").
Never raises: any exception falls back to bot.postflop.postflop_action.
"""
from __future__ import annotations

import os
import random

from game import Action

from bot import postflop as _pf

PARAMS: dict = {
    "enabled": 1,
    "called_shift": 0.20,   # eq when called = eq - called_shift * P(fold)
    "margin": 0.03,         # bet only if EV(bet) - EV(check) > margin * pot
    "min_street": 1,        # earliest street to pressure: 1 flop, 2 turn, 3 river
    "min_fold": 0.25,       # need P(fold) at least this
    "min_samples": 0,       # fold_to_bet observations needed on that street
    "size_pot_fold": 1.01,  # bet pot instead of half when P(fold) >= this (1.01 = never)
}

_ENV: dict | None = None


def _env_params() -> dict:
    """Parse PRESSURE="off" / "k=v,k=v" once."""
    global _ENV
    if _ENV is None:
        out: dict = {}
        raw = os.environ.get("PRESSURE", "")
        if raw.strip().lower() == "off":
            out["enabled"] = 0
        else:
            for part in raw.split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    try:
                        out[k.strip()] = float(v)
                    except ValueError:
                        pass
        _ENV = out
    return _ENV


def params(memory) -> dict:
    p = dict(PARAMS)
    p.update(_env_params())
    over = memory.get("pressure_params") if isinstance(memory, dict) else None
    if isinstance(over, dict):
        p.update(over)
    return p


def _rates(memory, street: int):
    """(P(fold), P(raise), samples) from the opponent model, or None."""
    model = memory.get("opp_model") if isinstance(memory, dict) else None
    if model is None:
        return None
    pf = float(model.fold_to_bet(street))
    pr = float(model.raise_vs_bet(street))
    n = int(model.samples("fold_to_bet", street))
    if not (0.0 <= pf <= 1.0 and 0.0 <= pr <= 1.0):
        return None
    return pf, min(pr, 1.0 - pf), n


def bet_ev_gain(eq: float, pot: float, bet: float, pf: float, pr: float, p: dict) -> float:
    """EV(bet) - EV(check), in chips."""
    eq_c = max(0.0, eq - p["called_shift"] * pf)
    pc = max(0.0, 1.0 - pf - pr)
    ev_bet = pf * pot - pr * bet + pc * (eq_c * (pot + 2.0 * bet) - bet)
    return ev_bet - eq * pot


def pressure_action(eq: float, obs, memory, p: dict):
    """The half-pot (or pot) bet if the EV test passes, else None."""
    if not p.get("enabled", 1):
        return None
    if int(obs.to_call) != 0 or len(obs.board) < 3:
        return None
    street = int(obs.street)
    if street < int(p["min_street"]):
        return None
    legal = tuple(obs.legal_actions)
    if Action.RAISE_HALF not in legal and Action.RAISE_POT not in legal:
        return None
    r = _rates(memory, street)
    if r is None:
        return None
    pf, pr, n = r
    if pf < p["min_fold"] or n < int(p["min_samples"]):
        return None
    pot = float(max(1, int(obs.pot)))
    raise_to = getattr(obs, "raise_to", None) or {}
    size = Action.RAISE_POT if pf >= p["size_pot_fold"] and Action.RAISE_POT in legal else Action.RAISE_HALF
    if size not in legal:
        size = Action.RAISE_POT if Action.RAISE_POT in legal else Action.RAISE_HALF
    bet = float(raise_to.get(size, 0) or 0) - float(getattr(obs, "my_bet", 0) or 0)
    if bet <= 0:
        bet = pot / 2.0 if size == Action.RAISE_HALF else pot
    bet = min(bet, float(max(1, int(obs.my_stack))))
    if bet_ev_gain(eq, pot, bet, pf, pr, p) > p["margin"] * pot:
        return size
    return None


def postflop_action(obs, memory, budget_ms, rng=None) -> Action:
    """bot.postflop.postflop_action plus pressure bets; always legal, never raises."""
    try:
        legal = tuple(obs.legal_actions)
    except Exception:
        return Action.CHECK_CALL
    try:
        if not isinstance(memory, dict):
            memory = {}
        p = params(memory)
        pp = _pf._params(memory)
        if rng is None or isinstance(rng, bool):
            rng = random.Random(_pf._seed(obs))
        elif isinstance(rng, int):
            rng = random.Random(rng)
        elif not callable(getattr(rng, "random", None)):
            rng = random.Random(_pf._seed(obs))
        eq = _pf.estimate_equity(obs, memory, budget_ms, pp, rng)
        a = _pf.decide(eq, obs, pp, rng)
        if a == Action.CHECK_CALL and int(obs.to_call) == 0:
            try:
                b = pressure_action(eq, obs, memory, p)
            except Exception:
                b = None
            if b is not None and b in legal:
                memory["_pressure_bets"] = memory.get("_pressure_bets", 0) + 1
                return b
        return a if a in legal else _pf._pick((), legal)
    except Exception:
        return _pf.postflop_action(obs, memory, budget_ms)

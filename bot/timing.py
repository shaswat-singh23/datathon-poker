"""bot/timing.py - how many milliseconds of Monte Carlo each decision may use.

The judge gives 8 s of charged thinking time per 1000-hand half. agent.py
tracks what we have used in ``memory["_time_left"]`` (seconds; it already adds
0.5 ms per decision for request overhead). This module turns that into a
per-decision budget:

    from bot import timing                   # import runs calibrate() once (startup)
    ms = timing.budget_ms(memory, obs)       # once per decision
    n  = timing.samples_for(ms)              # optional: ms -> omaha_score calls

Guarantees:
    * A RESERVE_S slice of the bank (1.5 s) is never handed out, so at least
      1 s is still unused at hand 1000 even if the estimates are off.
    * An allowance for per-decision overhead (wrapper, JSON, non-MC policy
      code) is held back for every decision still to come, so Monte Carlo can
      never starve the cheap decisions at the end of the half.
    * Each budget is 0 (inside the reserve: play the cheap path) or lies in
      [FLOOR_MS, CEIL_MS].
    * Spending is spread evenly over the decisions expected to remain, and
      weighted towards big pots and the flop/turn.

Call budget_ms exactly once per decision that uses Monte Carlo: it records what
it granted so it can measure the true overhead from memory["_spent"].
"""
from __future__ import annotations

import random
import time

from evaluator import NUM_CARDS, omaha_score, warmup
from game import NUM_DEALS, STARTING_STACK, TIME_BANK_SECONDS, Street

# --- tunables ---------------------------------------------------------------
RESERVE_S = 1.5            # never granted; keeps charged time <= 6.5 s of 8 s
FLOOR_MS = 0.2             # smallest non-zero budget (less isn't worth sampling)
CEIL_MS = 40.0             # largest single budget (judge hard limit is 1000 ms)
MAX_SHARE = 0.03           # one decision gets at most 3% of what is spendable

WRAPPER_OVERHEAD_MS = 0.5  # agent.py charges this per decision on top of real time
POLICY_OVERHEAD_MS = 0.15  # non-MC policy work per decision at reference speed
OVERHEAD_MARGIN = 1.25     # safety factor on the overhead allowance

PRIOR_DECISIONS_PER_HAND = 2.5   # until we have observed enough hands
MIN_OVERHEAD_DPH = 3.0           # overhead allowance never assumes fewer than this
WORST_DECISIONS_PER_HAND = 8     # exhaustive search of the game tree (non-button seat)
WARMUP_HANDS = 20                # hands before observed rates replace priors

STREET_WEIGHT = {
    Street.PREFLOP: 0.25,  # mostly table lookups
    Street.FLOP: 1.0,
    Street.TURN: 1.0,
    Street.RIVER: 0.6,     # one card fewer to sample
}

REF_EVALS_PER_MS = 30.0    # omaha_score calls per ms on the dev machine

# --- machine speed (a property of the machine, so module level is fine) ----
_speed = 1.0               # >1 means slower than the dev machine
_evals_per_ms = REF_EVALS_PER_MS


def calibrate(rounds: int = 3, evals_per_round: int = 150, seed: int = 0) -> float:
    """Measure machine speed with omaha_score and scale budgets to it.

    Call once at server startup (after warmup). Takes about 15 ms at reference
    speed. Returns the slowdown factor (1.0 = dev machine, 2.0 = twice as slow).
    """
    global _speed, _evals_per_ms
    warmup()
    rng = random.Random(seed)
    deals = [rng.sample(range(NUM_CARDS), 10) for _ in range(evals_per_round)]
    best = float("inf")
    for _ in range(max(1, rounds)):
        t0 = time.perf_counter()
        for d in deals:
            omaha_score(d[:5], d[5:])
        best = min(best, time.perf_counter() - t0)
    rate = evals_per_round / max(best * 1000.0, 1e-6)
    _evals_per_ms = rate
    _speed = min(4.0, max(0.5, REF_EVALS_PER_MS / rate))
    return _speed


def set_speed(speed: float) -> None:
    """Override the calibrated slowdown factor (used by tests and simulations)."""
    global _speed, _evals_per_ms
    _speed = min(4.0, max(0.5, float(speed)))
    _evals_per_ms = REF_EVALS_PER_MS / _speed


def speed() -> float:
    return _speed


def samples_for(ms: float) -> int:
    """How many omaha_score calls fit in ms on this machine (0 if ms <= 0)."""
    if ms <= 0:
        return 0
    return max(1, int(ms * _evals_per_ms))


# Calibrate at import: agent.py imports bot.policy (and so this module) while
# the server starts, which is free time, not time bank. Never fail an import.
try:
    calibrate()
except Exception:  # pragma: no cover - keep the reference speed
    _speed, _evals_per_ms = 1.0, REF_EVALS_PER_MS


def overhead_prior_ms() -> float:
    """Expected charged overhead per decision before any measurement."""
    return WRAPPER_OVERHEAD_MS + POLICY_OVERHEAD_MS * _speed


def _weight(obs) -> float:
    street_w = STREET_WEIGHT.get(obs.street, 1.0)
    # Pot after calling, relative to one full stack: 0.6x for the blinds, 1.8x
    # once the pot holds a stack or more.
    pot_frac = min(1.0, (obs.pot + max(0, obs.to_call)) / float(STARTING_STACK))
    return street_w * (0.6 + 1.2 * pot_frac)


def budget_ms(memory: dict, obs) -> float:
    """Milliseconds of Monte Carlo this decision may use (0.0 = use the cheap path)."""
    bank = float(memory.get("_bank", TIME_BANK_SECONDS))
    time_left = float(memory.get("_time_left", bank))
    num_hands = int(memory.get("_num_hands", NUM_DEALS))
    hand = max(0, int(getattr(obs, "hand_index", 0)))
    hands_left = max(1, num_hands - hand)          # includes this hand
    decisions = int(memory.get("_decisions", 0))   # finished decisions this half

    # Decisions per hand: observed once we have enough hands; during warm-up the
    # larger of the prior and what we have seen so far (never optimistic early).
    dph = PRIOR_DECISIONS_PER_HAND
    if hand >= 3 and decisions > 0:
        seen = min(float(WORST_DECISIONS_PER_HAND), max(1.0, decisions / hand))
        dph = seen if hand >= WARMUP_HANDS else max(dph, seen)
    remaining = max(1.0, hands_left * dph)

    # Overhead per decision: never below the prior, raised if measurement says so.
    granted = float(memory.get("_tb_granted_s", 0.0))
    spent = float(memory.get("_spent", bank - time_left))
    over_ms = overhead_prior_ms()
    if decisions >= 50:
        over_ms = max(over_ms, (spent - granted) / decisions * 1000.0)
    allowance_s = hands_left * max(dph, MIN_OVERHEAD_DPH) * over_ms * OVERHEAD_MARGIN / 1000.0

    spendable_ms = (time_left - RESERVE_S - allowance_s) * 1000.0
    if spendable_ms <= FLOOR_MS:
        return 0.0

    # Spread evenly: weight / (mean weight) gets this decision's share.
    w = _weight(obs)
    wsum = float(memory.get("_tb_wsum", 0.0)) + w
    wn = int(memory.get("_tb_wn", 0)) + 1
    memory["_tb_wsum"], memory["_tb_wn"] = wsum, wn
    mean_w = wsum / wn if wn >= 30 else 1.0
    ms = spendable_ms / remaining * (w / mean_w)

    ms = min(ms, CEIL_MS, spendable_ms * MAX_SHARE)
    ms = max(ms, FLOOR_MS)
    memory["_tb_granted_s"] = granted + ms / 1000.0
    return ms

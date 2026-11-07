"""bot/timing.py - how many milliseconds of Monte Carlo each decision may use.

The judge gives 8 s of charged thinking time per 1000-hand half. agent.py
tracks what we have used in ``memory["_time_left"]`` (seconds; it already adds
0.5 ms per decision for request overhead). This module turns that into a
per-decision budget:

    from bot import timing                   # import runs calibrate() once (startup)
    ms = timing.budget_ms(memory, obs)       # once per decision that may sample
    n  = timing.samples_for(ms)              # optional: ms -> omaha_score calls

Guarantees:
    * A reserve slice of the bank (RESERVE_FRAC of it, 1.0 s of 8 s, never
      under RESERVE_MIN_S) is never handed out, so time is still unused at
      hand 1000 even if the estimates are off. agent.py's accounting is itself
      pessimistic: it charges 0.5 ms per decision that the judge only charges
      when the HTTP round trip exceeds its 1 ms grace.
    * An allowance for per-decision overhead (wrapper, JSON, non-MC policy
      code) is held back for every decision still to come, so Monte Carlo can
      never starve the cheap decisions at the end of the half. The allowance
      starts from a pessimistic prior and follows the measured overhead (up or
      down, never below the wrapper's own charge) once 50 decisions are in.
    * Each budget is 0 (inside the reserve: play the cheap path) or lies in
      [FLOOR_MS, CEIL_MS]. FLOOR_MS is above the smallest budget bot/postflop
      will sample with (min_budget_ms / budget_frac = 0.31 ms), so a non-zero
      grant is never wasted.
    * Spending is spread evenly over the decisions expected to *ask* for a
      budget (policy.py only asks postflop), weighted towards big pots and the
      flop/turn.
    * Grants are in *cost* terms: the module learns how much the equity engine
      really spends per granted ms (it overshoots small budgets, see #28) and
      scales grants down by that ratio, so a grant of x ms costs about x ms.
    * When the bank cannot cover a floor grant for every remaining ask, a share
      of the asks (by pot weight) gets the floor and the rest get 0, instead
      of everyone getting the floor and the end of the half getting nothing.

Call budget_ms exactly once per decision that uses Monte Carlo: it records what
it granted so it can measure the true overhead from memory["_spent"], and how
often it is asked so it can spread the bank over the right count.
"""
from __future__ import annotations

import random
import time

from evaluator import NUM_CARDS, omaha_score, warmup
from game import NUM_DEALS, STARTING_STACK, TIME_BANK_SECONDS, Street

# --- tunables ---------------------------------------------------------------
RESERVE_FRAC = 0.125       # of the bank, never granted: 1.0 s of 8 s, 0.5 s of 4 s
RESERVE_MIN_S = 0.5        # reserve never below this, whatever the bank
FLOOR_MS = 0.4             # smallest non-zero budget (postflop samples from 0.31 ms)
CEIL_MS = 40.0             # largest single budget (judge hard limit is 1000 ms)
MAX_SHARE = 0.03           # one decision gets at most 3% of what is spendable

WRAPPER_OVERHEAD_MS = 0.5  # agent.py charges this per decision on top of real time
POLICY_OVERHEAD_MS = 0.15  # non-MC policy work per decision at reference speed
OVERHEAD_MARGIN = 1.25     # safety factor on the overhead allowance (prior)
MEASURED_MARGIN = 1.10     # safety factor once the overhead is measured
MEASURE_AFTER = 50         # decisions before the measured overhead replaces the prior

PRIOR_DECISIONS_PER_HAND = 2.5   # until we have observed enough hands
MIN_OVERHEAD_DPH = 2.0           # overhead allowance never assumes fewer than this
WORST_DECISIONS_PER_HAND = 8     # exhaustive search of the game tree (non-button seat)
PRIOR_ASKS_PER_HAND = 1.2        # budget_ms calls per hand until observed
MIN_ASKS_PER_HAND = 0.5          # spreading never assumes fewer asks than this
WARMUP_HANDS = 20                # hands before observed rates replace priors

PRIOR_COST_RATIO = 1.5           # realized Monte Carlo ms per granted ms, until measured
RATIO_MIN, RATIO_MAX = 0.5, 8.0  # bounds on one measurement of that ratio
RATIO_ALPHA = 0.05               # EMA step for the ratio

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


def reserve_s(bank: float) -> float:
    """Seconds of the bank that are never granted."""
    return max(RESERVE_MIN_S, RESERVE_FRAC * float(bank))


def overhead_prior_ms() -> float:
    """Expected charged overhead per decision before any measurement."""
    return WRAPPER_OVERHEAD_MS + POLICY_OVERHEAD_MS * _speed


def overhead_floor_ms() -> float:
    """Measured overhead is never trusted below this (the wrapper's own charge
    plus a sliver of policy work)."""
    return WRAPPER_OVERHEAD_MS + 0.2 * POLICY_OVERHEAD_MS * _speed


def _weight(obs) -> float:
    street_w = STREET_WEIGHT.get(obs.street, 1.0)
    # Pot after calling, relative to one full stack: 0.6x for the blinds, 1.8x
    # once the pot holds a stack or more.
    pot_frac = min(1.0, (obs.pot + max(0, obs.to_call)) / float(STARTING_STACK))
    return street_w * (0.6 + 1.2 * pot_frac)


def _rate(count: float, hand: int, prior: float, floor: float, cap: float) -> float:
    """Per-hand rate of `count` events over `hand` finished hands: the prior
    until WARMUP_HANDS, never optimistic (below the prior) before that."""
    if hand < 3 or count <= 0:
        return prior
    seen = min(cap, max(floor, count / hand))
    return seen if hand >= WARMUP_HANDS else max(prior, seen)


def budget_ms(memory: dict, obs) -> float:
    """Milliseconds of Monte Carlo this decision may use (0.0 = use the cheap path)."""
    bank = float(memory.get("_bank", TIME_BANK_SECONDS))
    time_left = float(memory.get("_time_left", bank))
    num_hands = int(memory.get("_num_hands", NUM_DEALS))
    hand = max(0, int(getattr(obs, "hand_index", 0)))
    hands_left = max(1, num_hands - hand)          # includes this hand
    decisions = int(memory.get("_decisions", 0))   # finished decisions this half
    asks = int(memory.get("_tb_wn", 0))            # budget_ms calls so far this half
    granted = float(memory.get("_tb_granted_s", 0.0))
    spent = float(memory.get("_spent", bank - time_left))

    # Realized cost of Monte Carlo per granted ms (the engine overshoots small
    # budgets): the previous grant's cost is what was spent since, minus the
    # expected overhead of the decisions in between.
    ratio = float(memory.get("_tb_ratio", PRIOR_COST_RATIO))
    prev = memory.get("_tb_prev")
    if prev is not None and prev[2] > 0.0:
        n_dec = decisions - prev[1]
        if n_dec >= 1:
            mc_ms = (spent - prev[0]) * 1000.0 - n_dec * overhead_prior_ms()
            sample = min(RATIO_MAX, max(RATIO_MIN, mc_ms / prev[2]))
            ratio += RATIO_ALPHA * (sample - ratio)
            memory["_tb_ratio"] = ratio

    # Decisions per hand (all of them: they each cost overhead) and budget
    # requests per hand (the ones that share the spendable time).
    dph = _rate(decisions, hand, PRIOR_DECISIONS_PER_HAND, 1.0, WORST_DECISIONS_PER_HAND)
    aph = _rate(asks, hand, PRIOR_ASKS_PER_HAND, MIN_ASKS_PER_HAND, WORST_DECISIONS_PER_HAND)
    remaining = max(1.0, hands_left * aph)

    # Overhead per decision: the prior until measured, then what memory says
    # once the Monte Carlo cost is taken out, never below the wrapper's charge.
    over_ms, margin = overhead_prior_ms(), OVERHEAD_MARGIN
    if decisions >= MEASURE_AFTER:
        over_ms = max(overhead_floor_ms(), (spent - ratio * granted) / decisions * 1000.0)
        margin = MEASURED_MARGIN
    allowance_s = hands_left * max(dph, MIN_OVERHEAD_DPH) * over_ms * margin / 1000.0

    # Spread evenly: weight / (mean weight) gets this decision's share.
    w = _weight(obs)
    wsum = float(memory.get("_tb_wsum", 0.0)) + w
    wn = asks + 1
    memory["_tb_wsum"], memory["_tb_wn"] = wsum, wn
    mean_w = wsum / wn if wn >= 30 else 1.0

    spendable_ms = (time_left - reserve_s(bank) - allowance_s) * 1000.0
    ms = 0.0
    if spendable_ms > FLOOR_MS * ratio:
        cost = spendable_ms / remaining * (w / mean_w)      # ms this decision may cost
        ms = min(CEIL_MS, min(cost, CEIL_MS, spendable_ms * MAX_SHARE) / ratio)
        if ms < FLOOR_MS:
            # Not enough for everyone: give a floor grant to a share of the asks
            # proportional to their claim, so the bank goes to the big pots and
            # is never overspent and then starved.
            rng = memory.get("_tb_rng")
            if rng is None:
                rng = memory["_tb_rng"] = random.Random(0x35)
            ms = FLOOR_MS if rng.random() < ms / FLOOR_MS else 0.0
    memory["_tb_prev"] = (spent, decisions, ms)
    if ms > 0.0:
        memory["_tb_granted_s"] = granted + ms / 1000.0
    return ms

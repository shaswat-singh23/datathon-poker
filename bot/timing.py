"""bot/timing.py - how many milliseconds of Monte Carlo each decision may use.

The judge gives 8 s of charged thinking time per 1000-hand half. agent.py
tracks what we have used in ``memory["_time_left"]`` (seconds; it already adds
0.5 ms per decision for request overhead). This module turns that into a
per-decision budget:

    from bot import timing                   # import runs calibrate() once (startup)
    ms = timing.budget_ms(memory, obs)       # once per decision
    n  = timing.samples_for(ms)              # optional: ms -> omaha_score calls

Guarantees:
    * A reserve slice of the bank (RESERVE_FRAC of it: 1.5 s of 8 s, 0.75 s of
      4 s, never under RESERVE_MIN_S) is never handed out, so time is still
      unused at hand 1000 even if the estimates are off.
    * An allowance for per-decision overhead (wrapper, JSON, non-MC policy
      code) is held back for every decision still to come, so Monte Carlo can
      never starve the cheap decisions at the end of the half. Before warm-up
      the allowance uses pessimistic priors; after WARMUP_HANDS it uses the
      measured overhead (never below the 0.5 ms agent.py always charges) and
      the observed decisions per hand.
    * Each budget is 0 (inside the reserve: play the cheap path) or lies in
      [FLOOR_MS, CEIL_MS]. FLOOR_MS is above postflop's Monte Carlo minimum
      (PARAMS min_budget_ms / budget_frac = 0.3125 ms), so a non-zero budget
      always buys samples instead of the made-hand fallback.
    * Spending is spread evenly over the decisions expected to still ask for
      a budget (postflop ones; preflop uses the table and never calls here),
      and weighted towards big pots and the flop/turn.

Call budget_ms exactly once per decision that uses Monte Carlo: it records what
it granted so it can measure the true overhead from memory["_spent"], and how
often it is called so it knows what share of decisions want a budget.
"""
from __future__ import annotations

import random
import time

from evaluator import NUM_CARDS, omaha_score, warmup
from game import NUM_DEALS, STARTING_STACK, TIME_BANK_SECONDS, Street

# --- tunables ---------------------------------------------------------------
RESERVE_S = 1.5            # never granted at the 8 s bank: charged time <= 6.5 s
RESERVE_FRAC = RESERVE_S / TIME_BANK_SECONDS   # the reserve scales with the bank
RESERVE_MIN_S = 0.5        # but never below this (agent.py's own cutoff is 0.25 s)
FLOOR_MS = 0.4             # smallest non-zero budget; above postflop's MC minimum
CEIL_MS = 12.0             # largest single budget: ~25k flop samples, more adds
                           # no precision and only exposes the equity overrun (#28)
MAX_SHARE = 0.03           # one decision gets at most 3% of what is spendable

WRAPPER_OVERHEAD_MS = 0.5  # agent.py charges this per decision on top of real time
POLICY_OVERHEAD_MS = 0.15  # non-MC policy work per decision at reference speed
OVERHEAD_MARGIN = 1.25     # safety factor on the prior overhead allowance
MEASURED_MARGIN = 1.1      # safety factor once the overhead is measured

PRIOR_DECISIONS_PER_HAND = 2.5   # until we have observed enough hands
MIN_OVERHEAD_DPH = 3.0           # before warm-up the allowance assumes at least this
WORST_DECISIONS_PER_HAND = 8     # exhaustive search of the game tree (non-button seat)
WARMUP_HANDS = 20                # hands before observed rates replace priors
WARMUP_DECISIONS = 50            # decisions before the measured overhead is trusted
MIN_BUDGET_SHARE = 0.25          # assume at least this share of decisions ask for a budget

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


def reserve_s(bank: float) -> float:
    """Seconds of the bank that are never handed out (1.5 s at 8 s, 0.75 s at 4 s)."""
    return max(RESERVE_MIN_S, RESERVE_FRAC * float(bank))


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
    calls = int(memory.get("_tb_calls", 0)) + 1    # budget requests incl. this one
    memory["_tb_calls"] = calls
    warm = hand >= WARMUP_HANDS and decisions >= WARMUP_DECISIONS

    # Decisions per hand: observed once we have enough hands; during warm-up the
    # larger of the prior and what we have seen so far (never optimistic early).
    dph = PRIOR_DECISIONS_PER_HAND
    if hand >= 3 and decisions > 0:
        seen = min(float(WORST_DECISIONS_PER_HAND), max(1.0, decisions / hand))
        dph = seen if hand >= WARMUP_HANDS else max(dph, seen)

    # Overhead per decision for every decision still to come. Priors with a
    # fat margin until warm-up; then what agent.py actually charged beyond
    # the budgets we granted (this includes Monte Carlo overshooting its
    # budget), never below the wrapper's fixed charge.
    granted = float(memory.get("_tb_granted_s", 0.0))
    spent = float(memory.get("_spent", bank - time_left))
    if warm:
        measured_ms = (spent - granted) / decisions * 1000.0
        over_ms = max(WRAPPER_OVERHEAD_MS, measured_ms)
        allowance_s = hands_left * dph * over_ms * MEASURED_MARGIN / 1000.0
    else:
        over_ms = overhead_prior_ms()
        allowance_s = hands_left * max(dph, MIN_OVERHEAD_DPH) * over_ms * OVERHEAD_MARGIN / 1000.0

    spendable_ms = (time_left - reserve_s(bank) - allowance_s) * 1000.0
    if spendable_ms <= FLOOR_MS:
        return 0.0

    # Decisions still to come that will ask for a budget: all of them until we
    # know better, then the observed share (preflop never asks).
    share = 1.0
    if warm:
        share = min(1.0, max(MIN_BUDGET_SHARE, (calls - 1) / decisions))
    remaining = max(1.0, hands_left * dph * share)

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

"""Tests for bot/timing.py: budget bounds, calibration, and a simulated half.

The simulation charges time the way agent.py does (real time + 0.5 ms per
decision) and pessimistically: Monte Carlo overshoots its budget by 10% and the
non-MC policy code costs more than timing.py assumes.
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import timing  # noqa: E402
from game import NUM_DEALS, TIME_BANK_SECONDS, Street  # noqa: E402

LIMIT_S = 6.5
EMERGENCY_RESERVE_S = 0.25  # agent.py stops calling the policy below this


@pytest.fixture(autouse=True)
def _reset_speed():
    timing.set_speed(1.0)
    yield
    timing.set_speed(1.0)


def fresh_memory():
    bank = TIME_BANK_SECONDS
    return {"_bank": bank, "_spent": 0.0, "_time_left": bank, "_decisions": 0}


def obs(hand=0, street=Street.FLOP, pot=10, to_call=0):
    return SimpleNamespace(hand_index=hand, street=street, pot=pot, to_call=to_call)


# Pots per decision for the two shapes of hand the simulation uses.
WORST_HAND = [  # 8 decisions: the most one seat can face (exhaustive tree search)
    (Street.PREFLOP, 3, 1), (Street.PREFLOP, 9, 4),
    (Street.FLOP, 24, 0), (Street.FLOP, 48, 12),
    (Street.TURN, 72, 0), (Street.TURN, 100, 14),
    (Street.RIVER, 130, 0), (Street.RIVER, 150, 10),
]
TYPICAL_HAND = [(Street.PREFLOP, 3, 1), (Street.FLOP, 8, 0), (Street.TURN, 16, 4)]


def simulate(hand_shape, speed=1.0, mc_overshoot=1.10, policy_overhead_ms=None,
             hand_end_ms=0.02, num_hands=NUM_DEALS):
    """Play num_hands hands of hand_shape. Returns (memory, per-hand MC ms, budgets)."""
    timing.set_speed(speed)
    if policy_overhead_ms is None:
        policy_overhead_ms = 2 * timing.POLICY_OVERHEAD_MS * speed  # 2x what timing assumes
    mem = fresh_memory()
    mc_per_hand, budgets = [], []
    for h in range(num_hands):
        mc_this_hand = 0.0
        for street, pot, to_call in hand_shape:
            ms = 0.0
            if mem["_time_left"] > EMERGENCY_RESERVE_S:
                ms = timing.budget_ms(mem, obs(h, street, pot, to_call))
                budgets.append(ms)
            charged_ms = ms * mc_overshoot + policy_overhead_ms + timing.WRAPPER_OVERHEAD_MS
            mc_this_hand += ms
            mem["_spent"] += charged_ms / 1000.0
            mem["_time_left"] = mem["_bank"] - mem["_spent"]
            mem["_decisions"] += 1
        mem["_spent"] += hand_end_ms / 1000.0
        mem["_time_left"] = mem["_bank"] - mem["_spent"]
        mc_per_hand.append(mc_this_hand)
    return mem, mc_per_hand, budgets


# --- budget_ms bounds -------------------------------------------------------

def test_budget_within_floor_and_ceiling():
    mem = fresh_memory()
    for street in Street:
        for pot in (3, 20, 80, 160):
            ms = timing.budget_ms(mem, obs(0, street, pot))
            assert ms == 0.0 or timing.FLOOR_MS <= ms <= timing.CEIL_MS


def test_ceiling_holds_on_last_hand_with_full_bank():
    mem = fresh_memory()
    ms = timing.budget_ms(mem, obs(NUM_DEALS - 1, Street.TURN, 160, 40))
    assert ms == timing.CEIL_MS


def test_zero_inside_reserve():
    mem = fresh_memory()
    mem["_time_left"] = timing.RESERVE_S
    mem["_spent"] = mem["_bank"] - mem["_time_left"]
    assert timing.budget_ms(mem, obs(990, Street.FLOP, 80)) == 0.0


def test_bigger_pot_gets_more_time():
    small = timing.budget_ms(fresh_memory(), obs(100, Street.FLOP, 6))
    big = timing.budget_ms(fresh_memory(), obs(100, Street.FLOP, 120, 30))
    assert big > small * 2


def test_preflop_gets_less_than_flop():
    pre = timing.budget_ms(fresh_memory(), obs(100, Street.PREFLOP, 20))
    flop = timing.budget_ms(fresh_memory(), obs(100, Street.FLOP, 20))
    assert pre < flop


def test_missing_memory_keys_do_not_crash():
    assert timing.budget_ms({}, obs(0)) >= 0.0


# --- calibrate --------------------------------------------------------------

def test_calibrate_measures_speed_quickly():
    import time
    t0 = time.perf_counter()
    s = timing.calibrate()
    assert time.perf_counter() - t0 < 0.5
    assert 0.5 <= s <= 4.0
    assert timing.speed() == s
    assert timing.samples_for(10.0) >= 1
    assert timing.samples_for(0.0) == 0


def test_slower_cpu_holds_back_more_overhead():
    mem_args = dict(hand=100, street=Street.FLOP, pot=20)
    timing.set_speed(1.0)
    fast = timing.budget_ms(fresh_memory(), obs(**mem_args))
    timing.set_speed(3.0)
    slow = timing.budget_ms(fresh_memory(), obs(**mem_args))
    assert slow < fast
    assert timing.samples_for(10.0) < 10.0 * timing.REF_EVALS_PER_MS


# --- simulated half ---------------------------------------------------------

@pytest.mark.parametrize("speed,overhead_mult", [(1.0, 1.0), (1.0, 2.0), (1.5, 1.0), (2.0, 1.0)])
def test_worst_case_half_stays_under_limit(speed, overhead_mult):
    po = overhead_mult * timing.POLICY_OVERHEAD_MS * speed
    mem, _, budgets = simulate(WORST_HAND, speed=speed, policy_overhead_ms=po)
    assert mem["_decisions"] == NUM_DEALS * len(WORST_HAND)
    assert mem["_spent"] <= LIMIT_S, f"charged {mem['_spent']:.3f}s at speed {speed}"
    assert mem["_time_left"] >= 1.0
    assert max(budgets) <= timing.CEIL_MS


def test_backs_off_when_fixed_cost_alone_exceeds_limit():
    # 8 decisions every hand on a 2x slower CPU with 2x the expected non-MC
    # cost: the per-decision overhead alone is ~8.8 s, more than the bank.
    # No budget can fix that; timing.py must at least add (almost) nothing.
    po = 2 * timing.POLICY_OVERHEAD_MS * 2.0
    mem, mc, _ = simulate(WORST_HAND, speed=2.0, policy_overhead_ms=po)
    assert sum(mc) * 1.10 / 1000.0 < 0.1


@pytest.mark.parametrize("speed", [1.0, 2.0])
def test_typical_half_stays_under_limit_and_uses_the_bank(speed):
    mem, _, _ = simulate(TYPICAL_HAND, speed=speed)
    assert mem["_spent"] <= LIMIT_S
    assert mem["_spent"] >= 5.0, f"only used {mem['_spent']:.3f}s; budgets too timid"


def test_typical_half_spends_evenly():
    _, mc, _ = simulate(TYPICAL_HAND)
    first, last = sum(mc[:200]), sum(mc[-200:])
    assert 0.5 <= last / first <= 2.0, (first, last)


def test_underestimated_overhead_is_corrected_by_measurement():
    # Real non-MC cost is 6x the prior; the measured-overhead path must catch it.
    mem, _, _ = simulate(TYPICAL_HAND, policy_overhead_ms=6 * timing.POLICY_OVERHEAD_MS)
    assert mem["_spent"] <= LIMIT_S

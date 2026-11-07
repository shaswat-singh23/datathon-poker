"""Tests for bot/timing.py: budget bounds, calibration, and a simulated half.

The simulation charges time the way agent.py does (real time + 0.5 ms per
decision) and pessimistically: Monte Carlo overshoots its budget by 10% and the
non-MC policy code costs more than timing.py assumes. As in bot/policy.py, only
postflop decisions ask for a budget; preflop decisions still cost overhead.
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import timing  # noqa: E402
from game import NUM_DEALS, TIME_BANK_SECONDS, Street  # noqa: E402

EMERGENCY_RESERVE_S = 0.25  # agent.py stops calling the policy below this
MC_MIN_MS = 0.25 / 0.8      # bot/postflop samples only from min_budget_ms / budget_frac


def limit_s(bank=TIME_BANK_SECONDS):
    """Self-accounted spending may not eat more than a tenth of the reserve."""
    return bank - 0.9 * timing.reserve_s(bank)


@pytest.fixture(autouse=True)
def _reset_speed():
    timing.set_speed(1.0)
    yield
    timing.set_speed(1.0)


def fresh_memory(bank=TIME_BANK_SECONDS):
    return {"_bank": bank, "_spent": 0.0, "_time_left": bank, "_decisions": 0}


def obs(hand=0, street=Street.FLOP, pot=10, to_call=0):
    return SimpleNamespace(hand_index=hand, street=street, pot=pot, to_call=to_call)


# Pots per decision for the shapes of hand the simulation uses.
WORST_HAND = [  # 8 decisions: the most one seat can face (exhaustive tree search)
    (Street.PREFLOP, 3, 1), (Street.PREFLOP, 9, 4),
    (Street.FLOP, 24, 0), (Street.FLOP, 48, 12),
    (Street.TURN, 72, 0), (Street.TURN, 100, 14),
    (Street.RIVER, 130, 0), (Street.RIVER, 150, 10),
]
TYPICAL_HAND = [(Street.PREFLOP, 3, 1), (Street.FLOP, 8, 0), (Street.TURN, 16, 4)]
# 3.7 decisions/hand, 2.7 postflop: what a calling station produced in the #35
# probe. A list of shapes is cycled hand by hand.
BUSY_HANDS = 7 * [[(Street.PREFLOP, 3, 1), (Street.FLOP, 8, 0), (Street.TURN, 16, 4), (Street.RIVER, 24, 0)]] \
    + 3 * [[(Street.PREFLOP, 3, 1), (Street.FLOP, 8, 0), (Street.TURN, 16, 4)]]


def simulate(hand_shape, speed=1.0, mc_overshoot=1.10, policy_overhead_ms=None,
             hand_end_ms=0.02, num_hands=NUM_DEALS, bank=TIME_BANK_SECONDS):
    """Play num_hands hands of hand_shape (one shape, or a list of shapes that
    is cycled). Returns (memory, per-hand MC ms, budgets)."""
    shapes = hand_shape if isinstance(hand_shape[0], list) else [hand_shape]
    timing.set_speed(speed)
    if policy_overhead_ms is None:
        policy_overhead_ms = 2 * timing.POLICY_OVERHEAD_MS * speed  # 2x what timing assumes
    mem = fresh_memory(bank)
    mc_per_hand, budgets = [], []
    for h in range(num_hands):
        mc_this_hand = 0.0
        for street, pot, to_call in shapes[h % len(shapes)]:
            ms = 0.0
            if street != Street.PREFLOP and mem["_time_left"] > EMERGENCY_RESERVE_S:
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
    # Grants are in cost terms: the ceiling applies to CEIL_MS of realized cost.
    mem = fresh_memory()
    ms = timing.budget_ms(mem, obs(NUM_DEALS - 1, Street.TURN, 160, 40))
    assert ms == pytest.approx(timing.CEIL_MS / timing.PRIOR_COST_RATIO)
    mem = fresh_memory()
    mem["_tb_ratio"] = timing.RATIO_MIN  # a cheap engine never gets more than CEIL_MS
    assert timing.budget_ms(mem, obs(NUM_DEALS - 1, Street.TURN, 160, 40)) == timing.CEIL_MS


@pytest.mark.parametrize("bank", [TIME_BANK_SECONDS, 4.0, 2.0])
def test_zero_inside_reserve(bank):
    mem = fresh_memory(bank)
    mem["_time_left"] = timing.reserve_s(bank)
    mem["_spent"] = mem["_bank"] - mem["_time_left"]
    assert timing.budget_ms(mem, obs(990, Street.FLOP, 80)) == 0.0


def test_reserve_scales_with_bank_but_has_a_floor():
    assert timing.reserve_s(TIME_BANK_SECONDS) == pytest.approx(1.0)
    assert timing.reserve_s(4.0) == pytest.approx(0.5)
    assert timing.reserve_s(1.0) == pytest.approx(timing.RESERVE_MIN_S)


def test_floor_is_enough_for_postflop_to_sample():
    assert timing.FLOOR_MS >= MC_MIN_MS


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


# --- simulated half, 8 s bank -----------------------------------------------

@pytest.mark.parametrize("speed,overhead_mult", [(1.0, 1.0), (1.0, 2.0), (1.5, 1.0), (2.0, 1.0)])
def test_worst_case_half_stays_under_limit(speed, overhead_mult):
    po = overhead_mult * timing.POLICY_OVERHEAD_MS * speed
    mem, _, budgets = simulate(WORST_HAND, speed=speed, policy_overhead_ms=po)
    assert mem["_decisions"] == NUM_DEALS * len(WORST_HAND)
    assert mem["_spent"] <= limit_s(), f"charged {mem['_spent']:.3f}s at speed {speed}"
    assert mem["_time_left"] >= 0.9 * timing.reserve_s(TIME_BANK_SECONDS)
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
    assert mem["_spent"] <= limit_s()
    assert mem["_spent"] >= 5.5, f"only used {mem['_spent']:.3f}s; budgets too timid"


def test_typical_half_spends_evenly():
    _, mc, _ = simulate(TYPICAL_HAND)
    first, last = sum(mc[:200]), sum(mc[-200:])
    assert 0.5 <= last / first <= 2.0, (first, last)


def test_underestimated_overhead_is_corrected_by_measurement():
    # Real non-MC cost is 6x the prior; the measured-overhead path must catch it.
    mem, _, _ = simulate(TYPICAL_HAND, policy_overhead_ms=6 * timing.POLICY_OVERHEAD_MS)
    assert mem["_spent"] <= limit_s()


# --- simulated half, 4 s test bank (#35) ------------------------------------

# The non-MC policy cost measured in the sim (#35 probe) is the prior, 0.15 ms;
# these tests use it rather than the 2x pessimism of the 8 s tests, because at
# 4 s the fixed cost of 3 decisions/hand already eats half the bank.
MEASURED_POLICY_MS = timing.POLICY_OVERHEAD_MS


def test_4s_bank_grants_monte_carlo_to_most_postflop_decisions():
    mem, _, budgets = simulate(TYPICAL_HAND, bank=4.0, policy_overhead_ms=MEASURED_POLICY_MS)
    assert mem["_spent"] <= limit_s(4.0), f"charged {mem['_spent']:.3f}s of a 4 s bank"
    usable = sum(1 for b in budgets if b >= MC_MIN_MS)
    assert usable / len(budgets) >= 0.9, f"only {usable / len(budgets):.1%} of postflop asks could sample"
    assert mem["_spent"] >= 3.0, f"only used {mem['_spent']:.3f}s of 4 s; budgets too timid"


def test_4s_bank_grants_from_the_first_hands():
    # The prior margin and cost ratio pinch a little before measurement kicks
    # in (50 decisions), but most early postflop decisions still sample.
    _, _, budgets = simulate(TYPICAL_HAND, bank=4.0, num_hands=30, policy_overhead_ms=MEASURED_POLICY_MS)
    usable = sum(1 for b in budgets if b >= MC_MIN_MS)
    assert usable / len(budgets) >= 0.75, f"{usable}/{len(budgets)}"


def test_4s_bank_busy_opponent_shares_the_floor_without_starving_the_end():
    # 2.7 postflop asks per hand: a floor grant for every ask does not fit, so
    # some asks get 0 all along the half instead of all of them late.
    mem, mc, budgets = simulate(BUSY_HANDS, bank=4.0, policy_overhead_ms=MEASURED_POLICY_MS)
    assert mem["_spent"] <= limit_s(4.0), f"charged {mem['_spent']:.3f}s of a 4 s bank"
    usable = sum(1 for b in budgets if b >= MC_MIN_MS)
    assert usable / len(budgets) >= 0.5
    assert all(b == 0.0 or b >= MC_MIN_MS for b in budgets)
    first, last = sum(mc[:200]), sum(mc[-200:])
    assert last >= 0.5 * first, (first, last)


@pytest.mark.parametrize("speed", [1.0, 2.0])
def test_4s_bank_worst_case_half_adds_almost_nothing(speed):
    # 8 decisions a hand cost more in overhead than the 4 s bank holds.
    _, mc, _ = simulate(WORST_HAND, speed=speed, bank=4.0)
    assert sum(mc) * 1.10 / 1000.0 < 0.1


def test_learns_the_engines_cost_ratio_and_stays_under_limit():
    # The equity engine spends 2.5x what it is granted (#28): the grants must
    # shrink to match and the half must still end inside the limit.
    mem, _, budgets = simulate(TYPICAL_HAND, bank=4.0, mc_overshoot=2.5, policy_overhead_ms=MEASURED_POLICY_MS)
    assert mem["_spent"] <= limit_s(4.0), f"charged {mem['_spent']:.3f}s of a 4 s bank"
    assert 2.0 <= mem["_tb_ratio"] <= 3.0, mem["_tb_ratio"]
    usable = sum(1 for b in budgets if b >= MC_MIN_MS)
    assert usable / len(budgets) >= 0.5


def test_measured_overhead_can_lower_the_allowance():
    # A cheap policy (overhead at the wrapper's floor) gets bigger budgets than
    # a dear one once measurement kicks in, and both stay under the limit.
    cheap, _, b_cheap = simulate(TYPICAL_HAND, policy_overhead_ms=0.0, bank=4.0)
    dear, _, b_dear = simulate(TYPICAL_HAND, policy_overhead_ms=3 * timing.POLICY_OVERHEAD_MS, bank=4.0)
    assert sum(b_cheap) > sum(b_dear) * 1.2
    assert cheap["_spent"] <= limit_s(4.0) and dear["_spent"] <= limit_s(4.0)
    assert timing.overhead_floor_ms() > timing.WRAPPER_OVERHEAD_MS

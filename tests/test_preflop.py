"""Tests for bot/preflop.py.  Run: python -m pytest -q tests/test_preflop.py"""

import itertools
import os
import random
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import equity as E  # noqa: E402
from bot import preflop as P  # noqa: E402
from game import Action, Game, Observation, Street, make_deal  # noqa: E402

pytestmark = pytest.mark.skipif(not E.tables_loaded(), reason="run tools/build_tables.py first")

ALL = (Action.FOLD, Action.CHECK_CALL, Action.RAISE_HALF, Action.RAISE_POT)


def _obs(**kw) -> Observation:
    """A preflop Observation with sensible defaults (button first in)."""
    base = dict(hand_index=0, street=Street.PREFLOP, hole_cards=(0, 5, 10, 15, 20), board=(),
                pot=3, to_call=1, my_bet=1, opp_bet=2, my_stack=79, opp_stack=78,
                is_button=True, legal_actions=ALL, raise_to={}, min_raise_to=4,
                raises_this_street=0, action_history=(), big_blind=2)
    base.update(kw)
    return Observation(**base)


def _game_obs(seed: int, rng: random.Random, steps: int) -> Observation | None:
    """Play `steps` random legal non-fold actions; return the preflop observation that follows."""
    g = Game(make_deal(f"pf-{seed}", seed), button_seat=seed % 2, hand_index=seed)
    for _ in range(steps):
        if g.is_terminal or g.street != Street.PREFLOP:
            return None
        g.apply(rng.choice([a for a in g.legal_actions() if a != Action.FOLD]))
    if g.is_terminal or g.street != Street.PREFLOP:
        return None
    return g.observation(g.to_act)


# ---------------------------------------------------------------------------
# Legality (property tests)
# ---------------------------------------------------------------------------

def test_every_legal_actions_subset_gets_a_legal_answer():
    rng = random.Random(0)
    subsets = [s for k in range(1, 5) for s in itertools.combinations(ALL, k)]
    for i in range(3000):
        legal = rng.choice(subsets)
        hole = tuple(rng.sample(range(36), 5))
        my_stack = rng.randint(0, 79)
        opp_stack = rng.randint(0, 79)
        obs = _obs(hand_index=i, hole_cards=hole, legal_actions=legal,
                   to_call=rng.choice([0, 0, 1, 2, 4, 12, 40, 78]),
                   pot=rng.randint(3, 160), my_stack=my_stack, opp_stack=opp_stack,
                   raises_this_street=rng.randint(0, 4), is_button=rng.random() < 0.5)
        pct = rng.random()
        mem = {"_time_left": rng.choice([0.1, 5.0])}
        assert P.preflop_action(obs, mem, pct) in legal


def test_random_reachable_preflop_states_are_legal():
    rng = random.Random(1)
    checked = 0
    for seed in range(2500):
        obs = _game_obs(seed, rng, rng.randint(0, 5))
        if obs is None:
            continue
        pct = E.preflop_percentile(obs.hole_cards)
        for mem in ({}, {"_time_left": 0.05}):
            assert P.preflop_action(obs, mem, pct) in obs.legal_actions
        # and with a random pct, which reaches every branch whatever the cards are
        assert P.preflop_action(obs, {}, rng.random()) in obs.legal_actions
        checked += 1
    assert checked > 1000


def test_full_preflop_playouts_never_go_illegal():
    """Both seats play our preflop policy against each other until the flop or a fold."""
    for seed in range(400):
        g = Game(make_deal(f"self-{seed}", seed), button_seat=seed % 2, hand_index=seed)
        while not g.is_terminal and g.street == Street.PREFLOP:
            obs = g.observation(g.to_act)
            a = P.preflop_action(obs, {}, E.preflop_percentile(obs.hole_cards))
            assert a in obs.legal_actions
            g.apply(a)


# ---------------------------------------------------------------------------
# Behaviour in each situation
# ---------------------------------------------------------------------------

def test_first_in_open_limp_fold():
    t = P.THRESHOLDS
    assert P.preflop_action(_obs(), {}, 0.99) == Action.RAISE_POT
    assert P.preflop_action(_obs(), {}, (t["open_limp"] + t["open_raise"]) / 2) == Action.CHECK_CALL
    assert P.preflop_action(_obs(), {}, 0.01) == Action.FOLD


def test_big_blind_option_never_folds():
    obs = _obs(is_button=False, to_call=0, my_bet=2, opp_bet=2, pot=4, my_stack=78,
               legal_actions=(Action.CHECK_CALL, Action.RAISE_HALF, Action.RAISE_POT))
    assert P.preflop_action(obs, {}, 0.99) == Action.RAISE_POT
    for pct in (0.0, 0.3, 0.6):
        assert P.preflop_action(obs, {}, pct) == Action.CHECK_CALL


def test_facing_open_three_bet_call_fold():
    # SB pot-opened to 6, BB to act: pot 8, to_call 4 (price 1/3, not cheap)
    obs = _obs(is_button=False, to_call=4, my_bet=2, opp_bet=6, pot=8, my_stack=78, opp_stack=74,
               raises_this_street=1)
    t = P.THRESHOLDS
    assert P.preflop_action(obs, {}, 0.99) == Action.RAISE_POT
    assert P.preflop_action(obs, {}, t["call_1"] + 0.01) == Action.CHECK_CALL
    assert P.preflop_action(obs, {}, t["call_1"] - 0.01) == Action.FOLD


def test_cheap_price_widens_calls():
    # SB half-pot opened to 4: pot 6, to_call 2, price 0.25 <= cheap_price
    obs = _obs(is_button=False, to_call=2, my_bet=2, opp_bet=4, pot=6, my_stack=78, opp_stack=76,
               raises_this_street=1)
    t = P.THRESHOLDS
    pct = t["call_1"] - t["cheap_bonus"] + 0.01
    assert P.preflop_action(obs, {}, pct) == Action.CHECK_CALL


def test_thresholds_rise_with_raise_level():
    t = P.THRESHOLDS
    assert t["call_1"] < t["call_2"] < t["call_3"]
    assert t["raise_1"] < t["raise_2"] < t["raise_3"]
    assert t["open_limp"] < t["open_raise"]
    for n in (1, 2, 3):
        assert t[f"call_{n}"] < t[f"raise_{n}"]


def test_facing_three_bet_continues_tighter():
    # we opened to 6, BB 3-bet pot to 18: pot 24, to_call 12, stack 74
    obs = _obs(to_call=12, my_bet=6, opp_bet=18, pot=24, my_stack=74, opp_stack=62,
               raises_this_street=2)
    t = P.THRESHOLDS
    assert P.preflop_action(obs, {}, t["call_1"] + 0.01) == Action.FOLD
    assert P.preflop_action(obs, {}, t["call_2"] + 0.01) == Action.CHECK_CALL
    assert P.preflop_action(obs, {}, 0.995) == Action.RAISE_POT


def test_capped_pot_only_calls_or_folds():
    obs = _obs(to_call=10, my_bet=20, opp_bet=30, pot=50, my_stack=60, opp_stack=50,
               raises_this_street=4, legal_actions=(Action.FOLD, Action.CHECK_CALL))
    assert P.preflop_action(obs, {}, 1.0) in (Action.FOLD, Action.CHECK_CALL)


# ---------------------------------------------------------------------------
# All-in spots
# ---------------------------------------------------------------------------

def test_allin_price():
    # opp all-in over our 18: pot 18+80=98, we have 62 behind, to_call 62
    obs = _obs(to_call=62, my_bet=18, opp_bet=80, pot=98, my_stack=62, opp_stack=0)
    assert P.allin_price(obs) == pytest.approx(62 / 160)
    # facing a 4-bet to 54 with 26 left behind for them: treat as all-in for 80 each
    obs = _obs(to_call=36, my_bet=18, opp_bet=54, pot=72, my_stack=62, opp_stack=26)
    assert P.allin_price(obs) == pytest.approx(62 / 160)
    # their bet bigger than our stack: the unmatched part comes back
    obs = _obs(to_call=50, my_bet=10, opp_bet=60, pot=70, my_stack=30, opp_stack=20)
    assert P.allin_price(obs) == pytest.approx(30 / (70 - 20 + 30))


def _jam_obs(hole):
    # we opened to 6, BB jams 80: pot 86, to_call 74, price 74/160 = 0.4625
    return _obs(hole_cards=tuple(hole), to_call=74, my_bet=6, opp_bet=80, pot=86, my_stack=74,
                opp_stack=0, raises_this_street=2, legal_actions=(Action.FOLD, Action.CHECK_CALL))


def _hand_at(target: float) -> tuple:
    rng = random.Random(int(target * 1000))
    best = None
    for _ in range(4000):
        h = tuple(rng.sample(range(36), 5))
        d = abs(E.preflop_percentile(h) - target)
        if best is None or d < best[0]:
            best = (d, h)
    return best[1]


def test_allin_calls_strong_folds_weak():
    strong, weak = _hand_at(0.99), _hand_at(0.05)
    assert P.preflop_action(_jam_obs(strong), {}, E.preflop_percentile(strong)) == Action.CHECK_CALL
    assert P.preflop_action(_jam_obs(weak), {}, E.preflop_percentile(weak)) == Action.FOLD


def test_allin_fallback_without_time():
    t = P.THRESHOLDS
    h = _hand_at(0.5)
    mem = {"_time_left": t["allin_min_time"] / 2}
    assert P.preflop_action(_jam_obs(h), mem, t["allin_fallback_pct"] + 0.01) == Action.CHECK_CALL
    assert P.preflop_action(_jam_obs(h), mem, t["allin_fallback_pct"] - 0.01) == Action.FOLD


def test_allin_is_deterministic():
    h = _hand_at(0.7)
    obs = _jam_obs(h)
    pct = E.preflop_percentile(h)
    assert len({P.preflop_action(obs, {}, pct) for _ in range(5)}) == 1


def test_overrides_from_memory():
    mem = {"preflop_overrides": {"open_limp": 0.0, "open_raise": 1.01}}
    assert P.preflop_action(_obs(), mem, 0.01) == Action.CHECK_CALL
    assert P.preflop_action(_obs(), mem, 0.99) == Action.CHECK_CALL
    assert P.THRESHOLDS["open_raise"] < 1.0  # module defaults untouched


# ---------------------------------------------------------------------------
# Speed: no preflop decision may come near the 100 ms bug line
# ---------------------------------------------------------------------------

def test_decisions_are_fast():
    rng = random.Random(3)
    worst = 0.0
    for i in range(200):
        h = tuple(rng.sample(range(36), 5))
        obs = _jam_obs(h)
        t0 = time.perf_counter()
        P.preflop_action(obs, {}, E.preflop_percentile(h))
        worst = max(worst, time.perf_counter() - t0)
    assert worst < 0.02, f"slowest all-in decision {worst * 1000:.1f} ms"

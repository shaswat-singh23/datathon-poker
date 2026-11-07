"""Tests for bot/postflop.py.  Run: python -m pytest -q tests/test_postflop.py"""

import dataclasses
import os
import random
import sys
from itertools import combinations

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import equity as E  # noqa: E402
from bot import postflop as P  # noqa: E402
from game import Action, Deal, Game, Street  # noqa: E402

pytestmark = pytest.mark.skipif(not E.tables_loaded(), reason="run tools/build_tables.py first")

ALL = (Action.FOLD, Action.CHECK_CALL, Action.RAISE_HALF, Action.RAISE_POT)
SUBSETS = [s for k in range(1, 5) for s in combinations(ALL, k)]


def _random_postflop_obs(rng: random.Random):
    """Play random legal actions until a postflop decision; return its Observation."""
    while True:
        deck = list(range(36))
        rng.shuffle(deck)
        deal = Deal(hole_cards=(tuple(sorted(deck[:5])), tuple(sorted(deck[5:10]))),
                    board=tuple(deck[10:15]))
        g = Game(deal, button_seat=rng.randint(0, 1), hand_index=rng.randint(0, 999))
        target = rng.choice((Street.FLOP, Street.TURN, Street.RIVER))
        while not g.is_terminal:
            if g.street >= target:
                return g.observation(g.to_act)
            legal = g.legal_actions()
            # bias towards calls so hands reach later streets
            a = Action.CHECK_CALL if rng.random() < 0.6 else rng.choice(legal)
            if a == Action.FOLD and rng.random() < 0.8:
                a = Action.CHECK_CALL
            g.apply(a)


def _obs(rng, **kw):
    return dataclasses.replace(_random_postflop_obs(rng), **kw)


@pytest.fixture
def no_mc(monkeypatch):
    """Make equity() return a fixed value so decisions are deterministic."""
    box = {"eq": 0.5}
    monkeypatch.setattr(E, "equity", lambda *a, **k: box["eq"])
    return box


def test_property_always_legal_and_never_raises():
    rng = random.Random(1)
    mem = {}
    for i in range(150):
        obs = _random_postflop_obs(rng)
        assert obs.street in (Street.FLOP, Street.TURN, Street.RIVER)
        assert P.postflop_action(obs, mem, 1.0, rng=rng) in obs.legal_actions
        for legal in SUBSETS:
            o = dataclasses.replace(obs, legal_actions=legal)
            a = P.postflop_action(o, mem, rng.choice((0.0, 0.1, 0.5, 1.0)), rng=rng)
            assert a in legal, (legal, a)


def test_never_raises_on_bad_inputs(monkeypatch):
    rng = random.Random(2)
    obs = _random_postflop_obs(rng)
    for budget in (None, "x", float("nan"), -5, 0):
        assert P.postflop_action(obs, None, budget) in obs.legal_actions
    assert P.postflop_action(obs, {"opp_aggression": "junk"}, 1.0) in obs.legal_actions

    def boom(*a, **k):
        raise RuntimeError("engine down")
    monkeypatch.setattr(E, "equity", boom)
    monkeypatch.setattr(E, "hand_features", boom)
    assert P.postflop_action(obs, {}, 1.0) in obs.legal_actions
    assert P.postflop_action(dataclasses.replace(obs, legal_actions=()), {}, 1.0) == Action.CHECK_CALL


def test_equity_called_within_budget(monkeypatch):
    calls = []
    real = E.equity

    def spy(*a, **k):
        calls.append(k.get("time_budget_ms"))
        return real(*a, **k)
    monkeypatch.setattr(E, "equity", spy)
    rng = random.Random(3)
    for budget in (0.1, 0.3, 0.5, 1.0, 2.5, 10.0):
        calls.clear()
        P.postflop_action(_random_postflop_obs(rng), {}, budget, rng=rng)
        assert len(calls) <= 1
        assert all(b is not None and b <= budget for b in calls), (budget, calls)
        if budget * P.PARAMS["budget_frac"] >= P.PARAMS["min_budget_ms"]:
            assert len(calls) == 1


def test_calls_vs_pot_odds_with_margin(no_mc):
    rng = random.Random(4)
    legal = (Action.FOLD, Action.CHECK_CALL, Action.RAISE_HALF, Action.RAISE_POT)
    obs = _obs(rng, to_call=10, pot=30, legal_actions=legal, raises_this_street=1)
    odds = 10 / 40  # 0.25
    m = P.PARAMS["call_margin"]
    no_mc["eq"] = odds + m - 0.01
    assert P.postflop_action(obs, {}, 1.0) == Action.FOLD
    no_mc["eq"] = odds + m + 0.01
    assert P.postflop_action(obs, {}, 1.0) == Action.CHECK_CALL
    # configurable margin
    assert P.postflop_action(obs, {"postflop_params": {"call_margin": 0.2}}, 1.0) == Action.FOLD


def test_raises_with_strong_equity(no_mc):
    rng = random.Random(5)
    legal = (Action.FOLD, Action.CHECK_CALL, Action.RAISE_HALF, Action.RAISE_POT)
    obs = _obs(rng, to_call=4, pot=12, legal_actions=legal, raises_this_street=0)
    no_mc["eq"] = 0.99
    assert P.postflop_action(obs, {}, 1.0) == Action.RAISE_POT
    no_mc["eq"] = (P.PARAMS["raise_half_eq"] + P.PARAMS["raise_pot_eq"]) / 2
    assert P.postflop_action(obs, {}, 1.0) == Action.RAISE_HALF
    # raises not legal (cap reached): falls back to call
    capped = dataclasses.replace(obs, legal_actions=(Action.FOLD, Action.CHECK_CALL))
    no_mc["eq"] = 0.99
    assert P.postflop_action(capped, {}, 1.0) == Action.CHECK_CALL


def test_free_check_back_weak_and_bet_strong(no_mc):
    rng = random.Random(6)
    legal = (Action.CHECK_CALL, Action.RAISE_HALF, Action.RAISE_POT)
    obs = _obs(rng, to_call=0, legal_actions=legal, raises_this_street=0)
    never_bluff = {"postflop_params": {"bluff_freq": 0.0}}
    for eq in (0.0, 0.1, 0.3, 0.5):
        no_mc["eq"] = eq
        assert P.postflop_action(obs, never_bluff, 1.0) == Action.CHECK_CALL
    no_mc["eq"] = 0.99
    assert P.postflop_action(obs, {}, 1.0) == Action.RAISE_POT
    no_mc["eq"] = (P.PARAMS["bet_half_eq"] + P.PARAMS["bet_pot_eq"]) / 2
    assert P.postflop_action(obs, {}, 1.0) == Action.RAISE_HALF
    # never folds when checking is free, even if FOLD is offered
    no_mc["eq"] = 0.0
    o = dataclasses.replace(obs, legal_actions=(Action.FOLD, Action.CHECK_CALL))
    assert P.postflop_action(o, never_bluff, 1.0) == Action.CHECK_CALL


def test_bluff_frequency(no_mc):
    rng = random.Random(7)
    legal = (Action.CHECK_CALL, Action.RAISE_HALF, Action.RAISE_POT)
    obs = _random_postflop_obs(rng)
    while len(obs.board) < 4:
        obs = _random_postflop_obs(rng)
    obs = dataclasses.replace(obs, to_call=0, legal_actions=legal, raises_this_street=0)
    no_mc["eq"] = 0.05
    acts = [P.postflop_action(obs, {"postflop_params": {"bluff_freq": 0.5}}, 1.0, rng=rng)
            for _ in range(400)]
    frac = acts.count(Action.RAISE_HALF) / len(acts)
    assert 0.4 < frac < 0.6
    assert set(acts) <= {Action.CHECK_CALL, Action.RAISE_HALF}


def test_range_narrows_with_opponent_aggression():
    rng = random.Random(8)
    # find observations with and without opponent raises
    seen = {}
    for _ in range(300):
        obs = _random_postflop_obs(rng)
        n = sum(1 for h in obs.action_history if not h.is_me and h.action in P._RAISES)
        seen.setdefault(min(n, 2), obs)
    assert 0 in seen and 2 in seen
    assert P.opp_min_pct(seen[0], {}) == 0.0
    p2 = P.opp_min_pct(seen[2], {})
    assert 0.0 < p2 <= P.PARAMS["max_opp_pct"]
    # generally aggressive opponents narrow less, passive ones more
    assert P.opp_min_pct(seen[2], {"opp_aggression": 0.9}) < p2 < P.opp_min_pct(seen[2], {"opp_aggression": 0.0})


def test_monte_carlo_sanity():
    """Real equity: the nuts on the river raises; total air facing a pot bet folds."""
    from evaluator import cards_from_str
    board = cards_from_str("As Ks Qs Js 9d")
    nuts = cards_from_str("Ts 9s 6h 7c 8d")       # K-high straight flush, unbeatable
    air = cards_from_str("6h 6c 7d 7c 8h")        # a pair of sixes, ~0 equity
    legal = (Action.FOLD, Action.CHECK_CALL, Action.RAISE_HALF, Action.RAISE_POT)
    rng = random.Random(9)
    base = _obs(rng, street=Street.RIVER, board=tuple(board), legal_actions=legal,
                to_call=20, pot=60, raises_this_street=1, action_history=())
    assert P.postflop_action(dataclasses.replace(base, hole_cards=tuple(nuts)), {}, 1.0) == Action.RAISE_POT
    assert P.postflop_action(dataclasses.replace(base, hole_cards=tuple(air)), {}, 1.0) == Action.FOLD


def test_cat_eq_monotone_in_evaluator_order():
    import evaluator as EV
    order = (EV.HIGH_CARD, EV.ONE_PAIR, EV.TWO_PAIR, EV.STRAIGHT, EV.THREE_OF_A_KIND,
             EV.FULL_HOUSE, EV.FLUSH, EV.FOUR_OF_A_KIND, EV.STRAIGHT_FLUSH)
    assert all(P._CAT_EQ[a] < P._CAT_EQ[b] for a, b in zip(order, order[1:]))


def test_deterministic_same_inputs_same_decision():
    rng = random.Random(10)
    for _ in range(40):
        obs = _random_postflop_obs(rng)
        for budget in (0.1, 1.0, 5.0):
            # no rng: per-decision seed derived from the observation
            assert P.postflop_action(obs, {}, budget) == P.postflop_action(obs, {}, budget)
            assert P.estimate_equity(obs, {}, budget) == P.estimate_equity(obs, {}, budget)
            # same caller seed twice -> same equity and action
            e1 = P.estimate_equity(obs, {}, budget, rng=random.Random(42))
            e2 = P.estimate_equity(obs, {}, budget, rng=random.Random(42))
            assert e1 == e2
            assert (P.postflop_action(obs, {}, budget, rng=random.Random(42))
                    == P.postflop_action(obs, {}, budget, rng=random.Random(42)))


def test_rng_passed_to_equity(monkeypatch):
    seen = []
    real = E.equity

    def spy(*a, **k):
        seen.append(k.get("rng"))
        return real(*a, **k)
    monkeypatch.setattr(E, "equity", spy)
    obs = _random_postflop_obs(random.Random(11))
    r = random.Random(5)
    P.postflop_action(obs, {}, 1.0, rng=r)
    P.postflop_action(obs, {}, 1.0)
    assert seen[0] is r and seen[1] is not None


def test_huge_budget_is_capped_and_fast(monkeypatch):
    import time
    calls = []
    real = E.equity

    def spy(*a, **k):
        calls.append(k.get("time_budget_ms"))
        return real(*a, **k)
    monkeypatch.setattr(E, "equity", spy)
    rng = random.Random(12)
    worst = 0.0
    for _ in range(30):
        obs = _random_postflop_obs(rng)
        t0 = time.perf_counter()
        a = P.postflop_action(obs, {}, 5000.0, rng=rng)
        worst = max(worst, (time.perf_counter() - t0) * 1000.0)
        assert a in obs.legal_actions
    assert calls and max(calls) <= P.PARAMS["max_equity_ms"]
    assert worst < 100.0, worst

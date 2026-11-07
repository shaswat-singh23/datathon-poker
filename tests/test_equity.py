"""Tests for bot/equity.py.  Run: python -m pytest -q tests/test_equity.py"""

import math
import os
import random
import sys
from itertools import combinations

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import equity as E  # noqa: E402
from evaluator import cards_from_str, omaha_score  # noqa: E402

pytestmark = pytest.mark.skipif(not E.tables_loaded(), reason="run tools/build_tables.py first")


def _permute_suits(cards, perm):
    return [(c & ~3) | perm[c & 3] for c in cards]


def _ref_equity(hole, board, n, seed, min_pct=0.0):
    """Slow reference: plain Python sampling + evaluator.omaha_score."""
    rng = random.Random(seed)
    known = set(hole) | set(board)
    deck = [c for c in range(36) if c not in known]
    tot = 0.0
    done = 0
    while done < n:
        rng.shuffle(deck)
        opp = deck[:5]
        if min_pct > 0 and E.preflop_percentile(opp) < min_pct:
            continue
        full = list(board) + deck[5:5 + 5 - len(board)]
        a, b = omaha_score(hole, full), omaha_score(opp, full)
        tot += 1.0 if a > b else 0.5 if a == b else 0.0
        done += 1
    p = tot / n
    return p, math.sqrt(max(p * (1 - p), 1e-4) / n)


# ---------------------------------------------------------------------------
# scoring table
# ---------------------------------------------------------------------------

def test_vectorised_scores_match_evaluator():
    rng = random.Random(0)
    deals = np.array([rng.sample(range(36), 10) for _ in range(3000)])
    s = E.score_np(E.pair_values(deals[:, :5]), E.triple_values(deals[:, 5:]))
    raw = E._DENSE_TO_RAW[s]
    for i in range(len(deals)):
        assert raw[i] == omaha_score(deals[i, :5].tolist(), deals[i, 5:].tolist())


def test_best_score_matches_evaluator_on_full_board():
    rng = random.Random(1)
    for _ in range(2000):
        d = rng.sample(range(36), 10)
        assert E.best_score(d[:5], d[5:]) == omaha_score(d[:5], d[5:])


def test_hero_plus_villain_is_one_on_full_board():
    rng = random.Random(2)
    deals = np.array([rng.sample(range(36), 15) for _ in range(2000)])
    tv = E.triple_values(deals[:, 10:])
    a = E.score_np(E.pair_values(deals[:, :5]), tv)
    b = E.score_np(E.pair_values(deals[:, 5:10]), tv)
    wa = (a > b) + 0.5 * (a == b)
    wb = (b > a) + 0.5 * (a == b)
    assert np.allclose(wa + wb, 1.0)


# ---------------------------------------------------------------------------
# preflop table
# ---------------------------------------------------------------------------

def test_canonicalisation_invariant_under_suit_permutation():
    rng = random.Random(3)
    perms = [list(p) for p in __import__("itertools").permutations(range(4))]
    for _ in range(300):
        h = rng.sample(range(36), 5)
        base_eq, base_pct = E.preflop_equity(h), E.preflop_percentile(h)
        for p in rng.sample(perms, 6):
            h2 = _permute_suits(h, p)
            rng.shuffle(h2)
            assert E.canonical_key(h2) == E.canonical_key(h)
            assert E.preflop_equity(h2) == base_eq
            assert E.preflop_percentile(h2) == base_pct


def test_class_count_and_every_hand_has_a_class():
    hands = np.array(list(combinations(range(36), 5)))
    keys = E.canonical_keys_np(hands)
    assert len(set(keys.tolist())) == len(E._CLASS_INDEX)
    assert all(int(k) in E._CLASS_INDEX for k in keys[::997])


def test_preflop_table_averages_to_half():
    # E over a random hand of its equity vs a random hand must be exactly 0.5
    d = np.load(E._DATA_PATH)
    avg = float((d["class_eq"].astype(np.float64) * d["class_orbit"]).sum() / d["class_orbit"].sum())
    assert abs(avg - 0.5) < 0.001


def test_percentile_monotone_and_bounded():
    rng = random.Random(4)
    pts = []
    for _ in range(500):
        h = rng.sample(range(36), 5)
        pts.append((E.preflop_equity(h), E.preflop_percentile(h)))
    for eq, pct in pts:
        assert 0.0 <= eq <= 1.0 and 0.0 < pct <= 1.0
    pts.sort()
    for (e1, p1), (e2, p2) in zip(pts, pts[1:]):
        assert p2 >= p1 or e2 == e1
    assert max(E._CLASS_PCT) == 1.0


@pytest.mark.parametrize("hand", ["AsAhKsKhQd", "6c7d8h9sJc", "AcKcQcJcTc", "6c6d6h7c7d"])
def test_preflop_table_matches_reference(hand):
    h = cards_from_str(hand)
    ref, se = _ref_equity(h, [], 6000, seed=hash(hand) & 0xFFFF)
    _, tse = E.equity_se(h, [])
    assert abs(E.preflop_equity(h) - ref) < 3.5 * math.hypot(se, tse)


# ---------------------------------------------------------------------------
# Monte Carlo equity
# ---------------------------------------------------------------------------

def test_equity_in_unit_interval_all_streets():
    rng = random.Random(5)
    g = np.random.default_rng(5)
    for nb in (0, 3, 4, 5):
        for pct in (0.0, 0.5, 0.9):
            for _ in range(5):
                d = rng.sample(range(36), 5 + nb)
                e = E.equity(d[:5], d[5:], opp_min_pct=pct, rng=g)
                assert 0.0 <= e <= 1.0


def test_deterministic_with_rng():
    h, b = cards_from_str("AsKsQhJh9d"), cards_from_str("Ts8s7c")
    a = E.equity(h, b, rng=np.random.default_rng(42))
    assert a == E.equity(h, b, rng=np.random.default_rng(42))
    assert E.equity(h, b, rng=random.Random(7)) == E.equity(h, b, rng=random.Random(7))
    assert E.equity(h, b, rng=11) == E.equity(h, b, rng=11)


def test_river_matches_exact_enumeration():
    hole = cards_from_str("AhKhQd9s7c")
    board = cards_from_str("Jh8h6dTc6s")
    known = set(hole) | set(board)
    deck = [c for c in range(36) if c not in known]
    hs = omaha_score(hole, board)
    tot = n = 0
    for opp in combinations(deck, 5):
        s = omaha_score(opp, board)
        tot += 1.0 if hs > s else 0.5 if hs == s else 0.0
        n += 1
    exact = tot / n
    e, se = E.equity_se(hole, board, n_samples=50000, rng=1)
    assert abs(e - exact) < 3 * se + 1e-9


SPOTS = [
    ("AsKsQhJh9d", "Ts8s7c"),          # flop: straight + flush draws
    ("6c6d7h8hKs", "6h9hTd"),          # flop: set + draws
    ("AcAdKhQh7s", "Ah9hTd6c"),        # turn
    ("JcJdTsTh8c", "9c7d6sKh"),        # turn: made straight
    ("KsQsJd9d8c", "AsTs7s6hQc"),      # river
]


@pytest.mark.parametrize("hole,board", SPOTS)
@pytest.mark.parametrize("pct", [0.0, 0.6])
def test_equity_matches_reference(hole, board, pct):
    h, b = cards_from_str(hole), cards_from_str(board)
    ref, rse = _ref_equity(h, b, 4000, seed=len(hole + board) * 31 + int(pct * 10), min_pct=pct)
    e, se = E.equity_se(h, b, opp_min_pct=pct, n_samples=40000, rng=3)
    assert abs(e - ref) < 3.5 * math.hypot(se, rse), (e, ref, se, rse)


def test_preflop_range_matches_reference():
    h = cards_from_str("AsAhKsKhQd")
    ref, rse = _ref_equity(h, [], 3000, seed=9, min_pct=0.7)
    e, se = E.equity_se(h, [], opp_min_pct=0.7, n_samples=30000, rng=4)
    assert abs(e - ref) < 3.5 * math.hypot(se, rse)
    assert e < E.preflop_equity(h)  # a stronger range must lower our equity


def test_default_call_standard_error_is_useful(monkeypatch):
    # the cost model on its reference machine; on a loaded box fewer samples fit in 1 ms
    monkeypatch.setattr(E, "_SLOW", {k: 1.0 for k in E._SLOW})
    monkeypatch.setattr(E, "_SLOW_EMA", {k: 1.0 for k in E._SLOW})
    monkeypatch.setattr(E, "_observe_slow", lambda street, ratio: None)
    rng = random.Random(6)
    for nb in (3, 4, 5):
        d = rng.sample(range(36), 5 + nb)
        _, se = E.equity_se(d[:5], d[5:], rng=1)
        assert se < 0.03


def test_budget_is_respected():
    """Budgeted calls finish near time_budget_ms (generous bounds: CI boxes are noisy;
    exact numbers come from a 200-spot harness, see PR #28's description)."""
    import time
    rng = random.Random(8)
    for budget in (1.0, 8.0):
        for nb in (3, 4, 5):
            ts = []
            for _ in range(15):
                d = rng.sample(range(36), 5 + nb)
                t0 = time.perf_counter()
                E.equity(d[:5], d[5:], opp_min_pct=0.3, time_budget_ms=budget)
                ts.append((time.perf_counter() - t0) * 1e3)
            ts.sort()
            assert ts[len(ts) // 2] < 2.0 * budget + 1.0, (budget, nb, ts)


def test_budget_adapts_to_a_slower_machine(monkeypatch):
    """If the cost table is 3x too optimistic, the slowdown factor catches up and
    multi-batch calls stop at the deadline instead of overrunning ~3x."""
    import time
    cost = {k: (a / 3.0, b / 3.0) for k, (a, b) in E._COST.items()}
    monkeypatch.setattr(E, "_COST", cost)
    monkeypatch.setattr(E, "_SLOW", {k: 1.0 for k in E._SLOW})
    monkeypatch.setattr(E, "_SLOW_EMA", {k: 1.0 for k in E._SLOW})
    rng = random.Random(9)
    ts = []
    for _ in range(80):
        d = rng.sample(range(36), 8)
        t0 = time.perf_counter()
        E.equity(d[:5], d[5:], time_budget_ms=12.0)
        ts.append((time.perf_counter() - t0) * 1e3)
    assert E._SLOW[3] > 1.5
    late = sorted(ts[40:])
    assert late[len(late) // 2] < 18.0, late


def test_repeated_spot_is_deterministic_at_a_budget():
    rng = random.Random(10)
    for _ in range(30):
        d = rng.sample(range(36), 9)
        a = E.equity(d[:5], d[5:], time_budget_ms=2.0, rng=5)
        assert a == E.equity(d[:5], d[5:], time_budget_ms=2.0, rng=5)


def test_input_validation():
    with pytest.raises(ValueError):
        E.equity([0, 1, 2, 3], [])
    with pytest.raises(ValueError):
        E.equity([0, 1, 2, 3, 4], [5, 6])
    with pytest.raises(ValueError):
        E.equity([0, 1, 2, 3, 4], [4, 5, 6])


# ---------------------------------------------------------------------------
# features
# ---------------------------------------------------------------------------

def test_hand_features_basic():
    f = E.hand_features(cards_from_str("AsKsQhJh9d"), cards_from_str("Ts8s7c"))
    assert f["has_straight"] and f["category"] == 3  # J9 + T87

    assert f["flush_draw"] and f["nut_flush_draw"]
    f = E.hand_features(cards_from_str("6c6d7h8hKs"), cards_from_str("6h9hTd"))
    assert f["category"] == 4 and f["flush_draw"] and f["has_straight"]  # set beats straight
    f = E.hand_features(cards_from_str("JcTd7s7h6c"), cards_from_str("8c9dKh"))
    assert not f["has_straight"] and f["straight_outs"] == 6 and f["wrap"]  # 6,7,T,J,Q + A (wheel)
    f = E.hand_features(cards_from_str("AhKh9c8d6s"), cards_from_str("QhJh7h"))
    assert f["has_flush"] and f["nut_flush"] and f["category"] == 6
    f = E.hand_features(cards_from_str("AsAhKsKhQd"), [])
    assert f["hole_pairs"] == 2 and f["max_suit_hole"] == 2 and "category" not in f


def test_hand_features_category_matches_evaluator():
    rng = random.Random(8)
    for _ in range(300):
        d = rng.sample(range(36), 10)
        assert E.hand_features(d[:5], d[5:])["score"] == omaha_score(d[:5], d[5:])

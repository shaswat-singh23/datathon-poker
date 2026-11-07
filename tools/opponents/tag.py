"""
tag.py - sim opponent: TAG (tight-aggressive Monte Carlo equity bot).

The strongest reference opponent. Preflop: opens/3-bets good hands, defends
by pot odds. Postflop: Monte Carlo equity vs a random hand (~120 samples),
discounted when the opponent has shown aggression (their range is stronger
than random); value-bets and raises strong equity, calls on pot odds, folds
otherwise, and bluffs the river occasionally in position.

A plain bot module for tools/sim.py (new_half / choose_action / on_hand_end);
self-contained: imports only evaluator, game and the standard library.
"""

import os
import random
import sys
import time
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from evaluator import get_table  # noqa: E402
from game import Action, Street  # noqa: E402

FOLD, CALL, HALF, POT = Action.FOLD, Action.CHECK_CALL, Action.RAISE_HALF, Action.RAISE_POT
_TABLE = get_table()
_PAIRS = tuple(combinations(range(5), 2))
_TRIPLES = tuple(combinations(range(5), 3))
# 5%-step quantiles of pf_raw() over random hands (index i = percentile 5*i).
_PF_QUANTILES = (4.25, 12.15, 13.25, 14.05, 14.95, 15.8, 16.55, 17.4, 18.0, 18.65,
                 19.35, 20.0, 20.8, 21.8, 22.75, 23.75, 24.95, 26.05, 28.05, 30.65)


def pf_raw(hole):
    """Quick preflop heuristic: pairs, high cards, suitedness, connectedness."""
    ranks = sorted((c >> 2 for c in hole), reverse=True)
    cnt = {}
    for r in ranks:
        cnt[r] = cnt.get(r, 0) + 1
    s = 0.0
    for r, k in cnt.items():
        if k == 2:
            s += 4 + r * 0.8
        elif k >= 3:
            s += 1 + r * 0.3
    s += sum(ranks[:3]) * 0.35
    for su in range(4):
        sc = [c >> 2 for c in hole if c & 3 == su]
        if len(sc) >= 2:
            s += 2.5 + max(sc) * 0.4 - (1.5 if len(sc) >= 4 else 0)
    distinct = set(ranks)
    best = 0
    for lo in range(-1, 5):
        n = sum(1 for r in distinct if lo <= r <= lo + 4 or (lo == -1 and r == 8))
        best = max(best, n)
    s += (0, 0, 0, 1.5, 3.5, 5)[best]
    return s


def pf_pct(hole):
    """Approximate percentile (0..1) of this hand among random starting hands."""
    raw = pf_raw(hole)
    i = 0
    while i < len(_PF_QUANTILES) and raw >= _PF_QUANTILES[i]:
        i += 1
    return i / len(_PF_QUANTILES)


def pf_equity(hole):
    """Rough preflop equity vs a random hand (fitted to Monte Carlo)."""
    return min(0.68, max(0.36, 0.415 + 0.0089 * (pf_raw(hole) - 8.3)))


def _best(hole_masks, board):
    bb = [1 << c for c in board]
    t = _TABLE
    best = 0
    for i, j, k in _TRIPLES:
        bm = bb[i] | bb[j] | bb[k]
        for hm in hole_masks:
            s = t[hm | bm]
            if s > best:
                best = s
    return best


def mc_equity(hole, board, n, rng):
    """Monte Carlo equity vs one random hand (ties count half)."""
    hb = [1 << c for c in hole]
    hm = [hb[i] | hb[j] for i, j in _PAIRS]
    known = set(hole) | set(board)
    rest = [c for c in range(36) if c not in known]
    need = 5 - len(board)
    board = list(board)
    fixed = _best(hm, board) if need == 0 else None
    win = 0.0
    for _ in range(n):
        smp = rng.sample(rest, 5 + need)
        full = board + smp[5:] if need else board
        h = fixed if fixed is not None else _best(hm, full)
        ob = [1 << c for c in smp[:5]]
        o = _best([ob[i] | ob[j] for i, j in _PAIRS], full)
        if h > o:
            win += 1.0
        elif h == o:
            win += 0.5
    return win / n


def equity(obs, memory, samples):
    """Cached (per hand and street) equity; fewer samples once time runs low."""
    key = (obs.hand_index, int(obs.street))
    cache = memory.setdefault("eq_cache", {})
    if key not in cache:
        if obs.street == Street.PREFLOP:
            cache.clear()
            cache[key] = pf_equity(obs.hole_cards)
        else:
            if memory.get("clock", 0.0) > memory.get("budget", 4.0):
                samples = max(12, samples // 6)
            cache[key] = mc_equity(obs.hole_cards, obs.board, samples, memory["rng"])
    return cache[key]


def opp_raises(obs, street=None):
    """How many times the opponent bet/raised this hand (or on one street)."""
    return sum(1 for a in obs.action_history
               if not a.is_me and a.action in (HALF, POT) and (street is None or a.street == street))


def pot_odds(obs):
    return obs.to_call / (obs.pot + obs.to_call) if obs.to_call else 0.0


def pick(obs, *prefs):
    """First legal action among prefs; falls back to check/call."""
    for a in prefs:
        if a in obs.legal_actions:
            return a
    return CALL


def timed(fn):
    """Track thinking time in memory['clock'] so bots can stay inside the bank."""
    def wrapper(obs, memory):
        t0 = time.perf_counter()
        try:
            a = fn(obs, memory)
            return a if a in obs.legal_actions else CALL
        except Exception:  # never hand the judge an error
            if os.environ.get("OPP_DEBUG"):
                raise
            return CALL if obs.to_call == 0 else FOLD
        finally:
            memory["clock"] = memory.get("clock", 0.0) + time.perf_counter() - t0
    return wrapper


def new_half(config, memory):
    memory["rng"] = random.Random(22)
    memory["budget"] = 4.5


@timed
def choose_action(obs, memory):
    rng = memory["rng"]
    if obs.street == Street.PREFLOP:
        pct = pf_pct(obs.hole_cards)
        raises = opp_raises(obs, Street.PREFLOP)
        if pct >= 0.85 or (pct >= 0.6 and raises == 0):
            if obs.raises_this_street < 3 or pct >= 0.95:
                return pick(obs, POT)
            return CALL
        if obs.to_call == 0:
            return CALL
        need = pot_odds(obs)
        if pf_equity(obs.hole_cards) - 0.06 * raises > need + 0.08 or (pct >= 0.35 and obs.to_call <= 1):
            return CALL
        return FOLD

    eq = equity(obs, memory, 120)
    adj = eq - 0.07 * opp_raises(obs) - 0.05 * opp_raises(obs, obs.street)
    if obs.to_call == 0:
        if adj > 0.70:
            return pick(obs, POT)
        if adj > 0.58:
            return pick(obs, HALF)
        if obs.street == Street.RIVER and obs.is_button and eq < 0.25 and rng.random() < 0.15:
            return pick(obs, POT)
        return CALL
    if adj > 0.78:
        return pick(obs, POT)
    if adj > 0.68 and obs.raises_this_street < 2:
        return pick(obs, HALF)
    if adj > pot_odds(obs) + 0.06:
        return CALL
    return FOLD


def on_hand_end(result, memory):
    pass

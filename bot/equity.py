"""
bot/equity.py - fast hand-equity engine for heads-up Short Deck (36 cards) 5-card PLO.

Card encoding is the one from evaluator.py: rank = c >> 2 (0 = six .. 8 = ace),
suit = c & 3.  A player's hand value is the best of exactly 2 hole + 3 board cards.

Public API
----------
preflop_equity(hole)            -> float  equity vs one uniformly random 5-card hand (table, ~1-2 us)
preflop_percentile(hole)        -> float  0..1 fraction of starting hands with preflop equity <= this one
equity(hole, board, ...)        -> float  Monte Carlo equity (win + 0.5 tie) vs a range-narrowed opponent
equity_se(hole, board, ...)     -> (float, float)  same, plus the standard error of the estimate
hand_features(hole, board)      -> dict   cheap descriptive features
calibrate(...)                  -> dict   re-measure the base cost model on this machine (optional)

Time budget: without `n_samples`, equity() plans a sample count from a per-street
cost model scaled by a slowdown factor measured on this machine (a few-ms probe at
import, then a moving average of every call's measured time), draws it in batches,
and stops early if the clock says the next batch would end past ~1.15x the budget.
So a call takes about 0.75-1x time_budget_ms on any CPU.  At least _MIN_SAMPLES
samples are always drawn.

Randomness: `rng` may be a numpy Generator, a `random.Random`, an int seed, or None.
With a Generator / Random / int and a fixed `n_samples` the result is fully
reproducible.  A budgeted call is reproducible while the machine's speed is steady
(the planned count only changes when the slowdown factor drifts >30%, and never
between two back-to-back queries of the same spot); if the machine slows down
mid-call it returns fewer samples.  A `random.Random` is consumed for one 64-bit
seed per call.

How it is fast
--------------
* A 5-card Omaha hand value splits additively into (hole pair) + (board triple):
  index = PV[pair] + TV[triple] into a 185,625-entry int16 table T of dense
  hand ranks.  The pair part encodes (rank pair, suit if suited) and the triple
  part (rank triple, suit if monotone), arranged so a flush is just an index
  that lands in the "same suit" cell.  Scoring a 5-card hand on a 5-card board
  is one vectorised gather of 100 entries + max.
* River: per board a 1296-entry "best score for each 2-card hole pair" table,
  so each sampled opponent costs 10 gathers.
* Turn: the same table for every possible river card (pairs restricted to live
  cards), so each sample is again 10 gathers.
* Flop / preflop-with-range: direct vectorised scoring of sampled runouts.
* Preflop: table of ~16k suit-isomorphism classes (see tools/build_tables.py).
"""

from __future__ import annotations

import math
import os
import random as _pyrandom
import time
from itertools import combinations
from typing import Sequence

import numpy as np

NUM_CARDS = 36
_DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "equity_tables.npz")

# ---------------------------------------------------------------------------
# Additive pair/triple scoring table
# ---------------------------------------------------------------------------

_RANK_PAIRS = [(a, b) for a in range(9) for b in range(a, 9)]                       # 45
_RANK_TRIPLES = [(a, b, c) for a in range(9) for b in range(a, 9) for c in range(b, 9)]  # 165
_RP_ID = {rp: i for i, rp in enumerate(_RANK_PAIRS)}
_RT_ID = {rt: i for i, rt in enumerate(_RANK_TRIPLES)}
_N_RT = len(_RANK_TRIPLES)
_PAIR_STRIDE = _N_RT * 25  # 4125
T_SIZE = len(_RANK_PAIRS) * _PAIR_STRIDE  # 185,625

_PI, _PJ = (np.array(x, dtype=np.intp) for x in zip(*combinations(range(5), 2)))
_TA, _TB, _TC = (np.array(x, dtype=np.intp) for x in zip(*combinations(range(5), 3)))


def _build_pv_tv() -> tuple[np.ndarray, np.ndarray]:
    rp_id = np.full((9, 9), -1, dtype=np.int32)
    for (a, b), i in _RP_ID.items():
        rp_id[a, b] = rp_id[b, a] = i
    rt_id = np.zeros((9, 9, 9), dtype=np.int32)
    for (a, b, c), i in _RT_ID.items():
        for x, y, z in ((a, b, c), (a, c, b), (b, a, c), (b, c, a), (c, a, b), (c, b, a)):
            rt_id[x, y, z] = i
    c = np.arange(NUM_CARDS)
    r, s = c >> 2, c & 3
    c1, c2 = np.meshgrid(c, c, indexing="ij")
    sp = np.where(s[c1] == s[c2], s[c1], 4)
    pv = (rp_id[r[c1], r[c2]] * _PAIR_STRIDE + sp * 5).astype(np.int32)
    pv[c1 == c2] = 0
    c1, c2, c3 = np.meshgrid(c, c, c, indexing="ij")
    st = np.where((s[c1] == s[c2]) & (s[c2] == s[c3]), s[c1], 4)
    tv = (rt_id[r[c1], r[c2], r[c3]] * 25 + st).astype(np.int32)
    tv[(c1 == c2) | (c1 == c3) | (c2 == c3)] = 0
    return pv.ravel(), tv.ravel()


def build_score_table() -> tuple[np.ndarray, np.ndarray]:
    """Return (T, dense_to_raw).

    T[PV[pair] + TV[triple]] is the dense rank (1 = worst valid hand, 0 = impossible
    combination) of the 5-card hand pair+triple; dense_to_raw[d] is the matching
    evaluator.py score (dense_to_raw[0] = -1).
    """
    from evaluator import _score_ranks  # reference scoring logic

    cache: dict = {}
    raw = np.full(T_SIZE, -1, dtype=np.int64)
    for (a, b), ip in _RP_ID.items():
        for (x, y, z), it in _RT_ID.items():
            ranks = (a, b, x, y, z)
            if max(ranks.count(r) for r in set(ranks)) > 4:
                continue
            desc = tuple(sorted(ranks, reverse=True))
            for sp in range(5):
                if sp < 4 and a == b:
                    continue
                for st in range(5):
                    if st < 4 and (x == y or y == z):
                        continue
                    flush = sp == st and sp < 4
                    key = (desc, flush)
                    sc = cache.get(key)
                    if sc is None:
                        sc = _score_ranks(desc, flush)
                        cache[key] = sc
                    raw[ip * _PAIR_STRIDE + it * 25 + sp * 5 + st] = sc
    uniq = np.unique(raw[raw >= 0])
    dense = np.zeros(T_SIZE, dtype=np.int16)
    ok = raw >= 0
    dense[ok] = (np.searchsorted(uniq, raw[ok]) + 1).astype(np.int16)
    dense_to_raw = np.concatenate([[-1], uniq]).astype(np.int32)
    return dense, dense_to_raw


# ---------------------------------------------------------------------------
# Suit-isomorphism canonicalisation (preflop)
# ---------------------------------------------------------------------------

def canonical_key(hole: Sequence[int]) -> int:
    """Suit-permutation-invariant key: the 4 per-suit 9-bit rank masks, sorted."""
    m = [0, 0, 0, 0]
    for c in hole:
        m[c & 3] |= 1 << (c >> 2)
    m.sort()
    return m[0] | (m[1] << 9) | (m[2] << 18) | (m[3] << 27)


def canonical_keys_np(hands: np.ndarray) -> np.ndarray:
    """Vectorised canonical_key for an (N, k) int array of hands."""
    hands = hands.astype(np.int64)
    n = hands.shape[0]
    masks = np.zeros((n, 4), dtype=np.int64)
    rows = np.arange(n)
    for j in range(hands.shape[1]):
        c = hands[:, j]
        masks[rows, c & 3] |= np.left_shift(1, c >> 2)
    masks.sort(axis=1)
    return masks[:, 0] | (masks[:, 1] << 9) | (masks[:, 2] << 18) | (masks[:, 3] << 27)


# ---------------------------------------------------------------------------
# Vectorised scoring helpers (shared with tools/build_tables.py and tests)
# ---------------------------------------------------------------------------

PV, TV = _build_pv_tv()


def pair_values(hands: np.ndarray) -> np.ndarray:
    """(N,5) cards -> (N,10) pair values."""
    h = hands.astype(np.intp)
    return PV[h[:, _PI] * 36 + h[:, _PJ]]


def triple_values(boards: np.ndarray) -> np.ndarray:
    """(N,5) board cards -> (N,10) triple values."""
    b = boards.astype(np.intp)
    return TV[(b[:, _TA] * 36 + b[:, _TB]) * 36 + b[:, _TC]]


def score_np(pv: np.ndarray, tv: np.ndarray, table: np.ndarray | None = None) -> np.ndarray:
    """Dense scores for (N,10) pair values against (N,10) (or (10,)) triple values."""
    t = _T if table is None else table
    if tv.ndim == 1:
        tv = tv[None, :]
    idx = pv[:, :, None] + tv[:, None, :]
    return t[idx].reshape(idx.shape[0], -1).max(axis=1)


# ---------------------------------------------------------------------------
# Table loading
# ---------------------------------------------------------------------------

_T: np.ndarray | None = None
_DENSE_TO_RAW: np.ndarray | None = None
_T_LIST: list | None = None
_PV_LIST = PV.tolist()
_TV_LIST = TV.tolist()

_CLASS_INDEX: dict[int, int] = {}
_CLASS_EQ: list = []
_CLASS_PCT: list = []
_CLASS_N: np.ndarray | None = None
_HANDS: np.ndarray | None = None       # (NH,5) int8, sorted ascending by preflop equity
_HMASK: np.ndarray | None = None       # (NH,) uint64 card masks
_HPV: np.ndarray | None = None         # (NH,10) int32 pair values
_HPAIR: np.ndarray | None = None       # (NH,10) int16 pair keys c1*36+c2 (c1<c2)
_HPCT: np.ndarray | None = None        # (NH,) float32 percentile of each sorted hand (non-decreasing)
_NH = 0
_LOADED = False
LOAD_SECONDS = 0.0

_PAIRS630 = np.array(list(combinations(range(NUM_CARDS), 2)), dtype=np.int64)
_PAIR_MASK = (np.uint64(1) << _PAIRS630[:, 0].astype(np.uint64)) | (np.uint64(1) << _PAIRS630[:, 1].astype(np.uint64))
_CARD_MASK = np.uint64(1) << np.arange(NUM_CARDS, dtype=np.uint64)


def _load(path: str = _DATA_PATH) -> None:
    global _T, _DENSE_TO_RAW, _T_LIST, _CLASS_INDEX, _CLASS_EQ, _CLASS_PCT, _CLASS_N
    global _HANDS, _HMASK, _HPV, _HPAIR, _HPCT, _NH, _LOADED, LOAD_SECONDS
    t0 = time.perf_counter()
    if not os.path.exists(path):
        _T, _DENSE_TO_RAW = build_score_table()
        _T_LIST = _T.tolist()
        LOAD_SECONDS = time.perf_counter() - t0
        return
    d = np.load(path)
    _T = d["T"]
    _DENSE_TO_RAW = d["dense_to_raw"]
    _T_LIST = _T.tolist()
    keys = d["class_keys"].tolist()
    _CLASS_INDEX = {k: i for i, k in enumerate(keys)}
    _CLASS_EQ = d["class_eq"].astype(np.float64).tolist()
    pct = d["class_pct"]
    _CLASS_PCT = pct.astype(np.float64).tolist()
    _CLASS_N = d["class_n"]
    _HANDS = d["hands_by_eq"].astype(np.int8)
    _HPCT = pct[d["hands_class"]]
    _NH = _HANDS.shape[0]
    h = _HANDS.astype(np.intp)
    _HMASK = np.bitwise_or.reduce(_CARD_MASK[h], axis=1)
    keys_p = h[:, _PI] * 36 + h[:, _PJ]
    _HPAIR = keys_p.astype(np.int16)
    _HPV = PV[keys_p]
    _LOADED = True
    LOAD_SECONDS = time.perf_counter() - t0


_load()


def tables_loaded() -> bool:
    return _LOADED


# ---------------------------------------------------------------------------
# Preflop
# ---------------------------------------------------------------------------

def _class_id(hole: Sequence[int]) -> int:
    m = [0, 0, 0, 0]
    for c in hole:
        m[c & 3] |= 1 << (c >> 2)
    m.sort()
    return _CLASS_INDEX[m[0] | (m[1] << 9) | (m[2] << 18) | (m[3] << 27)]


def preflop_equity(hole: Sequence[int]) -> float:
    """Equity (win + tie/2) of 5 hole cards vs one uniformly random 5-card hand, all-in preflop."""
    return _CLASS_EQ[_class_id(hole)]


def preflop_percentile(hole: Sequence[int]) -> float:
    """Fraction (0..1] of all C(36,5) starting hands whose preflop equity is <= this hand's."""
    return _CLASS_PCT[_class_id(hole)]


# ---------------------------------------------------------------------------
# Monte Carlo equity
# ---------------------------------------------------------------------------

# Cost model (microseconds) per street: fixed overhead + per-sample cost.
# Measured on the dev laptop (Apple Silicon); call calibrate() to re-measure.
_COST = {
    0: (50.0, 0.47),   # preflop with a range: direct scoring of 5-card runouts
    3: (40.0, 0.45),   # flop: direct scoring of 2-card runouts
    4: (210.0, 0.08),  # turn: per-river pair tables
    5: (50.0, 0.065),   # river: one pair table
}
_MIN_SAMPLES = 64
_MAX_SAMPLES = 200_000
_DEFAULT_RNG = np.random.default_rng()

# Budgeted sampling.  The sample count for a budget is planned from _COST scaled by a
# per-street slowdown factor _SLOW[street] = (measured time) / (_COST prediction) on
# this machine.  _SLOW is set at import by a few-ms probe and then follows _SLOW_EMA
# (a slow moving average of the measured ratio after every call), but only jumps when
# the average drifts more than _HYST away, so on a steady machine the planned count,
# and hence the result for a given rng, stays the same from call to call.  A jump is
# applied only when the queried spot changes, so asking about the same spot twice in
# a row (same cards, range and budget) always plans the same count.  Samples
# are drawn in batches of at most _MAX_BATCH_US, and if the clock says the next batch
# would end past _HARD * budget the call stops early (machine suddenly slower).
# Worst steady state: _SLOW_EMA = _HYST * _SLOW -> calls take _TARGET * _HYST ~ 0.975x the budget.
_SLOW = {0: 1.0, 3: 1.0, 4: 1.0, 5: 1.0}
_SLOW_EMA = dict(_SLOW)
_SLOW_MIN, _SLOW_MAX = 0.25, 50.0
_SLOW_ALPHA = 0.05
_HYST = 1.3              # re-plan when the average moves more than 30% from _SLOW
_TARGET = 0.75           # plan to finish at this fraction of the budget
_HARD = 1.15             # never start a batch predicted to end past this fraction
_MAX_BATCH_US = 4000.0   # one batch's predicted cost cap
_BATCH_OVH_US = 25.0     # extra overhead per additional batch (dev laptop)
_OBSERVE_MIN_US = 400.0  # only calls predicted at least this long update _SLOW_EMA
_LAST_SPOT = None


def _to_generator(rng) -> np.random.Generator:
    if rng is None:
        return _DEFAULT_RNG
    if isinstance(rng, np.random.Generator):
        return rng
    if isinstance(rng, _pyrandom.Random):
        return np.random.default_rng(rng.getrandbits(64))
    if isinstance(rng, (int, np.integer)):
        return np.random.default_rng(int(rng))
    raise TypeError("rng must be a numpy Generator, random.Random, int seed or None")


def _n_for_budget(street: int, budget_ms: float) -> int:
    """Sample count the cost model predicts fits in budget_ms on this machine."""
    fixed, per = _COST[street]
    n = int((budget_ms * 1000.0 / _SLOW[street] - fixed) / per)
    return max(_MIN_SAMPLES, min(_MAX_SAMPLES, n))


def _set_slow(street: int, ratio: float) -> None:
    r = min(_SLOW_MAX, max(_SLOW_MIN, ratio))
    _SLOW[street] = _SLOW_EMA[street] = r


def _observe_slow(street: int, ratio: float) -> None:
    """Fold one call's measured/predicted time ratio into the street's slowdown factor."""
    ema = _SLOW_EMA[street]
    ratio = min(2.0 * ema, max(0.5 * ema, ratio))  # one preempted call moves it little
    ema = (1.0 - _SLOW_ALPHA) * ema + _SLOW_ALPHA * ratio
    ema = min(_SLOW_MAX, max(_SLOW_MIN, ema))
    _SLOW_EMA[street] = ema


def _replan(street: int, spot) -> None:
    """Move _SLOW[street] to the average if it drifted out of band and the spot changed."""
    global _LAST_SPOT
    if spot == _LAST_SPOT:
        return
    _LAST_SPOT = spot
    ema = _SLOW_EMA[street]
    if not (1.0 / _HYST <= ema / _SLOW[street] <= _HYST):
        _SLOW[street] = ema


def _sample_budget(draw, street: int, budget_ms: float, t0: float) -> np.ndarray:
    """Draw the planned number of samples for budget_ms in batches, stopping early if
    the clock says the next batch would end well past the budget."""
    fixed, per = _COST[street]
    slow = _SLOW[street]
    n_plan = _n_for_budget(street, _TARGET * budget_ms)
    per_batch = max(_MIN_SAMPLES, int((_MAX_BATCH_US / slow - _BATCH_OVH_US) / per))
    k = -(-n_plan // per_batch)
    size = -(-n_plan // k)
    hard = t0 + _HARD * budget_ms / 1000.0
    batch_s = slow * (_BATCH_OVH_US + per * size) / 1e6
    chunks = []
    got = 0
    while got < n_plan:
        if got >= _MIN_SAMPLES and time.perf_counter() + batch_s > hard:
            break
        m = min(size, n_plan - got)
        chunks.append(draw(m))
        got += m
    elapsed_us = (time.perf_counter() - t0) * 1e6
    pred_us = fixed + per * got + _BATCH_OVH_US * (len(chunks) - 1)
    if pred_us >= _OBSERVE_MIN_US:  # tiny calls measure Python overhead, not throughput
        _observe_slow(street, elapsed_us / pred_us)
    return chunks[0] if len(chunks) == 1 else np.concatenate(chunks)


def _range_start(opp_min_pct: float) -> int:
    if opp_min_pct <= 0.0:
        return 0
    start = int(np.searchsorted(_HPCT, np.float32(opp_min_pct), side="left"))
    return min(start, _NH - 2000)  # always keep a few thousand hands in range


def _sample_opps(g: np.random.Generator, n: int, known: int, start: int) -> np.ndarray:
    """n indices into the sorted hand list, uniform over [start, NH) avoiding `known` cards."""
    known_u = np.uint64(known)
    out = []
    got = 0
    acc = math.comb(NUM_CARDS - bin(known).count("1"), 5) / math.comb(NUM_CARDS, 5)
    for _ in range(50):
        need = n - got
        m = int(need / max(acc, 0.02) * 1.15) + 32
        idx = g.integers(start, _NH, size=m)
        ok = (_HMASK[idx] & known_u) == 0
        sel = idx[ok]
        if sel.size:
            acc = max(0.5 * acc, sel.size / m)
        out.append(sel[:need])
        got += min(need, sel.size)
        if got >= n:
            break
    res = np.concatenate(out)
    if res.size < n:
        raise RuntimeError("could not sample opponent hands (range too narrow?)")
    return res


def _sample_runouts(g: np.random.Generator, excl: np.ndarray, k: int, known_count: int) -> np.ndarray:
    """For each row, a uniformly random k-subset of cards (k in {2, 5}) disjoint from excl[row].

    Returns (n, k) int array.
    """
    n = excl.shape[0]
    if k == 2:
        pool, pool_mask = _PAIRS630, _PAIR_MASK
    else:
        pool, pool_mask = _HANDS, _HMASK
    live = NUM_CARDS - known_count
    acc = math.comb(live, k) / math.comb(NUM_CARDS, k)
    c = int(math.ceil(math.log(0.03) / math.log(1.0 - acc)))
    c = max(2, min(c, 40))
    res = np.empty(n, dtype=np.int64)
    pending = np.arange(n)
    for _ in range(200):
        p = pending.size
        cand = g.integers(0, pool.shape[0], size=(p, c))
        ok = (pool_mask[cand] & excl[pending][:, None]) == 0
        anyok = ok.any(axis=1)
        first = ok.argmax(axis=1)
        done = pending[anyok]
        res[done] = cand[anyok, first[anyok]]
        pending = pending[~anyok]
        if pending.size == 0:
            break
    return pool[res].astype(np.intp)


def _validate(hole: Sequence[int], board: Sequence[int]) -> None:
    if len(hole) != 5:
        raise ValueError("hole must have 5 cards")
    if len(board) not in (0, 3, 4, 5):
        raise ValueError("board must have 0, 3, 4 or 5 cards")
    allc = list(hole) + list(board)
    if len(set(allc)) != len(allc) or min(allc) < 0 or max(allc) >= NUM_CARDS:
        raise ValueError("cards must be distinct ints in 0..35")


def equity_se(hole: Sequence[int], board: Sequence[int], *, opp_min_pct: float = 0.0,
              n_samples: int | None = None, time_budget_ms: float = 1.0, rng=None) -> tuple[float, float]:
    """Like equity() but returns (equity, standard_error). SE is 0.0 for pure table lookups."""
    t0 = time.perf_counter()
    if not _LOADED:
        raise RuntimeError(f"equity tables missing: run tools/build_tables.py (expected {_DATA_PATH})")
    _validate(hole, board)
    nb = len(board)
    if nb == 0 and opp_min_pct <= 0.0:
        cid = _class_id(hole)
        eq = _CLASS_EQ[cid]
        return eq, math.sqrt(eq * (1.0 - eq) / max(1, int(_CLASS_N[cid])))
    g = _to_generator(rng)
    draw = _make_sampler(hole, board, opp_min_pct, g)
    if n_samples is not None:
        w = draw(max(1, int(n_samples)))
    else:
        _replan(nb, (tuple(hole), tuple(board), opp_min_pct, time_budget_ms))
        w = _sample_budget(draw, nb, float(time_budget_ms), t0)
    n = w.size
    mean = float(w.mean())
    se = float(w.std() / math.sqrt(n)) if n > 1 else 0.5
    return mean, se


def equity(hole: Sequence[int], board: Sequence[int], *, opp_min_pct: float = 0.0,
           n_samples: int | None = None, time_budget_ms: float = 1.0, rng=None) -> float:
    """Monte Carlo equity (win + 0.5 tie) vs one opponent holding a random hand with
    preflop_percentile >= opp_min_pct (no card collisions); the board (0, 3, 4 or 5
    cards) is completed at random.

    n_samples: exact number of (opponent, runout) samples; if None, samples are
    drawn in batches until about time_budget_ms has elapsed (at least _MIN_SAMPLES).
    Board = 0 with opp_min_pct = 0 returns preflop_equity(hole).
    """
    return equity_se(hole, board, opp_min_pct=opp_min_pct, n_samples=n_samples,
                     time_budget_ms=time_budget_ms, rng=rng)[0]


def _equity_samples(hole, board, opp_min_pct, n, g) -> np.ndarray:
    return _make_sampler(hole, board, opp_min_pct, g)(n)


def _make_sampler(hole, board, opp_min_pct, g):
    """Do the per-spot setup once; return draw(n) -> (n,) array of win (1/0.5/0) samples."""
    nb = len(board)
    known = 0
    for c in hole:
        known |= 1 << c
    for c in board:
        known |= 1 << c
    start = _range_start(opp_min_pct)
    hole_a = np.asarray(hole, dtype=np.intp)
    hpv = PV[hole_a[_PI] * 36 + hole_a[_PJ]]  # (10,)

    if nb == 5:
        b = np.asarray(board, dtype=np.intp)
        tv = TV[(b[_TA] * 36 + b[_TB]) * 36 + b[_TC]]  # (10,)
        hero = int(_T[hpv[:, None] + tv[None, :]].max())
        pt = _T[PV[:, None] + tv[None, :]].max(axis=1)  # (1296,)

        def draw_river(n):
            opp = _sample_opps(g, n, known, start)
            opp_s = pt[_HPAIR[opp]].max(axis=1)
            return (opp_s < hero) + 0.5 * (opp_s == hero)
        return draw_river

    if nb == 4:
        live = np.array([c for c in range(NUM_CARDS) if not (known >> c) & 1], dtype=np.intp)
        R = live.size
        b = np.asarray(board, dtype=np.intp)
        boards = np.empty((R, 5), dtype=np.intp)
        boards[:, :4] = b
        boards[:, 4] = live
        tv = TV[(boards[:, _TA] * 36 + boards[:, _TB]) * 36 + boards[:, _TC]]  # (R,10)
        hero = _T[hpv[None, :, None] + tv[:, None, :]].reshape(R, -1).max(axis=1)  # (R,)
        li, lj = np.triu_indices(R, 1)
        keys = live[li] * 36 + live[lj]  # pairs of live cards, c1 < c2
        vals = _T[PV[keys][None, :, None] + tv[:, None, :]].max(axis=2)  # (R, P)
        pt = np.zeros((R, 1296), dtype=_T.dtype)
        pt[:, keys] = vals
        pt = pt.ravel()
        live_u = live.astype(np.uint64)

        def draw_turn(n):
            opp = _sample_opps(g, n, known, start)
            omask = _HMASK[opp]
            ri = g.integers(0, R, size=n)
            for _ in range(100):
                bad = ((omask >> live_u[ri]) & np.uint64(1)).astype(bool)
                nbad = int(bad.sum())
                if nbad == 0:
                    break
                ri[bad] = g.integers(0, R, size=nbad)
            opp_s = pt[ri[:, None] * 1296 + _HPAIR[opp]].max(axis=1)
            h = hero[ri]
            return (opp_s < h) + 0.5 * (opp_s == h)
        return draw_turn

    # flop (2-card runout) or preflop with a range (5-card runout): direct scoring
    k = 5 - nb
    known_count = bin(known).count("1") + 5
    board_a = np.asarray(board, dtype=np.intp)

    def draw_direct(n):
        opp = _sample_opps(g, n, known, start)
        excl = _HMASK[opp] | np.uint64(known)
        run = _sample_runouts(g, excl, k, known_count)
        boards = np.empty((n, 5), dtype=np.intp)
        if nb:
            boards[:, :nb] = board_a
        boards[:, nb:] = run
        tv = TV[(boards[:, _TA] * 36 + boards[:, _TB]) * 36 + boards[:, _TC]]  # (n,10)
        hero = _T[hpv[None, :, None] + tv[:, None, :]].reshape(n, -1).max(axis=1)
        ov = _HPV[opp]
        opp_s = _T[ov[:, :, None] + tv[:, None, :]].reshape(n, -1).max(axis=1)
        return (opp_s < hero) + 0.5 * (opp_s == hero)
    return draw_direct


def calibrate(repeats: int = 7, seed: int = 0) -> dict:
    """Re-measure the per-street cost model on this machine (takes ~0.3 s) and reset
    the slowdown factors to 1.  Optional: budgeted calls already adapt via _SLOW.
    Returns the new {street: (fixed_us, per_sample_us)}.
    """
    g = np.random.default_rng(seed)
    spots = {0: 0, 3: 3, 4: 4, 5: 5}
    deck = list(range(NUM_CARDS))
    for street in spots:
        cards = g.permutation(deck)[:10].tolist()
        hole, board = cards[:5], cards[5:5 + street]
        times = {}
        for n in (300, 3000):
            best = float("inf")
            for _ in range(repeats):
                t0 = time.perf_counter()
                _equity_samples(hole, board, 0.3 if street == 0 else 0.0, n, g)
                best = min(best, time.perf_counter() - t0)
            times[n] = best * 1e6
        per = max(0.01, (times[3000] - times[300]) / 2700.0)
        fixed = max(0.0, times[300] - 300 * per)
        _COST[street] = (fixed * 1.1, per * 1.1)
    for street in _SLOW:
        _set_slow(street, 1.0)
    return dict(_COST)


def _quick_slowdown(seed: int = 0) -> None:
    """Import-time estimate of _SLOW per street: median of 3 small timed calls each
    (~0.3-0.5 ms per call on the dev laptop, a few ms in total)."""
    if not _LOADED:
        return
    g = np.random.default_rng(seed)
    hole = [0, 5, 10, 15, 20]
    probes = {0: ([], 0.5, 600), 3: ([25, 30, 35], 0.0, 1000),
              4: ([25, 30, 35, 1], 0.0, 2000), 5: ([25, 30, 35, 1, 6], 0.0, 3000)}
    for street, (board, pct, n) in probes.items():
        _make_sampler(hole, board, pct, g)(64)  # warm caches
        times = []
        for _ in range(3):
            t0 = time.perf_counter()
            _make_sampler(hole, board, pct, g)(n)
            times.append((time.perf_counter() - t0) * 1e6)
        fixed, per = _COST[street]
        _set_slow(street, sorted(times)[1] / (fixed + per * n))


try:
    _quick_slowdown()
except Exception:  # never let a timing probe break import
    pass


# ---------------------------------------------------------------------------
# Hand features
# ---------------------------------------------------------------------------

_STRAIGHT_MASKS = [0b11111 << i for i in range(5)] + [(1 << 8) | 0b1111]  # wheel A6789
_PAIRS5 = list(combinations(range(5), 2))
_TRIPLES = {n: list(combinations(range(n), 3)) for n in (3, 4, 5)}


def _popcount(x: int) -> int:
    return bin(x).count("1")


def _made_straight(hole_ranks: int, board_ranks: int) -> bool:
    """Exactly-2-hole + 3-board straight from rank bitmasks."""
    for w in _STRAIGHT_MASKS:
        if (w & ~(hole_ranks | board_ranks)) == 0 and _popcount(w & ~board_ranks) <= 2 \
                and _popcount(w & hole_ranks) >= 2:
            return True
    return False


def best_score(hole: Sequence[int], board: Sequence[int]) -> int:
    """evaluator-compatible best score (2 hole + 3 board) for a 3, 4 or 5-card board."""
    T = _T_LIST
    pvl, tvl = _PV_LIST, _TV_LIST
    pv = [pvl[hole[i] * 36 + hole[j]] for i, j in _PAIRS5]
    best = 0
    for a, b, c in _TRIPLES[len(board)]:
        t = tvl[(board[a] * 36 + board[b]) * 36 + board[c]]
        for p in pv:
            s = T[p + t]
            if s > best:
                best = s
    return int(_DENSE_TO_RAW[best])


def hand_features(hole: Sequence[int], board: Sequence[int]) -> dict:
    """Cheap descriptive features (~10-30 us).

    Always: n_board, max_suit_hole (most cards of one suit in hand), hole_pairs
    (number of paired ranks in hand), rank_span_connected (longest run of
    consecutive distinct hole ranks, wheel-aware), preflop_equity/percentile
    (if tables loaded).
    Board >= 3: score (evaluator-compatible), category (0..8, evaluator.category_of),
    flush_draw, nut_flush_draw, has_flush, nut_flush, straight_outs (distinct ranks
    that would complete a straight next card, 0 if already made), oesd (>= 2),
    wrap (>= 3), straight_out_cards (unseen cards giving those ranks),
    board_paired, board_monotone/two_tone flags, board_max_suit.
    """
    feats: dict = {"n_board": len(board)}
    hs = [0, 0, 0, 0]
    hr_counts = [0] * 9
    hole_ranks = 0
    hole_suit_ranks = [0, 0, 0, 0]
    for c in hole:
        s, r = c & 3, c >> 2
        hs[s] += 1
        hr_counts[r] += 1
        hole_ranks |= 1 << r
        hole_suit_ranks[s] |= 1 << r
    feats["max_suit_hole"] = max(hs)
    feats["hole_pairs"] = sum(1 for x in hr_counts if x >= 2)
    run = best_run = 0
    for r in (8, 0, 1, 2, 3, 4, 5, 6, 7, 8):  # ace plays low (A-6-7-8-9) and high
        run = run + 1 if (hole_ranks >> r) & 1 else 0
        best_run = max(best_run, run)
    feats["rank_span_connected"] = best_run
    if _LOADED:
        cid = _class_id(hole)
        feats["preflop_equity"] = _CLASS_EQ[cid]
        feats["preflop_percentile"] = _CLASS_PCT[cid]
    if len(board) < 3:
        return feats

    score = best_score(hole, board)
    cat = score >> 20
    feats["score"] = score
    feats["category"] = cat
    bs = [0, 0, 0, 0]
    board_ranks = 0
    board_suit_ranks = [0, 0, 0, 0]
    br_counts = [0] * 9
    for c in board:
        s, r = c & 3, c >> 2
        bs[s] += 1
        board_ranks |= 1 << r
        board_suit_ranks[s] |= 1 << r
        br_counts[r] += 1
    feats["board_paired"] = max(br_counts) >= 2
    feats["board_max_suit"] = max(bs)
    nb = len(board)
    flush_draw = nut_fd = has_flush = nut_flush = False
    for s in range(4):
        if hs[s] >= 2 and bs[s] >= 3:
            has_flush = True
            used = hole_suit_ranks[s] | board_suit_ranks[s]
            missing = [r for r in range(8, -1, -1) if not (used >> r) & 1]
            top_hole = max(r for r in range(9) if (hole_suit_ranks[s] >> r) & 1)
            # nut flush: no unseen card of this suit outranks our best flush card
            if not missing or top_hole > missing[0]:
                nut_flush = True
        if nb < 5 and hs[s] >= 2 and bs[s] == 2:
            flush_draw = True
            used = hole_suit_ranks[s] | board_suit_ranks[s]
            missing = [r for r in range(8, -1, -1) if not (used >> r) & 1]
            top_hole = max(r for r in range(9) if (hole_suit_ranks[s] >> r) & 1)
            if not missing or top_hole > missing[0]:
                nut_fd = True
    feats["flush_draw"] = flush_draw
    feats["nut_flush_draw"] = nut_fd
    feats["has_flush"] = has_flush
    feats["nut_flush"] = nut_flush

    made = _made_straight(hole_ranks, board_ranks)
    feats["has_straight"] = made
    outs = 0
    out_cards = 0
    if nb < 5 and not made:
        seen = [0] * 9
        for c in hole:
            seen[c >> 2] += 1
        for c in board:
            seen[c >> 2] += 1
        for r in range(9):
            if _made_straight(hole_ranks, board_ranks | (1 << r)):
                outs += 1
                out_cards += 4 - seen[r]
    feats["straight_outs"] = outs
    feats["straight_out_cards"] = out_cards
    feats["oesd"] = outs >= 2
    feats["wrap"] = outs >= 3
    return feats


# ---------------------------------------------------------------------------
# Benchmark:  python -m bot.equity
# ---------------------------------------------------------------------------

def _bench() -> None:
    rng = _pyrandom.Random(0)
    print(f"table load: {LOAD_SECONDS * 1000:.1f} ms; data file {os.path.getsize(_DATA_PATH) / 1e6:.2f} MB")
    hands = [rng.sample(range(NUM_CARDS), 5) for _ in range(20000)]
    t0 = time.perf_counter()
    for h in hands:
        preflop_equity(h)
    print(f"preflop_equity: {(time.perf_counter() - t0) / len(hands) * 1e6:.2f} us/call")
    t0 = time.perf_counter()
    for h in hands[:5000]:
        hand_features(h, [])
    print(f"hand_features preflop: {(time.perf_counter() - t0) / 5000 * 1e6:.1f} us/call")
    g = np.random.default_rng(0)
    for nb, pct in ((3, 0.0), (4, 0.0), (5, 0.0), (0, 0.5), (3, 0.5), (4, 0.5), (5, 0.5)):
        spots = [rng.sample(range(NUM_CARDS), 5 + nb) for _ in range(300)]
        ses = []
        t0 = time.perf_counter()
        for d in spots:
            ses.append(equity_se(d[:5], d[5:], opp_min_pct=pct, rng=g)[1])
        dt = (time.perf_counter() - t0) / len(spots) * 1e3
        tmax = 0.0
        for d in spots[:100]:
            t1 = time.perf_counter()
            equity_se(d[:5], d[5:], opp_min_pct=pct, rng=g)
            tmax = max(tmax, time.perf_counter() - t1)
        print(f"equity board={nb} opp_min_pct={pct}: {dt:.3f} ms/call (max {tmax * 1e3:.2f}), "
              f"slow={_SLOW[nb]:.2f}, mean SE {np.mean(ses):.4f}, max SE {np.max(ses):.4f}")
        if nb >= 3:
            t0 = time.perf_counter()
            for d in spots:
                hand_features(d[:5], d[5:])
            print(f"   hand_features board={nb}: {(time.perf_counter() - t0) / len(spots) * 1e6:.1f} us/call")


if __name__ == "__main__":
    _bench()

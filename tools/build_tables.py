"""
tools/build_tables.py - regenerate bot/data/equity_tables.npz (offline).

Usage:
    python tools/build_tables.py [--deals 400] [--min-samples 40000] [--workers N] [--seed 1]

What it computes
----------------
* T / dense_to_raw: the additive pair+triple scoring table (see bot/equity.py).
* The suit-isomorphism classes of the C(36,5) = 376,992 starting hands.
* Each class's all-in preflop equity vs ONE uniformly random opponent hand,
  estimated by Monte Carlo:
    1. "--deals" million uniformly random deals (hero 5, villain 5, board 5);
       every deal is credited to BOTH players' classes (hero gets w, villain
       1 - w), which is unbiased for both because the deal is uniform.
    2. Top-up: classes with fewer than --min-samples samples (small orbits,
       e.g. hands symmetric under a suit swap) get extra stratified samples
       with the class representative as hero.
* class_pct: fraction of all 376,992 hands whose class equity is <= this class's.
* hands_by_eq / hands_class: every hand sorted by preflop equity (used for
  range-narrowed opponent sampling).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from itertools import combinations
from multiprocessing import Pool

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bot import equity as E  # noqa: E402

OUT = os.path.join(ROOT, "bot", "data", "equity_tables.npz")
BATCH = 50_000

# shared (per worker) state
_G = {}


def colex(hands_sorted: np.ndarray, binom: np.ndarray) -> np.ndarray:
    h = hands_sorted.astype(np.intp)
    return sum(binom[h[:, i], i + 1] for i in range(5))


def _init(T, class_of_colex, binom):
    _G["T"] = T
    _G["cls"] = class_of_colex
    _G["binom"] = binom


def _score(h, o, b, T):
    tv = E.triple_values(b)
    sh = E.score_np(E.pair_values(h), tv, T)
    so = E.score_np(E.pair_values(o), tv, T)
    return (sh > so) + 0.5 * (sh == so)


def _uniform_job(args):
    seed, n_deals, k = args
    g = np.random.default_rng(seed)
    T, cls, binom = _G["T"], _G["cls"], _G["binom"]
    sums = np.zeros(k)
    cnts = np.zeros(k)
    base = np.tile(np.arange(36, dtype=np.int8), (BATCH, 1))
    done = 0
    while done < n_deals:
        deal = g.permuted(base, axis=1)[:, :15]
        h, o, b = deal[:, :5], deal[:, 5:10], deal[:, 10:]
        w = _score(h, o, b, T)
        ch = cls[colex(np.sort(h, axis=1), binom)]
        co = cls[colex(np.sort(o, axis=1), binom)]
        sums += np.bincount(ch, weights=w, minlength=k) + np.bincount(co, weights=1.0 - w, minlength=k)
        cnts += np.bincount(ch, minlength=k) + np.bincount(co, minlength=k)
        done += BATCH
    return sums, cnts


def _topup_job(args):
    seed, reps, need = args  # reps (m,5) representatives, need (m,) samples each
    g = np.random.default_rng(seed)
    T = _G["T"]
    heroes = np.repeat(reps, need, axis=0)
    owner = np.repeat(np.arange(len(reps)), need)
    n = heroes.shape[0]
    sums = np.zeros(len(reps))
    for s in range(0, n, BATCH):
        hh = heroes[s:s + BATCH]
        m = hh.shape[0]
        # random permutation of the 31 remaining cards per row
        keys = g.random((m, 36))
        np.put_along_axis(keys, hh.astype(np.intp), 2.0, axis=1)
        rest = np.argsort(keys, axis=1)[:, :10]
        w = _score(hh, rest[:, :5], rest[:, 5:], T)
        sums += np.bincount(owner[s:s + BATCH], weights=w, minlength=len(reps))
    return sums


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deals", type=float, default=400, help="millions of uniform deals")
    ap.add_argument("--min-samples", type=int, default=40000)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    t0 = time.time()

    T, dense_to_raw = E.build_score_table()
    print(f"score table: {T.size} entries, {len(dense_to_raw) - 1} distinct hand ranks ({time.time() - t0:.1f}s)")

    hands = np.array(list(combinations(range(36), 5)), dtype=np.int8)  # colex order? no: lexicographic
    binom = np.array([[__import__("math").comb(n, k) for k in range(6)] for n in range(37)], dtype=np.int64)
    cidx = colex(hands, binom)
    keys = E.canonical_keys_np(hands)
    class_keys, inv, orbit = np.unique(keys, return_inverse=True, return_counts=True)
    k = class_keys.size
    class_of_colex = np.empty(hands.shape[0], dtype=np.int32)
    class_of_colex[cidx] = inv
    print(f"{hands.shape[0]} hands, {k} suit classes; orbit sizes {dict(zip(*np.unique(orbit, return_counts=True)))}")

    n_total = int(args.deals * 1e6)
    jobs_n = args.workers * 4
    per = int(np.ceil(n_total / jobs_n / BATCH)) * BATCH
    ss = np.random.SeedSequence(args.seed)
    seeds = [int(s.generate_state(1)[0]) for s in ss.spawn(jobs_n + args.workers * 4)]
    with Pool(args.workers, initializer=_init, initargs=(T, class_of_colex, binom)) as pool:
        sums = np.zeros(k)
        cnts = np.zeros(k)
        for s, c in pool.imap_unordered(_uniform_job, [(seeds[i], per, k) for i in range(jobs_n)]):
            sums += s
            cnts += c
        print(f"uniform phase: {per * jobs_n / 1e6:.0f}M deals, {time.time() - t0:.0f}s; "
              f"samples/class min {cnts.min():.0f} median {np.median(cnts):.0f}")

        need = np.maximum(0, args.min_samples - cnts).astype(np.int64)
        todo = np.nonzero(need)[0]
        if todo.size:
            first_hand = np.zeros(k, dtype=np.int64)
            first_hand[inv[::-1]] = np.arange(hands.shape[0])[::-1]
            reps = hands[first_hand[todo]]
            chunks = np.array_split(np.arange(todo.size), args.workers * 4)
            jobs = [(seeds[jobs_n + i], reps[ch], need[todo[ch]]) for i, ch in enumerate(chunks) if ch.size]
            res = pool.map(_topup_job, jobs)
            for ch, r in zip([c for c in chunks if c.size], res):
                sums[todo[ch]] += r
                cnts[todo[ch]] += need[todo[ch]]
            print(f"top-up: {todo.size} classes, {need.sum() / 1e6:.1f}M samples, {time.time() - t0:.0f}s")

    eq = sums / cnts
    # percentile: fraction of all hands with class equity <= this class's equity
    order = np.argsort(eq, kind="stable")
    cum = np.cumsum(orbit[order])
    eq_sorted = eq[order]
    # for ties take the cumulative count up to the last equal entry
    last = np.searchsorted(eq_sorted, eq_sorted, side="right") - 1
    pct_sorted = cum[last] / hands.shape[0]
    pct = np.empty(k)
    pct[order] = pct_sorted

    hand_eq = eq[inv]
    horder = np.argsort(hand_eq, kind="stable")
    hands_by_eq = hands[horder].astype(np.uint8)
    hands_class = inv[horder].astype(np.uint16)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez(OUT, T=T, dense_to_raw=dense_to_raw, class_keys=class_keys.astype(np.int64),
             class_eq=eq.astype(np.float32), class_pct=pct.astype(np.float32),
             class_n=cnts.astype(np.int32), class_orbit=orbit.astype(np.int16),
             hands_by_eq=hands_by_eq, hands_class=hands_class)
    se = np.sqrt(eq * (1 - eq) / cnts)  # conservative-ish (ignores ties)
    print(f"saved {OUT} ({os.path.getsize(OUT) / 1e6:.2f} MB) in {time.time() - t0:.0f}s")
    print(f"equity range {eq.min():.4f} .. {eq.max():.4f}; mean SE {se.mean():.4f}, max SE {se.max():.4f}")


if __name__ == "__main__":
    main()

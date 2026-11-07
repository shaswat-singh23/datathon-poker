"""bot/postflop.py - flop / turn / river decisions.

    postflop_action(obs, memory, budget_ms, rng=None) -> Action

One Monte Carlo equity call (bot.equity.equity) against a range-narrowed
opponent, compared with pot odds:

* Facing a bet: pot_odds = to_call / (pot + to_call) (obs.pot already holds
  every chip committed this hand, both players' current bets included).
  Fold if equity < pot_odds + call_margin, call otherwise, raise half / pot
  at the higher equity thresholds. Each raise already made on this street
  raises the bar for (re)raising by `reraise_step`.
* Checking is free: check back weak hands, bet half pot with good equity,
  bet pot with very strong equity, and (optionally) bluff half pot with a
  small frequency on the turn / river when equity is very low.

Range narrowing (opp_min_pct): the opponent's range is cut to hands whose
preflop percentile >= opp_min_pct. It rises with each opponent raise / bet in
this hand (postflop raises count more than preflop ones) and is scaled down
for opponents who are aggressive in general (they raise wider).

Optional memory keys (never required, safe defaults):
    memory["opp_aggression"]   float 0..1, the opponent's overall raise
                               frequency (e.g. from bot/opponent_model.py).
                               Default PARAMS["default_aggression"].
    memory["postflop_params"]  dict of PARAMS overrides (merged over PARAMS).

Thresholds live in PARAMS so tuning tickets (#12) can adjust them.

Units: budget_ms is a wall-clock budget in MILLISECONDS for this decision,
i.e. what bot/timing.py's budget_ms(memory, obs) returns. Never pass
timing.samples_for() (that is a sample count). Whatever the caller passes, the
Monte Carlo call gets at most PARAMS["max_mc_ms"] (20 ms by default), so a
generous caller cannot push a single decision anywhere near the 100 ms limit.

Randomness: pass a random.Random as `rng` and the whole decision (Monte Carlo
sampling and the bluff coin) follows it. With rng=None a per-decision seed is
derived from the observation (hand index, cards, street, history length), so
the same spot always gets the same action, whatever was decided before it.

The returned action is always in obs.legal_actions (best legal fallback), and
the function never raises: if equity fails or the budget is too small, it
falls back to a made-hand-category estimate. The equity engine is called at
most once per decision with time_budget_ms <= min(budget_ms, max_mc_ms).
"""
from __future__ import annotations

import random

from game import Action

from bot import equity as _eq

PARAMS: dict = {
    # facing a bet
    "call_margin": 0.03,       # call if equity >= pot_odds + call_margin
    "raise_half_eq": 0.72,     # raise half pot at or above this equity
    "raise_pot_eq": 0.82,      # raise pot at or above this equity
    "reraise_step": 0.06,      # each raise already made this street adds this to raise/bet thresholds
    # checked to us / first to act
    "bet_half_eq": 0.62,       # bet half pot at or above this equity
    "bet_pot_eq": 0.78,        # bet pot at or above this equity
    "bluff_freq": 0.10,        # chance to bluff half pot when free and equity is low (turn/river only)
    "bluff_max_eq": 0.20,      # only bluff with equity below this
    # range narrowing
    "pct_per_pre_raise": 0.10,   # opp_min_pct added per opponent preflop raise
    "pct_per_post_raise": 0.15,  # opp_min_pct added per opponent postflop bet/raise
    "max_opp_pct": 0.70,         # cap on opp_min_pct
    "default_aggression": 0.30,  # assumed opponent raise frequency when unknown
    # budget
    "budget_frac": 0.8,        # fraction of budget_ms handed to the equity engine
    "min_budget_ms": 0.25,     # below this (after budget_frac), skip Monte Carlo
    "max_mc_ms": 20.0,         # hard cap on the Monte Carlo budget, whatever the caller passes
}

# made-hand category (evaluator.category_of) -> rough equity, used only when
# Monte Carlo is skipped or fails. Index order follows evaluator.py's Short Deck
# ranking: 0 high card, 1 pair, 2 two pair, 3 STRAIGHT, 4 THREE_OF_A_KIND,
# 5 full house, 6 flush, 7 quads, 8 straight flush. Trips beat a straight and a
# flush beats a full house here, so the values must be non-decreasing in index.
_CAT_EQ = (0.25, 0.45, 0.60, 0.66, 0.70, 0.80, 0.85, 0.92, 0.97)

_RAISES = (Action.RAISE_HALF, Action.RAISE_POT)


def _seed(obs) -> int:
    """Deterministic per-decision seed from the observation (used when rng=None)."""
    try:
        s = int(obs.hand_index) * 1_000_003
        s += sum(int(c) << (3 * i) for i, c in enumerate(obs.hole_cards))
        s += sum(int(c) << (3 * i + 1) for i, c in enumerate(obs.board)) * 7919
        s += int(obs.street) * 104_729 + len(obs.action_history or ()) * 15_485_863
        return s & 0xFFFFFFFF
    except Exception:
        return 0


def _params(memory) -> dict:
    over = memory.get("postflop_params")
    if isinstance(over, dict) and over:
        return {**PARAMS, **over}
    return PARAMS


def _pick(prefs, legal) -> Action:
    """First action in prefs that is legal; then the safest legal one."""
    for a in prefs:
        if a in legal:
            return a
    for a in (Action.CHECK_CALL, Action.FOLD, Action.RAISE_HALF, Action.RAISE_POT):
        if a in legal:
            return a
    return Action.CHECK_CALL  # nothing is legal; the shell handles that case


def opp_min_pct(obs, memory, p=PARAMS) -> float:
    """Range-narrowing percentile from opponent raises in this hand.

    First pass: counts only the opponent's raises, ignoring position and calls
    (an opponent who flat-called a 3-bet is still treated as a random hand).
    #12 (exploitative adjustments) should refine this with the opponent model.
    """
    pre = post = 0
    for h in obs.action_history or ():
        if h.is_me or h.action not in _RAISES:
            continue
        if int(h.street) == 0:
            pre += 1
        else:
            post += 1
    pct = pre * p["pct_per_pre_raise"] + post * p["pct_per_post_raise"]
    try:
        aggr = float(memory.get("opp_aggression", p["default_aggression"]))
    except (TypeError, ValueError):
        aggr = p["default_aggression"]
    if not 0.0 <= aggr <= 1.0:  # also rejects NaN
        aggr = p["default_aggression"]
    # relative to the default: maniacs (aggr -> 1) narrow less, nits up to 1.3x
    scale = min(1.3, max(0.5, 1.0 - (aggr - p["default_aggression"])))
    return float(min(p["max_opp_pct"], max(0.0, pct * scale)))


def _fallback_equity(hole, board) -> float:
    try:
        cat = int(_eq.hand_features(hole, board).get("category", 0))
        return _CAT_EQ[max(0, min(8, cat))]
    except Exception:
        return 0.4


def mc_budget_ms(budget_ms, p=PARAMS) -> float:
    """Milliseconds handed to the equity engine for a decision budget of budget_ms.

    budget_frac of the budget, capped at max_mc_ms; 0.0 (skip Monte Carlo) when
    the result would be below min_budget_ms or the input is not a number.
    """
    try:
        budget_ms = float(budget_ms)
    except (TypeError, ValueError):
        return 0.0
    budget = min(budget_ms * p["budget_frac"], p["max_mc_ms"])
    if not budget >= p["min_budget_ms"]:  # `not >=` also catches NaN
        return 0.0
    return budget


def estimate_equity(obs, memory, budget_ms, p=PARAMS, rng=None) -> float:
    """One Monte Carlo call within min(budget_ms, max_mc_ms), or the category fallback."""
    hole, board = tuple(obs.hole_cards), tuple(obs.board)
    budget = mc_budget_ms(budget_ms, p)
    if budget <= 0.0 or len(board) < 3:
        return _fallback_equity(hole, board)
    if rng is None:
        rng = random.Random(_seed(obs))
    try:
        e = float(_eq.equity(hole, board, opp_min_pct=opp_min_pct(obs, memory, p),
                             time_budget_ms=budget, rng=rng))
        if 0.0 <= e <= 1.0:
            return e
    except Exception:
        pass
    return _fallback_equity(hole, board)


def decide(eq, obs, p=PARAMS, rng=None) -> Action:
    """Pure decision from an equity estimate (no Monte Carlo)."""
    if rng is None:
        rng = random.Random(_seed(obs))
    legal = tuple(obs.legal_actions)
    to_call = max(0, int(obs.to_call))
    step = p["reraise_step"] * max(0, int(obs.raises_this_street))
    if to_call == 0:
        if eq >= p["bet_pot_eq"] + step:
            return _pick((Action.RAISE_POT, Action.RAISE_HALF), legal)
        if eq >= p["bet_half_eq"] + step:
            return _pick((Action.RAISE_HALF, Action.RAISE_POT), legal)
        if (p["bluff_freq"] > 0 and eq < p["bluff_max_eq"] and len(obs.board) >= 4
                and rng.random() < p["bluff_freq"]):
            return _pick((Action.RAISE_HALF, Action.CHECK_CALL), legal)
        return _pick((Action.CHECK_CALL,), legal)
    pot_odds = to_call / float(max(1, int(obs.pot)) + to_call)
    if eq >= p["raise_pot_eq"] + step:
        return _pick((Action.RAISE_POT, Action.RAISE_HALF, Action.CHECK_CALL), legal)
    if eq >= p["raise_half_eq"] + step:
        return _pick((Action.RAISE_HALF, Action.RAISE_POT, Action.CHECK_CALL), legal)
    if eq >= pot_odds + p["call_margin"]:
        return _pick((Action.CHECK_CALL,), legal)
    return _pick((Action.FOLD, Action.CHECK_CALL), legal)


def postflop_action(obs, memory, budget_ms, rng=None) -> Action:
    """Flop/turn/river action; always in obs.legal_actions, never raises."""
    try:
        legal = tuple(obs.legal_actions)
    except Exception:
        return Action.CHECK_CALL
    try:
        if not isinstance(memory, dict):
            memory = {}
        p = _params(memory)
        if not isinstance(rng, random.Random):
            rng = random.Random(_seed(obs) if rng is None else rng)
        a = decide(estimate_equity(obs, memory, budget_ms, p, rng), obs, p, rng)
        return a if a in legal else _pick((), legal)
    except Exception:
        return _pick((Action.CHECK_CALL, Action.FOLD), legal)

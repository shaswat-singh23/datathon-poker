"""bot/preflop.py - preflop decisions for heads-up Short Deck 5-card PLO.

    preflop_action(obs, memory, pct) -> Action

`pct` is bot.equity.preflop_percentile(hole): the fraction of all starting
hands with preflop equity <= ours (0 = worst, 1 = best).

Situations (heads-up: the button posts the small blind and acts first preflop)
------------------------------------------------------------------------------
* first in    button, nobody has raised, to_call = 1: raise / limp / fold
* option      big blind after a limp, to_call = 0: raise / check
* facing a raise, by `raises_this_street` (blinds don't count):
    level 1   facing an open (BB) or an iso-raise after our limp (button)
    level 2   facing a 3-bet
    level 3+  facing a 4-bet or more (level 4 = capped, call or fold only)
  For each level: raise with pct >= raise_<n>, call with pct >= call_<n>, else fold.
* facing all-in, or a call that commits most of our stack: call if Monte Carlo
  equity against the opponent's estimated range beats the pot odds.

Why these numbers
-----------------
Preflop equities in this game are tightly bunched: a median hand has 50% against
a random hand and still about 43% against a top-50% range. Folding preflop
therefore gives up a lot. Most of the edge against student bots comes from
(a) never paying off big preflop raises with the bottom of the range and
(b) building pots with the top ~20-35% of hands, which keep their equity
against the strong ranges that re-raise. So:
  * the button opens a wide range (it has position for the whole hand) and
    folds only the bottom ~20%;
  * calls get cheaper thresholds when the price is low (`cheap_price`):
    a big blind facing a half-pot open needs only 25% equity;
  * each extra raise means a stronger opponent range, so call_<n> and
    raise_<n> rise with the level;
  * all-in calls use real equity against a range (`allin_range`, as an
    opp_min_pct for bot.equity), because pot odds matter more than hand rank
    there: 80-chip stacks mean a jam over an open lays roughly 1.2 : 1.
All values are first guesses, kept in THRESHOLDS so a sweep can tune them.
`memory["preflop_overrides"]` (a dict with the same keys) replaces any of them
for the current half, so the opponent model can tighten or loosen play without
editing this file.
"""
from __future__ import annotations

from game import Action

from bot import equity as _eq

THRESHOLDS: dict = {
    # button, first in
    "open_raise": 0.55,     # raise with the top 45%
    "open_limp": 0.20,      # limp with 20-55%, fold the bottom 20%
    "open_size": Action.RAISE_POT,
    # big blind after a limp
    "iso_raise": 0.70,      # raise with the top 30%, otherwise check for free
    "iso_size": Action.RAISE_POT,
    # facing a raise: level 1 (open / iso), 2 (3-bet), 3 (4-bet or more)
    "call_1": 0.35, "raise_1": 0.82,
    "call_2": 0.55, "raise_2": 0.92,
    "call_3": 0.70, "raise_3": 0.97,
    "reraise_size": Action.RAISE_POT,
    # cheap calls: if to_call / (pot + to_call) <= cheap_price, call_<n> drops by cheap_bonus
    "cheap_price": 0.30,
    "cheap_bonus": 0.15,
    # commitment: a call of at least this fraction of our stack is played as all-in
    "commit_frac": 0.5,
    # all-in calls: opponent range (opp_min_pct) by raise level, and our safety margin
    "allin_range": {0: 0.30, 1: 0.40, 2: 0.55, 3: 0.65, 4: 0.70},
    "allin_margin": 0.02,
    "allin_samples": 1500,   # Monte Carlo samples (~1 ms); skipped when the bank is low
    "allin_min_time": 1.0,   # seconds of time bank needed to run Monte Carlo
    # fallback when Monte Carlo is skipped: call an all-in with pct >= this
    "allin_fallback_pct": 0.75,
}


def _cfg(memory: dict) -> dict:
    over = memory.get("preflop_overrides") if isinstance(memory, dict) else None
    if isinstance(over, dict) and over:
        return {**THRESHOLDS, **over}
    return THRESHOLDS


def _legalize(want: Action, legal) -> Action:
    """Closest legal action to `want`: a raise degrades to the other raise size,
    then to a call; a fold with nothing to call becomes a check."""
    if want in legal:
        return want
    if want in (Action.RAISE_POT, Action.RAISE_HALF):
        other = Action.RAISE_HALF if want == Action.RAISE_POT else Action.RAISE_POT
        for a in (other, Action.CHECK_CALL):
            if a in legal:
                return a
    if want == Action.FOLD and Action.CHECK_CALL in legal:
        return Action.CHECK_CALL
    for a in (Action.CHECK_CALL, Action.FOLD, Action.RAISE_HALF, Action.RAISE_POT):
        if a in legal:
            return a
    return want  # legal is empty: nothing valid exists, the shell will handle it


def _raise_or(want_raise: Action, fallback: Action, legal) -> Action:
    """`want_raise` if any raise is legal, else `fallback` (made legal)."""
    if Action.RAISE_POT in legal or Action.RAISE_HALF in legal:
        return _legalize(want_raise, legal)
    return _legalize(fallback, legal)


def allin_price(obs) -> float:
    """Equity needed to call when the rest of the effective stack goes in.

    R = chips we add from now if both players end up all-in
      = min(my_stack, to_call + opp_stack).
    The final pot is the current pot, minus any part of the opponent's bet we
    can't match (it is returned), plus our R, plus whatever the opponent still
    adds to match R. Price = R / final pot.
    """
    r = min(obs.my_stack, obs.to_call + obs.opp_stack)
    if r <= 0:
        return 0.0
    final_pot = obs.pot - max(0, obs.to_call - r) + r + max(0, r - obs.to_call)
    return r / final_pot if final_pot > 0 else 1.0


def _allin_call(obs, memory: dict, cfg: dict, pct: float, level: int) -> bool:
    """Should we call a bet that commits (or is) our stack?"""
    price = allin_price(obs)
    rng_ranges = cfg["allin_range"]
    opp_min = float(rng_ranges.get(min(level, 4), 0.5)) if isinstance(rng_ranges, dict) else float(rng_ranges)
    time_left = memory.get("_time_left", 99.0) if isinstance(memory, dict) else 99.0
    eq = None
    if time_left >= cfg["allin_min_time"] and len(obs.hole_cards) == 5:
        try:
            seed = (obs.hand_index * 1_000_003 + sum(c << (3 * i) for i, c in enumerate(obs.hole_cards))) & 0xFFFFFFFF
            eq = _eq.equity(obs.hole_cards, [], opp_min_pct=opp_min,
                            n_samples=int(cfg["allin_samples"]), rng=seed)
        except Exception:
            eq = None
    if eq is None:
        return pct >= cfg["allin_fallback_pct"]
    return eq >= price + cfg["allin_margin"]


def preflop_action(obs, memory: dict, pct: float) -> Action:
    """Preflop action for observation `obs`, given our hand's preflop percentile."""
    cfg = _cfg(memory)
    legal = obs.legal_actions
    to_call = obs.to_call
    raises = obs.raises_this_street

    if raises == 0 and to_call > 0:
        # button, first in
        if pct >= cfg["open_raise"]:
            return _raise_or(cfg["open_size"], Action.CHECK_CALL, legal)
        if pct >= cfg["open_limp"]:
            return _legalize(Action.CHECK_CALL, legal)
        return _legalize(Action.FOLD, legal)

    if to_call == 0:
        # big blind option after a limp (or any spot where checking is free)
        thr = cfg["iso_raise"] if raises == 0 else cfg[f"raise_{min(raises, 3)}"]
        if pct >= thr:
            return _raise_or(cfg["iso_size"], Action.CHECK_CALL, legal)
        return _legalize(Action.CHECK_CALL, legal)

    # facing a raise
    level = min(raises, 3)
    can_raise = Action.RAISE_POT in legal or Action.RAISE_HALF in legal
    if pct >= cfg[f"raise_{level}"] and can_raise:
        return _legalize(cfg["reraise_size"], legal)

    allin = obs.opp_stack == 0 or to_call >= obs.my_stack
    if allin or to_call >= cfg["commit_frac"] * obs.my_stack:
        if _allin_call(obs, memory, cfg, pct, raises):
            return _legalize(Action.CHECK_CALL, legal)
        return _legalize(Action.FOLD, legal)

    call_thr = cfg[f"call_{level}"]
    price = to_call / (obs.pot + to_call)
    if price <= cfg["cheap_price"]:
        call_thr -= cfg["cheap_bonus"]
    if pct >= call_thr:
        return _legalize(Action.CHECK_CALL, legal)
    return _legalize(Action.FOLD, legal)

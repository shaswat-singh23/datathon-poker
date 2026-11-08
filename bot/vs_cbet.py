"""bot/vs_cbet.py - tighten postflop value bets and calls against a "c-bet bot" (#82).

    apply(obs, memory) -> bool    observe the opponent; when it looks like a c-bet bot,
                                  merge OVERRIDES into memory["postflop_params"]

A c-bet bot bets (almost) every time it can bet first postflop, never raises over
our bet, and folds to our bets a fair share of the time (tools/opponents/cbetter.py).
Its bets say little, but its calls are strong: it only calls with Monte Carlo equity
above ~0.45, so its river range after calling is far better than the random range
our equity engine assumes. Thin value bets (bet_half_eq 0.52) and light calls then
lose: on 3 x 1000 deals our straights called by it won 0 of 31 hands as the bettor and
35% of 444 hands as the caller (findings/82-cbetter-exploit.md).

The gate is deliberately narrow so the bots we beat hardest by betting thin keep the
default play: maniac / always_half / always_pot raise back, the calling station never
bets, and a never-folding bettor fails the fold test. Per-half state lives in memory
(both halves are fresh processes), so the gate needs ~20 opponent chances to open.

Wiring: one call per decision in bot/policy.py, after exploit.apply (which rewrites
memory["postflop_params"] every hand). Never raises; adds no Monte Carlo work.
"""
from __future__ import annotations

from game import Action

_RAISES = (Action.RAISE_HALF, Action.RAISE_POT)

# gate: opponent chances to bet, and times it faced our bet
MIN_OPPS = 20
MIN_FACED = 8
BET_RATE_MIN = 0.90      # bets / chances to bet first (cbetter: ~1.0)
RERAISE_MAX = 0.05       # raises / replies we saw to our bets (cbetter: 0)
FOLD_MIN = 0.25          # postflop fold_to_bet from the opponent model (cbetter: ~0.4)

# postflop PARAMS replaced while the gate is open (absolute values, like exploit.py).
# Screened on 12 seeds vs cbetter (findings/82-cbetter-exploit.md): 0.76 beat 0.62 / 0.70.
OVERRIDES: dict = {"bet_half_eq": 0.76}

_KEY = "_vs_cbet"


def _fresh() -> dict:
    return {"hand": None, "seen": 0, "street": -1, "raises": 0, "last_me": False,
            "opps": 0, "bets": 0, "replies": 0, "reraises": 0}


def observe(obs, memory) -> dict:
    """Count the opponent's postflop behaviour; each history entry is counted once."""
    st = memory.get(_KEY)
    if not isinstance(st, dict):
        st = memory[_KEY] = _fresh()
    hist = tuple(obs.action_history or ())
    if st["hand"] != obs.hand_index:
        st["hand"], st["seen"], st["street"], st["raises"], st["last_me"] = obs.hand_index, 0, -1, 0, False
    for h in hist[st["seen"]:]:
        street = int(h.street)
        if street == 0:
            continue
        if street != st["street"]:
            st["street"], st["raises"], st["last_me"] = street, 0, False
        if not h.is_me:
            if st["raises"] == 0:                 # nothing to call: it chose to bet or check
                st["opps"] += 1
                st["bets"] += h.action in _RAISES
            elif st["last_me"]:                   # it replied to our bet / raise
                # a fold ends the hand, so we never see one in the history: folds come from the model
                st["replies"] += 1
                st["reraises"] += h.action in _RAISES
        if h.action in _RAISES:
            st["raises"] += 1
            st["last_me"] = bool(h.is_me)
    st["seen"] = len(hist)
    return st


def _postflop_fold(model):
    """(fold_to_bet over the flop, turn and river, samples) from the opponent model."""
    rates = [(float(model.fold_to_bet(s)), int(model.samples("fold_to_bet", s))) for s in (1, 2, 3)]
    n = sum(k for _, k in rates)
    return (sum(r * k for r, k in rates) / n if n else 0.0), n


def is_cbet_bot(st, model) -> bool:
    if model is None or st["opps"] < MIN_OPPS:
        return False
    fold, n_faced = _postflop_fold(model)
    return (n_faced >= MIN_FACED
            and st["bets"] / st["opps"] >= BET_RATE_MIN
            and st["reraises"] <= RERAISE_MAX * st["replies"]
            and fold >= FOLD_MIN)


def apply(obs, memory) -> bool:
    """Observe, then tighten the postflop params if the opponent is a c-bet bot."""
    try:
        if not isinstance(memory, dict):
            return False
        st = observe(obs, memory)
        on = is_cbet_bot(st, memory.get("opp_model"))
        memory["vs_cbet"] = on
        if on:
            p = dict(memory.get("postflop_params") or {})
            p.update(OVERRIDES)
            memory["postflop_params"] = p
        return on
    except Exception:
        return False

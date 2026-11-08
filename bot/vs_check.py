"""bot/vs_check.py - bet half pot when the opponent checks to us postflop (#92).

    adjust(obs, memory, action) -> Action    called on our postflop action

Equity bots (ours included) bet when their equity clears a threshold and check
otherwise; none of them check strong hands to trap. So an opponent's check on
the current street caps its range, and a half-pot bet takes the pot often enough
to profit with any hand. When the opponent has checked to us this street and our
postflop module chose to check, this module bets half pot instead.

Measured with a scratch wrapper before this module existed: +0.93 bb/deal against
a copy of our own bot, +0.4 to +0.8 against tag / honest / exploiter, but -1.49
against the calling station, which never folds. Hence the switch: once the
opponent has faced MIN_FACED of our postflop bets and folds less than FOLD_OFF of
the time (opponent model, shrunk toward its prior), the module turns itself off.

`memory["_vs_check_off"] = True` disables it for a half (used by the sim harness
to play a copy of the bot without this module). Never raises; no Monte Carlo work.
"""
from __future__ import annotations

from game import Action

MIN_FACED = 12     # our postflop bets the opponent must have faced before the switch can act
FOLD_OFF = 0.18    # pooled postflop fold_to_bet below this turns it off (never-folder: 3.2/20 = 0.16 at 12 faced)


PRIOR_FOLD = 0.40  # postflop fold_to_bet prior (opponent_model.PRIOR_FOLD_TO_BET) ...
PRIOR_N = 8.0      # ... worth this many observations (opponent_model.PRIOR_WEIGHT)


def _postflop_fold(model):
    """(fold_to_bet over flop, turn and river pooled, samples) from the opponent model.

    The model shrinks each street toward its prior separately, so a never-folder
    facing 5 bets per street still reads 0.25 there. Pooling the raw counts and
    shrinking once lets the switch act after about MIN_FACED bets in all.
    """
    faced = sum(int(model.faced[s]) for s in (1, 2, 3))
    folds = sum(float(model.fold_f[s]) for s in (1, 2, 3))
    return (folds + PRIOR_N * PRIOR_FOLD) / (faced + PRIOR_N), faced


def enabled(memory) -> bool:
    if not isinstance(memory, dict) or memory.get("_vs_check_off"):
        return False
    model = memory.get("opp_model")
    if model is None:
        return True
    fold, n = _postflop_fold(model)
    return not (n >= MIN_FACED and fold < FOLD_OFF)


def opponent_checked(obs) -> bool:
    """The opponent acted on this street and left nothing to call: it checked."""
    if int(obs.to_call) != 0:
        return False
    street = int(obs.street)
    return any(not h.is_me and int(h.street) == street for h in (obs.action_history or ()))


def opponent_called_our_bet(obs) -> bool:
    """The opponent called one of our postflop bets earlier in this hand.

    A call uncaps its range (a trapper check-calls strong hands, tools/opponents/
    trappy.py), so a later check no longer means weakness: no automatic bet then.
    """
    last_raiser_me = False
    for h in obs.action_history or ():
        if int(h.street) == 0:
            continue
        if h.action in (Action.RAISE_HALF, Action.RAISE_POT):
            last_raiser_me = bool(h.is_me)
        elif not h.is_me and h.action == Action.CHECK_CALL and last_raiser_me:
            return True
        if not h.is_me and h.action == Action.CHECK_CALL:
            last_raiser_me = False
    return False


def adjust(obs, memory, action):
    """Turn our check into a half-pot bet after an opponent check, unless switched off."""
    try:
        if (action == Action.CHECK_CALL and int(obs.street) != 0
                and Action.RAISE_HALF in obs.legal_actions
                and opponent_checked(obs) and not opponent_called_our_bet(obs)
                and enabled(memory)):
            memory["vs_check_bets"] = memory.get("vs_check_bets", 0) + 1
            return Action.RAISE_HALF
    except Exception:
        pass
    return action

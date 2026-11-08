"""Tests for bot/vs_check.py: after an opponent check on the current postflop street,
our check becomes a half-pot bet, unless the opponent has shown it never folds."""
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import policy, vs_check  # noqa: E402
from game import Action, Street  # noqa: E402

CHECK, FOLD, HALF, POT = Action.CHECK_CALL, Action.FOLD, Action.RAISE_HALF, Action.RAISE_POT
ALL = (FOLD, CHECK, HALF, POT)
NO_FOLD = (CHECK, HALF, POT)


class FakeModel:
    """Raw postflop counts like OpponentModel.faced / fold_f, all on the flop."""

    def __init__(self, fold=0.40, n=0):
        self.faced = [0, n, 0, 0]
        self.fold_f = [0, fold * n, 0, 0]


def act(is_me, action, street=Street.FLOP, amount=0):
    return NS(street=street, is_me=is_me, action=action, amount=amount)


def obs(history, street=Street.FLOP, to_call=0, legal=NO_FOLD):
    return NS(street=street, to_call=to_call, legal_actions=legal, action_history=tuple(history))


def opp_checked(street=Street.FLOP):
    return [act(True, CHECK, Street.PREFLOP, 1), act(False, CHECK, Street.PREFLOP), act(False, CHECK, street)]


def test_bets_after_opponent_check():
    assert vs_check.adjust(obs(opp_checked()), {}, CHECK) == HALF


def test_bets_on_turn_and_river_too():
    for st in (Street.TURN, Street.RIVER):
        assert vs_check.adjust(obs(opp_checked(st), street=st), {}, CHECK) == HALF


def test_first_to_act_keeps_check():
    # the opponent acted only preflop: nothing on this street yet, so no check to exploit
    hist = [act(True, CHECK, Street.PREFLOP, 1), act(False, CHECK, Street.PREFLOP)]
    assert vs_check.adjust(obs(hist), {}, CHECK) == CHECK


def test_preflop_untouched():
    hist = [act(False, CHECK, Street.PREFLOP)]
    assert vs_check.adjust(obs(hist, street=Street.PREFLOP), {}, CHECK) == CHECK


def test_facing_a_bet_untouched():
    hist = [act(False, HALF, Street.FLOP, 4)]
    assert vs_check.adjust(obs(hist, to_call=4, legal=ALL), {}, CHECK) == CHECK
    assert vs_check.adjust(obs(hist, to_call=4, legal=ALL), {}, FOLD) == FOLD


def test_other_actions_untouched():
    for a in (HALF, POT):
        assert vs_check.adjust(obs(opp_checked()), {}, a) == a


def test_respects_legal_actions():
    assert vs_check.adjust(obs(opp_checked(), legal=(CHECK, POT)), {}, CHECK) == CHECK


def test_switch_off_vs_station():
    station = {"opp_model": FakeModel(fold=0.0, n=vs_check.MIN_FACED)}
    assert vs_check.adjust(obs(opp_checked()), station, CHECK) == CHECK


def test_stays_on_until_enough_samples():
    early = {"opp_model": FakeModel(fold=0.05, n=vs_check.MIN_FACED - 1)}
    assert vs_check.adjust(obs(opp_checked()), early, CHECK) == HALF


def test_stays_on_vs_folders():
    folder = {"opp_model": FakeModel(fold=0.45, n=100)}
    assert vs_check.adjust(obs(opp_checked()), folder, CHECK) == HALF


def test_memory_flag_disables():
    assert vs_check.adjust(obs(opp_checked()), {"_vs_check_off": True}, CHECK) == CHECK


def test_never_raises():
    assert vs_check.adjust(None, {}, CHECK) == CHECK
    assert vs_check.adjust(obs(opp_checked()), None, CHECK) == CHECK
    broken = {"opp_model": object()}
    assert vs_check.adjust(obs(opp_checked()), broken, CHECK) == CHECK


def test_station_model_turns_off_with_real_opponent_model():
    # the real model's shrunk fold_to_bet for a never-folder drops below FOLD_OFF by MIN_FACED+2
    from bot.opponent_model import OpponentModel
    m = OpponentModel()
    for s in (1, 2, 3):
        m.faced[s] = vs_check.MIN_FACED // 3
    fold, n = vs_check._postflop_fold(m)
    assert n >= vs_check.MIN_FACED and fold < vs_check.FOLD_OFF
    assert not vs_check.enabled({"opp_model": m})


def test_wired_in_policy():
    assert policy.vs_check is vs_check


def test_no_auto_bet_after_opponent_called_our_bet():
    # flop: we bet, it called; turn: it checks to us -> its range is no longer capped
    hist = [act(True, CHECK, Street.PREFLOP, 1), act(False, CHECK, Street.PREFLOP),
            act(False, CHECK, Street.FLOP), act(True, HALF, Street.FLOP, 2), act(False, CHECK, Street.FLOP, 2),
            act(False, CHECK, Street.TURN)]
    assert vs_check.opponent_called_our_bet(obs(hist, street=Street.TURN))
    assert vs_check.adjust(obs(hist, street=Street.TURN), {}, CHECK) == CHECK


def test_its_own_bet_called_by_us_does_not_count():
    # flop: it bet, we called; turn: it checks -> still an auto-bet spot
    hist = [act(True, CHECK, Street.PREFLOP, 1), act(False, CHECK, Street.PREFLOP),
            act(False, HALF, Street.FLOP, 2), act(True, CHECK, Street.FLOP, 2),
            act(False, CHECK, Street.TURN)]
    assert not vs_check.opponent_called_our_bet(obs(hist, street=Street.TURN))
    assert vs_check.adjust(obs(hist, street=Street.TURN), {}, CHECK) == HALF

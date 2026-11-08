"""Tests for bot/vs_cbet.py: the c-bet-bot gate opens only for a bot that bets whenever
it can, never raises back and folds to our bets; everything else keeps default play."""
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import vs_cbet  # noqa: E402
from game import Action, Street  # noqa: E402

BET, CALL = Action.RAISE_HALF, Action.CHECK_CALL


class FakeModel:
    """Fixed postflop fold_to_bet and sample count, like OpponentModel's queries."""

    def __init__(self, fold=0.45, n=100):
        self.fold, self.n = fold, n

    def fold_to_bet(self, street=None):
        return self.fold

    def samples(self, name, street=None):
        assert name == "fold_to_bet"
        return self.n


def act(is_me, action, street=Street.FLOP):
    return NS(street=street, is_me=is_me, action=action, amount=1, street_total=1)


def opp_bets_when_checked_to():   # we check, it bets
    return [act(True, CALL), act(False, BET)]


def we_bet_it_calls():            # we bet, it calls (hand goes on)
    return [act(True, BET), act(False, CALL)]


def we_bet_it_raises():
    return [act(True, BET), act(False, BET)]


def opp_checks_behind():
    return [act(True, CALL), act(False, CALL)]


def run(memory, hands, model="default"):
    """Feed whole hands (lists of history entries) one after the other; returns apply's last result."""
    if model == "default":
        model = FakeModel()
    memory["opp_model"] = model
    on = False
    for i, hist in enumerate(hands):
        on = vs_cbet.apply(NS(hand_index=i, action_history=tuple(hist)), memory)
    return on


def cbetter_like(n=60):
    return [opp_bets_when_checked_to() if i % 2 == 0 else we_bet_it_calls() for i in range(n)]


def test_opens_for_a_cbet_bot_and_keeps_other_params():
    mem = {"postflop_params": {"call_margin": 0.05}}
    assert run(mem, cbetter_like()) is True
    assert mem["vs_cbet"] is True
    assert mem["postflop_params"]["bet_half_eq"] == vs_cbet.OVERRIDES["bet_half_eq"]
    assert mem["postflop_params"]["call_margin"] == 0.05   # exploit's values survive


def test_closed_before_enough_chances():
    mem = {}
    assert run(mem, cbetter_like(10)) is False             # 5 chances < MIN_OPPS
    assert "postflop_params" not in mem


def test_closed_without_fold_evidence():
    assert run({}, cbetter_like(), FakeModel(fold=0.45, n=2)) is False   # 3 streets x 2 = 6 folds-chances < MIN_FACED
    assert run({}, cbetter_like(), FakeModel(fold=0.05, n=100)) is False  # a bettor who never folds
    assert run({}, cbetter_like(), model=None) is False                   # model disabled


def test_closed_for_a_maniac_who_raises_back():
    hands = [opp_bets_when_checked_to() if i % 2 == 0 else we_bet_it_raises() for i in range(60)]
    assert run({}, hands, FakeModel(fold=0.05)) is False
    # even if its folds look fine, raising back on a third of replies keeps the gate shut
    hands = [opp_bets_when_checked_to() if i % 2 == 0 else (we_bet_it_raises() if i % 6 == 1 else we_bet_it_calls())
             for i in range(60)]
    assert run({}, hands) is False


def test_closed_for_a_bot_that_checks_behind():
    hands = [opp_bets_when_checked_to() if i % 4 else opp_checks_behind() for i in range(60)]  # bets 75%
    assert run({}, hands) is False


def test_closed_for_a_calling_station():
    assert run({}, [we_bet_it_calls() for _ in range(40)]) is False


def test_each_history_entry_counted_once():
    mem = {"opp_model": FakeModel()}
    hist = tuple(opp_bets_when_checked_to())
    for _ in range(5):
        vs_cbet.apply(NS(hand_index=0, action_history=hist), mem)
    assert (mem["_vs_cbet"]["opps"], mem["_vs_cbet"]["bets"]) == (1, 1)
    vs_cbet.apply(NS(hand_index=0, action_history=hist + (act(True, CALL), act(False, BET, Street.TURN))), mem)
    assert (mem["_vs_cbet"]["opps"], mem["_vs_cbet"]["bets"]) == (2, 2)   # new street, new chance


def test_preflop_actions_are_ignored():
    mem = {"opp_model": FakeModel()}
    hist = tuple(act(False, BET, Street.PREFLOP) for _ in range(5))
    vs_cbet.apply(NS(hand_index=0, action_history=hist), mem)
    assert mem["_vs_cbet"]["opps"] == 0


def test_never_raises_on_garbage():
    for mem in (None, {}, {"opp_model": object()}, {"_vs_cbet": "junk", "opp_model": FakeModel()}):
        assert vs_cbet.apply(NS(hand_index=0, action_history=None), mem) is False
        assert vs_cbet.apply(object(), mem) is False

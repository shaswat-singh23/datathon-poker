"""Tests for bot/opponent_model.py.

Two kinds of check: exact counts on hand-built histories (so each inference
is pinned down), and whole halves against the maniac and nit sparring bots
driven through the real game engine (so the stats are correctly ordered on
realistic play).
"""
import importlib.util
import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bot.opponent_model import PRIOR_WEIGHT, PRIOR_VPIP, OpponentModel  # noqa: E402
from evaluator import cards_from_str, category_of, omaha_score  # noqa: E402
from game import Action, AgentConfig, Game, ObservedAction, Street, make_deal  # noqa: E402

FOLD, CALL, HALF, POT = Action.FOLD, Action.CHECK_CALL, Action.RAISE_HALF, Action.RAISE_POT


def act(street, is_me, action, amount, total=None):
    return ObservedAction(street=street, is_me=is_me, action=action, amount=amount,
                          street_total=amount if total is None else total)


def obs(hand_index, street, history):
    return SimpleNamespace(hand_index=hand_index, street=street, action_history=tuple(history))


def result(hand_index, my_net, winner, showdown=False, board=(), opp_hole=None, pot=10):
    return SimpleNamespace(hand_index=hand_index, my_net=my_net, pot=pot, went_to_showdown=showdown,
                           board=tuple(board), opp_hole=opp_hole, winner=winner)


# ----------------------------------------------------------------- exact counts

def test_priors_before_any_data():
    m = OpponentModel()
    assert m.vpip() == pytest.approx(PRIOR_VPIP)
    assert m.samples("vpip") == 0
    s = m.summary()
    assert s["hands"] == 0 and s["aggression"] == [0.45, 0.4, 0.35, 0.3]


def test_opp_raises_then_folds_to_our_turn_bet():
    """Opp (SB) pot-raises preflop, bets flop, checks turn, folds to our turn bet.

    The fold happens after our last decision so it is never in the history; it
    must be inferred from the result."""
    m = OpponentModel()
    h = [act(Street.PREFLOP, False, POT, 6, 7)]
    m.observe_action(obs(0, Street.PREFLOP, h))           # our preflop decision
    h += [act(Street.PREFLOP, True, CALL, 5, 7), act(Street.FLOP, False, HALF, 7)]
    m.observe_action(obs(0, Street.FLOP, h))              # our flop decision
    h += [act(Street.FLOP, True, CALL, 7), act(Street.TURN, False, CALL, 0)]
    m.observe_action(obs(0, Street.TURN, h))              # our turn decision: we bet
    m.observe_my_action(obs(0, Street.TURN, h), HALF)
    m.observe_result(result(0, +14, "me"))
    assert (m.pf_opp, m.vpip_n, m.pfr_n) == (1, 1, 1)
    assert m.raise_c == [1, 1, 0, 0] and m.check_c == [0, 0, 1, 0]
    assert m.fold_c == [0, 0, 1, 0]
    assert m.faced == [0, 0, 1, 0] and m.fold_f == [0, 0, 1, 0]
    assert m.hands == 1 and m.showdowns == 0 and m.opp_net == -14


def test_three_bet_and_facing_counts():
    """We raise preflop, opp 3-bets, we call; flop we bet, opp calls (visible)."""
    m = OpponentModel()
    h = []
    m.observe_action(obs(1, Street.PREFLOP, h))           # we open
    h += [act(Street.PREFLOP, True, POT, 5, 6), act(Street.PREFLOP, False, POT, 16, 18)]
    m.observe_action(obs(1, Street.PREFLOP, h))           # facing the 3-bet
    h += [act(Street.PREFLOP, True, CALL, 12, 18)]
    m.observe_action(obs(1, Street.FLOP, h))              # we bet the flop
    h += [act(Street.FLOP, True, HALF, 18), act(Street.FLOP, False, CALL, 18)]
    m.observe_action(obs(1, Street.TURN, h))
    assert (m.tb_opp, m.tb_n) == (1, 1)
    assert m.faced == [1, 1, 0, 0] and m.raise_f == [1, 0, 0, 0] and m.call_f == [0, 1, 0, 0]
    assert m.vpip_n == 1 and m.pfr_n == 1


def test_small_blind_fold_first_in_without_any_obs():
    m = OpponentModel()
    m.observe_result(result(2, +1, "me"))
    assert m.pf_opp == 1 and m.vpip_n == 0 and m.fold_c == [1, 0, 0, 0]
    assert m.faced == [0, 0, 0, 0]           # folding to the blind is not facing a bet
    assert m.hands == 1


def test_showdown_credits_invisible_river_call_and_category():
    m = OpponentModel()
    board = cards_from_str("6c 7d 9h Js Kc")
    opp_hole = cards_from_str("Ad Ah 8c 8d Qd")
    expected = category_of(omaha_score(opp_hole, board))
    h = [act(Street.RIVER, False, CALL, 0)]
    m.observe_action(obs(3, Street.RIVER, h))
    m.observe_my_action(obs(3, Street.RIVER, h), HALF)   # we bet the river
    m.observe_result(result(3, +10, "me", showdown=True, board=board, opp_hole=opp_hole))
    assert m.showdowns == 1 and m.sd_won_x2 == 0
    assert m.call_c[3] == 1 and m.faced[3] == 1 and m.call_f[3] == 1
    assert sum(m.sd_cat_hist) == 1
    assert m.sd_cat_hist[expected] == 1
    assert m.wtsd() > OpponentModel().wtsd()


def test_our_check_does_not_infer_a_fold():
    """Engine quirk guard: if we checked last and still 'won' without showdown,
    don't invent an opponent fold."""
    m = OpponentModel()
    h = [act(Street.RIVER, False, CALL, 0)]
    m.observe_action(obs(4, Street.RIVER, h))
    m.observe_my_action(obs(4, Street.RIVER, h), CALL)
    m.observe_result(result(4, +3, "me"))
    assert m.fold_c == [0, 0, 0, 0]


def test_history_is_read_incrementally():
    """Calling observe_action twice with the same history must not double count."""
    m = OpponentModel()
    h = [act(Street.PREFLOP, False, POT, 6, 7)]
    m.observe_action(obs(5, Street.PREFLOP, h))
    m.observe_action(obs(5, Street.PREFLOP, h))
    assert m.raise_c[0] == 1 and m.pf_opp == 1


def test_json_round_trip_and_attach():
    m = OpponentModel()
    h = [act(Street.PREFLOP, False, POT, 6, 7)]
    m.observe_action(obs(6, Street.PREFLOP, h))
    m.observe_result(result(6, -7, "opp"))
    blob = json.dumps(m.to_dict())
    m2 = OpponentModel.from_dict(json.loads(blob))
    assert m2.summary() == m.summary()
    memory = {"opp_model": json.loads(blob)}
    m3 = OpponentModel.attach(memory)
    assert isinstance(memory["opp_model"], OpponentModel) and m3.summary() == m.summary()
    assert OpponentModel.attach(memory) is m3


def test_does_not_import_equity():
    src = open(os.path.join(ROOT, "bot", "opponent_model.py")).read()
    assert "equity" not in [line for line in src.splitlines() if line.startswith(("import", "from"))].__str__()
    code = ("import sys; sys.path.insert(0, %r); import bot.opponent_model; "
            "print('bot.equity' in sys.modules)" % ROOT)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# ------------------------------------------------------------------- timing

def test_update_cost_under_20us():
    m = OpponentModel()
    n_hands, per_hand = 2000, 6
    t_act = 0.0
    t_res = 0.0
    for hand in range(n_hands):
        h = []
        for k in range(per_hand):
            is_me = bool(k % 2)
            st = Street(min(k // 2, 3))
            h.append(act(st, is_me, HALF if k % 3 else CALL, 4, 4))
            o = obs(hand, st, h)
            t0 = time.perf_counter()
            m.observe_action(o)
            t_act += time.perf_counter() - t0
        r = result(hand, -3, "opp")
        t0 = time.perf_counter()
        m.observe_result(r)
        t_res += time.perf_counter() - t0
    mean_act_us = 1e6 * t_act / (n_hands * per_hand)
    mean_res_us = 1e6 * t_res / n_hands
    print(f"\nobserve_action {mean_act_us:.2f} us, observe_result {mean_res_us:.2f} us per call")
    assert mean_act_us < 20 and mean_res_us < 20


# ---------------------------------------------------------- real opponents

def _load_bot(name):
    path = os.path.join(ROOT, "tools", "opponents", f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"opp_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _our_probe_policy(o):
    """Open-raise preflop, bet the flop once, then check/call: provokes folds
    from tight bots and showdowns from loose ones."""
    if o.street == Street.PREFLOP and o.raises_this_street == 0 and POT in o.legal_actions:
        return POT
    if o.street == Street.FLOP and o.raises_this_street == 0 and HALF in o.legal_actions:
        return HALF
    return CALL if CALL in o.legal_actions else o.legal_actions[0]


def _play_half(bot_name, deals=300, seed="opp-model-test"):
    bot = _load_bot(bot_name)
    me, opp = 0, 1
    model = OpponentModel()
    bot_mem = {}
    bot.new_half(AgentConfig(), bot_mem)
    for i in range(deals):
        game = Game(make_deal(seed, i), button_seat=i % 2, hand_index=i)
        while game.to_act is not None:
            seat = game.to_act
            o = game.observation(seat)
            if seat == me:
                model.observe_action(o)
                a = _our_probe_policy(o)
                model.observe_my_action(o, a)
            else:
                a = bot.choose_action(o, bot_mem)
                if a not in o.legal_actions:
                    a = CALL if CALL in o.legal_actions else FOLD
            game.apply(a)
        model.observe_result(game.hand_result(me))
        bot.on_hand_end(game.hand_result(opp), bot_mem)
    assert model.hands == deals
    return model


@pytest.fixture(scope="module")
def maniac_and_nit():
    return _play_half("maniac"), _play_half("nit")


def test_maniac_vs_nit_are_ordered(maniac_and_nit):
    maniac, nit = maniac_and_nit
    print("\nmaniac", maniac.summary(), "\nnit   ", nit.summary())
    assert maniac.vpip() > 0.9 > 0.6 > nit.vpip()
    assert maniac.pfr() > 0.8 > nit.pfr() + 0.3
    for s in (Street.PREFLOP, Street.FLOP):
        assert maniac.aggression(s) > nit.aggression(s) + 0.3
    assert maniac.fold_to_bet() < 0.1 < 0.5 < nit.fold_to_bet()
    assert maniac.wtsd() > nit.wtsd() + 0.2
    assert nit.showdown_strength() > maniac.showdown_strength()
    assert maniac.samples("vpip") >= 250 and nit.samples("fold_to_bet") >= 30


def test_stats_converge_past_the_prior(maniac_and_nit):
    maniac, _ = maniac_and_nit
    # With ~300 hands the prior weight of 8 moves vpip by under 3 points.
    raw = maniac.vpip_n / maniac.pf_opp
    assert abs(maniac.vpip() - raw) < 8 / (maniac.pf_opp + PRIOR_WEIGHT)

"""Tests for bot/pressure.py (#68): legality, EV logic, fallbacks, off switch."""
import dataclasses
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import equity as E  # noqa: E402
from bot import opponent_model as OM  # noqa: E402
from bot import postflop as P  # noqa: E402
from bot import pressure as PR  # noqa: E402
from game import Action, Deal, Game, Street  # noqa: E402

from tests.test_postflop import _random_postflop_obs  # noqa: E402


class _Model:
    """Stub opponent model with fixed rates."""

    def __init__(self, fold=0.5, raise_=0.1, n=100):
        self.f, self.r, self.n = fold, raise_, n

    def fold_to_bet(self, street=None):
        return self.f

    def raise_vs_bet(self, street=None):
        return self.r

    def samples(self, name, street=None):
        return self.n


@pytest.fixture
def fixed_eq(monkeypatch):
    box = {"eq": 0.35}
    monkeypatch.setattr(E, "equity", lambda *a, **k: box["eq"])
    return box


def _check_spot(rng):
    """A postflop observation where it is checked to us and a half-pot bet is legal."""
    while True:
        obs = _random_postflop_obs(rng)
        if obs.to_call == 0 and Action.RAISE_HALF in obs.legal_actions:
            return obs


def test_ev_gain_station_vs_folder():
    p = PR.PARAMS
    # eq 0.35, pot 10, bet 5: a 55% folder makes the bet clearly profitable
    assert PR.bet_ev_gain(0.35, 10, 5, 0.55, 0.10, p) > p["margin"] * 10
    # a 10% folder makes it a losing bet
    assert PR.bet_ev_gain(0.35, 10, 5, 0.10, 0.10, p) < 0
    # a strong hand gains from betting regardless (value); weak hand vs station loses
    assert PR.bet_ev_gain(0.80, 10, 5, 0.10, 0.10, p) > 0
    assert PR.bet_ev_gain(0.10, 10, 5, 0.10, 0.10, p) < 0


def test_bets_into_folder_checks_vs_station(fixed_eq):
    rng = random.Random(68)
    obs = _check_spot(rng)
    fixed_eq["eq"] = 0.35
    folder = {"opp_model": _Model(fold=0.6)}
    station = {"opp_model": _Model(fold=0.05)}
    assert PR.postflop_action(obs, folder, 5.0) in (Action.RAISE_HALF, Action.RAISE_POT)
    assert PR.postflop_action(obs, station, 5.0) == Action.CHECK_CALL
    assert folder.get("_pressure_bets") == 1


def test_off_switch_and_no_model_match_postflop(fixed_eq):
    rng = random.Random(1)
    for _ in range(50):
        obs = _random_postflop_obs(rng)
        fixed_eq["eq"] = rng.random()
        base = P.postflop_action(obs, {}, 5.0)
        assert PR.postflop_action(obs, {}, 5.0) == base                      # no model: identical
        off = {"opp_model": _Model(fold=0.9), "pressure_params": {"enabled": 0}}
        assert PR.postflop_action(obs, off, 5.0) == base                     # disabled: identical


def test_never_overrides_bets_calls_or_folds(fixed_eq):
    rng = random.Random(2)
    mem = {"opp_model": _Model(fold=0.9, raise_=0.0)}
    for _ in range(200):
        obs = _random_postflop_obs(rng, facing_bet=rng.random() < 0.5)
        fixed_eq["eq"] = rng.random()
        base = P.postflop_action(obs, mem, 5.0)
        got = PR.postflop_action(obs, mem, 5.0)
        if base != Action.CHECK_CALL or obs.to_call > 0:
            assert got == base
        assert got in obs.legal_actions


def test_min_street_and_min_fold(fixed_eq):
    rng = random.Random(3)
    fixed_eq["eq"] = 0.35
    for _ in range(100):
        obs = _check_spot(rng)
        mem = {"opp_model": _Model(fold=0.6), "pressure_params": {"min_street": 3}}
        a = PR.postflop_action(obs, mem, 5.0)
        if obs.street != Street.RIVER:
            assert a == Action.CHECK_CALL
        mem = {"opp_model": _Model(fold=0.2)}
        assert PR.postflop_action(obs, mem, 5.0) == Action.CHECK_CALL


def test_real_model_and_broken_model_never_raise(fixed_eq, monkeypatch):
    rng = random.Random(4)
    real = {"opp_model": OM.OpponentModel()}
    for _ in range(50):
        obs = _random_postflop_obs(rng)
        fixed_eq["eq"] = rng.random()
        assert PR.postflop_action(obs, real, 5.0) in obs.legal_actions

    class Broken:
        def fold_to_bet(self, s=None):
            raise RuntimeError("boom")

    for _ in range(50):
        obs = _random_postflop_obs(rng)
        a = PR.postflop_action(obs, {"opp_model": Broken()}, 5.0)
        assert a in obs.legal_actions
        assert a == P.postflop_action(obs, {}, 5.0)
    # garbage memory and budget
    obs = _random_postflop_obs(rng)
    assert PR.postflop_action(obs, None, "x") in obs.legal_actions
    assert PR.postflop_action(obs, {"opp_model": 42}, float("nan")) in obs.legal_actions


def test_env_override(monkeypatch):
    monkeypatch.setattr(PR, "_ENV", None)
    monkeypatch.setenv("PRESSURE", "called_shift=0.5,margin=0.1,bogus")
    p = PR.params({})
    assert p["called_shift"] == 0.5 and p["margin"] == 0.1 and p["enabled"] == 1
    monkeypatch.setattr(PR, "_ENV", None)
    monkeypatch.setenv("PRESSURE", "off")
    assert PR.params({})["enabled"] == 0
    monkeypatch.setattr(PR, "_ENV", None)
    monkeypatch.delenv("PRESSURE")
    assert PR.params({}) == PR.PARAMS

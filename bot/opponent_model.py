"""bot/opponent_model.py - the opponent's tendencies within one half.

Everything is learned from what the engine lets us see: ``obs.action_history``
on our turns (``observe_action``) and the ``HandResult`` at the end of each
hand (``observe_result``). Nothing carries over between halves; the model
lives in ``memory`` (see ``OpponentModel.attach``) and is JSON-serialisable
through ``to_dict`` / ``from_dict``.

Stats tracked (opponent only)
-----------------------------
vpip            hands where the opponent voluntarily put chips in preflop
                (limp, call or raise), over hands where they had a preflop
                decision. A big-blind check is not VPIP.
pfr             hands with an opponent preflop raise, same denominator.
three_bet       opponent raised when facing our preflop raise, over hands
                where they faced one.
aggression(s)   on street s: raises / (raises + calls + checks).
fold_to_bet(s)  on street s: folds / actions taken while facing our bet or
                raise. ``call_vs_bet`` and ``raise_vs_bet`` split the rest.
wtsd            hands that reached showdown, over hands finished.
won_at_showdown opponent's share of showdown pots (a split counts half).
showdown_strength
                mean evaluator category (0 high card .. 8 straight flush) of
                the hands the opponent showed down.

What we cannot see
------------------
Our own final action of a hand is never in ``action_history`` and neither is
anything the opponent does after it. Two inferences fill the gap:

* If a hand ends without showdown, we won, and we saw no opponent fold, the
  opponent folded to our last action. A fold is only legal facing a bet, so
  that action was a raise: it counts as a fold facing a bet on the street of
  our last decision. If we never acted in the hand, the opponent folded the
  small blind first-in preflop (a preflop decision, not facing a bet).
* The opponent's final check or call before a showdown is invisible unless the
  policy tells us what we did: call ``observe_my_action(obs, action)`` after
  choosing, and that last check/call is credited on the river. Without it,
  the call is skipped (aggression on the river is then slightly overstated).

Priors
------
Every rate is shrunk toward a heads-up default with ``PRIOR_WEIGHT`` pseudo-
observations::

    rate = (k + PRIOR_WEIGHT * p0) / (n + PRIOR_WEIGHT)

which is the posterior mean of a Beta(PRIOR_WEIGHT * p0, PRIOR_WEIGHT * (1 -
p0)) prior after n trials with k successes. With no data every query returns
its prior; after about 25 observations the data dominates. ``samples(name)``
gives n so a caller can decide how much to trust a rate.

This module imports only ``game`` and ``evaluator``; never ``bot.equity``.
"""
from __future__ import annotations

from typing import Any, Optional

from evaluator import category_of, omaha_score

PRIOR_WEIGHT = 8.0

# Heads-up defaults for a typical unknown bot.
PRIOR_VPIP = 0.65
PRIOR_PFR = 0.40
PRIOR_THREE_BET = 0.15
PRIOR_AGGRESSION = (0.45, 0.40, 0.35, 0.30)      # by street
PRIOR_FOLD_TO_BET = (0.30, 0.40, 0.40, 0.40)     # by street
PRIOR_WTSD = 0.30
PRIOR_WON_AT_SHOWDOWN = 0.50
PRIOR_SHOWDOWN_CATEGORY = 1.6                    # between one pair and two pair

_FOLD, _CHECK_CALL = 0, 1                         # game.Action values
_NUM_STREETS = 4
_NUM_CATEGORIES = 9

_COUNTER_FIELDS = (
    "hands", "pf_opp", "vpip_n", "pfr_n", "tb_opp", "tb_n",
    "showdowns", "sd_won_x2", "sd_cat_sum", "opp_net",
)
_STREET_FIELDS = ("raise_c", "call_c", "check_c", "fold_c", "faced", "fold_f", "call_f", "raise_f")


def _shrink(k: float, n: float, p0: float, m: float = PRIOR_WEIGHT) -> float:
    return (k + m * p0) / (n + m)


class OpponentModel:
    """Opponent tendencies for one half. See the module docstring."""

    __slots__ = tuple(_COUNTER_FIELDS) + tuple(_STREET_FIELDS) + (
        "sd_cat_hist",
        # per-hand transient state
        "cur_hand", "seen", "acted", "pf_opp_flag", "vpip_flag", "pfr_flag",
        "tb_opp_flag", "tb_flag", "opp_folded", "prev_is_me", "prev_action",
        "prev_street", "last_street", "my_last_action", "my_last_street",
    )

    def __init__(self) -> None:
        for name in _COUNTER_FIELDS:
            setattr(self, name, 0)
        for name in _STREET_FIELDS:
            setattr(self, name, [0] * _NUM_STREETS)
        self.sd_cat_hist = [0] * _NUM_CATEGORIES
        self.cur_hand: Optional[int] = None
        self._start_hand(None)

    # ------------------------------------------------------------------ memory
    @classmethod
    def attach(cls, memory: dict, key: str = "opp_model") -> "OpponentModel":
        """Return the model stored in memory under key, creating it if absent.

        Accepts a dict (from ``to_dict``) already stored there and upgrades it.
        """
        obj = memory.get(key)
        if isinstance(obj, cls):
            return obj
        model = cls.from_dict(obj) if isinstance(obj, dict) else cls()
        memory[key] = model
        return model

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {name: getattr(self, name) for name in _COUNTER_FIELDS}
        for name in _STREET_FIELDS:
            d[name] = list(getattr(self, name))
        d["sd_cat_hist"] = list(self.sd_cat_hist)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OpponentModel":
        m = cls()
        for name in _COUNTER_FIELDS:
            setattr(m, name, d.get(name, 0))
        for name in _STREET_FIELDS:
            vals = list(d.get(name, [0] * _NUM_STREETS))
            setattr(m, name, (vals + [0] * _NUM_STREETS)[:_NUM_STREETS])
        hist = list(d.get("sd_cat_hist", [0] * _NUM_CATEGORIES))
        m.sd_cat_hist = (hist + [0] * _NUM_CATEGORIES)[:_NUM_CATEGORIES]
        return m

    # ----------------------------------------------------------------- updates
    def _start_hand(self, hand_index: Optional[int]) -> None:
        self.cur_hand = hand_index
        self.seen = 0
        self.acted = False
        self.pf_opp_flag = False
        self.vpip_flag = False
        self.pfr_flag = False
        self.tb_opp_flag = False
        self.tb_flag = False
        self.opp_folded = False
        self.prev_is_me = False
        self.prev_action = -1
        self.prev_street = -1
        self.last_street = 0
        self.my_last_action = -1
        self.my_last_street = -1

    def observe_action(self, obs: Any) -> None:
        """Call on every one of our turns. Reads only new history entries."""
        if obs.hand_index != self.cur_hand:
            self._start_hand(obs.hand_index)
        self.acted = True
        self.last_street = int(obs.street)
        hist = obs.action_history
        n = len(hist)
        if n > self.seen:
            for a in hist[self.seen:]:
                self._ingest(int(a.street), bool(a.is_me), int(a.action), a.amount)
            self.seen = n

    def observe_my_action(self, obs: Any, action: Any) -> None:
        """Optional: tell the model what we chose, so the opponent's invisible
        final check/call before a showdown can be credited."""
        if obs.hand_index != self.cur_hand:
            self._start_hand(obs.hand_index)
            self.acted = True
        self.my_last_action = int(action)
        self.my_last_street = int(obs.street)

    def _ingest(self, st: int, is_me: bool, act: int, amount: int) -> None:
        if is_me:
            self.prev_is_me = True
            self.prev_action = act
            self.prev_street = st
            return
        facing = self.prev_is_me and self.prev_action >= 2 and self.prev_street == st
        if st == 0:
            if not self.pf_opp_flag:
                self.pf_opp_flag = True
                self.pf_opp += 1
            if act >= 2 or (act == _CHECK_CALL and amount > 0):
                if not self.vpip_flag:
                    self.vpip_flag = True
                    self.vpip_n += 1
            if act >= 2 and not self.pfr_flag:
                self.pfr_flag = True
                self.pfr_n += 1
            if facing and not self.tb_opp_flag:
                self.tb_opp_flag = True
                self.tb_opp += 1
                if act >= 2:
                    self.tb_n += 1
        if act == _FOLD:
            self.fold_c[st] += 1
            self.opp_folded = True
        elif act == _CHECK_CALL:
            if amount > 0:
                self.call_c[st] += 1
            else:
                self.check_c[st] += 1
        else:
            self.raise_c[st] += 1
        if facing:
            self.faced[st] += 1
            if act == _FOLD:
                self.fold_f[st] += 1
            elif act == _CHECK_CALL:
                self.call_f[st] += 1
            else:
                self.raise_f[st] += 1
        self.prev_is_me = False
        self.prev_action = act
        self.prev_street = st

    def observe_result(self, result: Any) -> None:
        """Call once per finished hand (from on_hand_end)."""
        if result.hand_index != self.cur_hand:
            self._start_hand(result.hand_index)   # a hand we never acted in
        self.hands += 1
        self.opp_net -= result.my_net
        if not result.went_to_showdown:
            if result.winner == "me" and not self.opp_folded:
                if self.acted:
                    st = self.last_street
                    if self.my_last_street == st and self.my_last_action >= 0 and self.my_last_action < 2:
                        # We checked/called last; the opponent cannot have folded
                        # to that. Unusual (engine quirk); skip the inference.
                        pass
                    else:
                        self.fold_c[st] += 1
                        self.faced[st] += 1
                        self.fold_f[st] += 1
                        if st == 0 and not self.pf_opp_flag:
                            self.pf_opp += 1
                else:
                    # Small blind folded first-in before we ever acted.
                    self.fold_c[0] += 1
                    self.pf_opp += 1
        else:
            self.showdowns += 1
            if result.winner == "opp":
                self.sd_won_x2 += 2
            elif result.winner == "split":
                self.sd_won_x2 += 1
            if self.my_last_action >= 0 and self.my_last_street == 3:
                # Their last river action was the reply to ours (invisible to us).
                if self.my_last_action >= 2:
                    self.call_c[3] += 1
                    self.faced[3] += 1
                    self.call_f[3] += 1
                elif not self.prev_is_me or self.prev_street != 3:
                    # We checked and the street ended, so they checked behind
                    # (only if their check isn't already in the history).
                    self.check_c[3] += 1
            opp_hole = result.opp_hole
            board = result.board
            if opp_hole is not None and len(opp_hole) == 5 and len(board) == 5:
                cat = category_of(omaha_score(opp_hole, board))
                self.sd_cat_sum += cat
                self.sd_cat_hist[cat] += 1
        self._start_hand(None)

    # ----------------------------------------------------------------- queries
    def vpip(self) -> float:
        return _shrink(self.vpip_n, self.pf_opp, PRIOR_VPIP)

    def pfr(self) -> float:
        return _shrink(self.pfr_n, self.pf_opp, PRIOR_PFR)

    def three_bet(self) -> float:
        return _shrink(self.tb_n, self.tb_opp, PRIOR_THREE_BET)

    def aggression(self, street: int) -> float:
        s = int(street)
        n = self.raise_c[s] + self.call_c[s] + self.check_c[s]
        return _shrink(self.raise_c[s], n, PRIOR_AGGRESSION[s])

    def _facing(self, street: Optional[int]):
        if street is None:
            return (sum(self.faced), sum(self.fold_f), sum(self.call_f), sum(self.raise_f),
                    sum(PRIOR_FOLD_TO_BET) / _NUM_STREETS)
        s = int(street)
        return self.faced[s], self.fold_f[s], self.call_f[s], self.raise_f[s], PRIOR_FOLD_TO_BET[s]

    def fold_to_bet(self, street: Optional[int] = None) -> float:
        n, f, _c, _r, p0 = self._facing(street)
        return _shrink(f, n, p0)

    def call_vs_bet(self, street: Optional[int] = None) -> float:
        n, _f, c, _r, p0 = self._facing(street)
        return _shrink(c, n, (1.0 - p0) * 0.75)

    def raise_vs_bet(self, street: Optional[int] = None) -> float:
        n, _f, _c, r, p0 = self._facing(street)
        return _shrink(r, n, (1.0 - p0) * 0.25)

    def wtsd(self) -> float:
        return _shrink(self.showdowns, self.hands, PRIOR_WTSD)

    def won_at_showdown(self) -> float:
        return _shrink(self.sd_won_x2 / 2.0, self.showdowns, PRIOR_WON_AT_SHOWDOWN)

    def showdown_strength(self) -> float:
        """Mean evaluator category of shown-down hands, shrunk toward the prior."""
        n = sum(self.sd_cat_hist)
        return (self.sd_cat_sum + PRIOR_WEIGHT * PRIOR_SHOWDOWN_CATEGORY) / (n + PRIOR_WEIGHT)

    def samples(self, name: str, street: Optional[int] = None) -> int:
        """How many real observations back a rate (0 means pure prior)."""
        if name in ("vpip", "pfr"):
            return self.pf_opp
        if name == "three_bet":
            return self.tb_opp
        if name == "aggression":
            s = int(street or 0)
            return self.raise_c[s] + self.call_c[s] + self.check_c[s]
        if name in ("fold_to_bet", "call_vs_bet", "raise_vs_bet"):
            return sum(self.faced) if street is None else self.faced[int(street)]
        if name == "wtsd":
            return self.hands
        if name in ("won_at_showdown", "showdown_strength"):
            return self.showdowns
        raise KeyError(name)

    def summary(self) -> dict[str, Any]:
        return {
            "hands": self.hands,
            "vpip": round(self.vpip(), 3),
            "pfr": round(self.pfr(), 3),
            "three_bet": round(self.three_bet(), 3),
            "aggression": [round(self.aggression(s), 3) for s in range(_NUM_STREETS)],
            "fold_to_bet": [round(self.fold_to_bet(s), 3) for s in range(_NUM_STREETS)],
            "wtsd": round(self.wtsd(), 3),
            "won_at_showdown": round(self.won_at_showdown(), 3),
            "showdown_strength": round(self.showdown_strength(), 2),
            "opp_net": self.opp_net,
        }

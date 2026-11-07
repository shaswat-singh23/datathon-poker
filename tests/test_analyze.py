"""Tests for tools/analyze.py on a synthetic two-half sim JSON.
Run: python -m pytest -q tests/test_analyze.py"""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import analyze as A  # noqa: E402


def _hand(half, i, button, nets, actions, board_n=5, showdown=True):
    return {"half": half, "deal_index": i, "button_seat": button,
            "hole_cards": [["As", "Kd", "9h", "8h", "6c"], ["Qs", "Jd", "7c", "Th", "6s"]],
            "board": ["Qh", "Jh", "7d", "Ts", "6d"], "board_revealed": ["Qh", "Jh", "7d", "Ts", "6d"][:board_n],
            "actions": actions, "pot": sum(abs(n) for n in nets), "went_to_showdown": showdown,
            "nets": list(nets)}


def _act(seat, street, action, amount=0):
    return {"seat": seat, "street": street, "action": action, "amount": amount, "street_total": amount}


def _match(bot_a="hero.py", bot_b="villain.py", deals=2):
    """Bot A sits in seat 0 in half 1 and seat 1 in half 2. Chips flow to A: +10, +4, -6, +2."""
    half1 = [
        _hand(1, 0, 0, (10, -10), [_act(0, "PREFLOP", "RAISE_POT", 6), _act(1, "PREFLOP", "CHECK_CALL", 4),
                                    _act(1, "FLOP", "CHECK_CALL"), _act(0, "FLOP", "RAISE_HALF", 6),
                                    _act(1, "FLOP", "FOLD")], board_n=3, showdown=False),
        _hand(1, 1, 1, (4, -4), [_act(1, "PREFLOP", "CHECK_CALL", 1), _act(0, "PREFLOP", "CHECK_CALL")]),
    ]
    half2 = [  # A is now seat 1; a walk: seat 0 (B, button) folds preflop, A never acts
        _hand(2, 0, 0, (-2, 2), [_act(0, "PREFLOP", "FOLD")], board_n=0, showdown=False),
        _hand(2, 1, 1, (6, -6), [_act(1, "PREFLOP", "CHECK_CALL", 1), _act(0, "PREFLOP", "RAISE_POT", 6),
                                  _act(1, "PREFLOP", "FOLD")], board_n=0, showdown=False),
    ]
    a_total = 10 + 4 + 2 - 6  # +10 bb -> +5 bb/deal over 2 deals
    return {"bot_a": bot_a, "bot_b": bot_b, "name_a": "hero", "name_b": "villain", "seed": 1,
            "deals": deals, "paired_bb": [a_total / A.BIG_BLIND], "logs": {"half1": half1, "half2": half2}}


def _run(data, hero, capsys):
    rc = A.analyze(data, hero)
    out, err = capsys.readouterr()
    return rc, out, err


def _table_sums(out):
    """{table title: sum of its bb/deal column} for every table in the output."""
    sums, title = {}, None
    for line in out.splitlines():
        m = re.match(r"^(\S.*?)\s+hands\s+%hands\s+bb/hand\s+bb/deal\*?$", line)
        if m:
            title = m.group(1).strip()
            sums[title] = 0.0
            continue
        if title and line.strip() and not line.startswith("*"):
            parts = line.split()
            if len(parts) >= 5 and re.match(r"^[+-]\d", parts[-1]):
                sums[title] += float(parts[-1])
            else:
                title = None
    return sums


def test_seat_swap_and_sign_for_both_sides(capsys, monkeypatch):
    monkeypatch.setattr(A, "_percentile", lambda hole: 0.55)
    data = {"matches": [_match()]}
    rc, out, _ = _run(data, "hero", capsys)
    assert rc == 0
    assert "Overall +2.500 bb/deal  (sim paired_bb: +2.500)" in out  # +10 chips / 2 bb / 2 deals
    rc, out, _ = _run(data, "villain", capsys)
    assert rc == 0
    assert "Overall -2.500 bb/deal  (sim paired_bb: -2.500)" in out


def test_every_table_sums_to_overall(capsys, monkeypatch):
    monkeypatch.setattr(A, "_percentile", lambda hole: 0.55)
    rc, out, _ = _run({"matches": [_match()]}, "hero", capsys)
    assert rc == 0
    sums = _table_sums(out)
    assert {"position", "preflop pct", "preflop 1st act", "flop 1st act",
            "turn 1st act", "river 1st act"} <= set(sums), sorted(sums)
    for title, s in sums.items():
        assert s == pytest.approx(2.5, abs=1e-6), (title, s)
    assert "(no act)" in out and "(not reached)" in out  # the walk in half 2, and unreached streets


def test_opponent_table_is_per_opponent(capsys, monkeypatch):
    monkeypatch.setattr(A, "_percentile", lambda hole: 0.55)
    m2 = _match(bot_b="other.py")
    m2["name_b"] = "other"
    for h in m2["logs"]["half1"] + m2["logs"]["half2"]:
        h["nets"] = [0, 0]
    m2["paired_bb"] = [0.0]
    rc, out, _ = _run({"matches": [_match(), m2]}, "hero", capsys)
    assert rc == 0
    assert "Overall +1.250 bb/deal" in out  # (+10 + 0) chips / 2 bb / 4 deals
    opp = out[out.index("opponent"):]
    assert re.search(r"^villain\s+4\s+50\.0%\s+\+1\.250\s+\+2\.500$", opp, re.M), opp  # vs villain alone
    assert re.search(r"^other\s+4\s+50\.0%\s+\+0\.000\s+\+0\.000$", opp, re.M), opp


def test_needs_hero_when_bot_a_varies_and_warns_on_crash(capsys):
    data = {"matches": [_match(), _match(bot_a="x.py"), {"bot_a": "hero.py", "bot_b": "v.py",
                                                         "seed": 3, "crash": "boom"}]}
    rc, _, err = _run(data, None, capsys)
    assert rc == 1 and "pass --hero" in err
    rc, out, err = _run(data, "hero", capsys)
    assert rc == 0 and "skipping 1 crashed match" in err and "+2.500 bb/deal" in out


def test_no_logs_exits_1(capsys):
    m = _match()
    del m["logs"]
    rc, _, err = _run({"matches": [m]}, "hero", capsys)
    assert rc == 1 and "--generate" in err

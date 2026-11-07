"""Fast tests for tools/sim.py (the in-process match simulator)."""

import json
import os
import sys
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

import sim  # noqa: E402
from game import ERROR_LIMIT, make_deal  # noqa: E402

BASE = os.path.join(ROOT, "baseline-bots")
POT = os.path.join(BASE, "baseline_always_pot.py")
STATION = os.path.join(BASE, "baseline_calling_station.py")
RANDOM = os.path.join(BASE, "baseline_random.py")

HEADER = "from game import Action\n"


def write_bot(tmp_path, name, body):
    path = tmp_path / f"{name}.py"
    path.write_text(HEADER + textwrap.dedent(body))
    return str(path)


def test_structure_and_zero_sum():
    r = sim.run_match(RANDOM, STATION, deals=40, seed="t1")
    for key in ("bb_per_deal", "ci", "verdict", "half_chips", "errors", "timing", "paired_bb"):
        assert key in r
    assert r["verdict"] in ("A_WIN", "B_WIN", "CHOP")
    assert r["ci"][0] <= r["bb_per_deal"] <= r["ci"][1]
    assert len(r["paired_bb"]) == 40
    for half in ("half1", "half2"):
        assert r["half_chips"][half]["a"] + r["half_chips"][half]["b"] == 0
    total = r["half_chips"]["half1"]["a"] + r["half_chips"]["half2"]["a"]
    assert r["bb_per_deal"] == pytest.approx(total / 2 / 40)
    assert r["errors"] == {"a": [0, 0], "b": [0, 0]}
    assert all(t["decisions"] > 0 for t in r["timing"]["a"] + r["timing"]["b"])
    json.dumps(r)  # JSON-friendly


def test_deterministic():
    r1 = sim.run_match(RANDOM, POT, deals=30, seed="det")
    r2 = sim.run_match(RANDOM, POT, deals=30, seed="det")
    assert r1["paired_bb"] == r2["paired_bb"]


def test_duplicate_seat_swap(tmp_path, monkeypatch):
    """Each bot gets seat 0's cards in one half and seat 1's in the other."""
    log = tmp_path / "seen.jsonl"
    monkeypatch.setenv("SIM_TEST_LOG", str(log))
    body = """
        import json, os
        def new_half(config, memory):
            memory["id"] = os.path.basename(__file__)
        def choose_action(obs, memory):
            with open(os.environ["SIM_TEST_LOG"], "a") as f:
                f.write(json.dumps([memory["id"], obs.hand_index, list(obs.hole_cards)]) + "\\n")
            return Action.CHECK_CALL
        def on_hand_end(result, memory):
            pass
    """
    a = write_bot(tmp_path, "rec_a", body)
    b = write_bot(tmp_path, "rec_b", body)
    sim.run_match(a, b, deals=12, seed="swap")
    seen = {}  # (bot, hand) -> list of hole cards over the match
    for line in log.read_text().splitlines():
        bot, hand, hole = json.loads(line)
        cards = seen.setdefault((bot, hand), [])
        if tuple(hole) not in cards:
            cards.append(tuple(hole))
    for d in range(12):
        deal = make_deal("swap", d)
        # half 1: A in seat 0, half 2: A in seat 1 (calling stations see every hand)
        assert seen[("rec_a.py", d)] == [deal.hole_cards[0], deal.hole_cards[1]]
        assert seen[("rec_b.py", d)] == [deal.hole_cards[1], deal.hole_cards[0]]


def test_crashing_bot_forfeits(tmp_path):
    bad = write_bot(tmp_path, "crasher", """
        def new_half(config, memory): pass
        def choose_action(obs, memory): raise RuntimeError("boom")
        def on_hand_end(result, memory): pass
    """)
    r = sim.run_match(bad, STATION, deals=20, seed="crash")
    assert r["forfeited"]["a"] == [True, True]
    assert r["errors"]["a"] == [ERROR_LIMIT, ERROR_LIMIT]
    assert r["verdict"] == "B_WIN" and r["points_a"] == 0.0
    assert "boom" in r["error_messages"]["a"][0]


def test_crash_in_on_hand_end_counts(tmp_path):
    bad = write_bot(tmp_path, "hand_end_crasher", """
        def new_half(config, memory): pass
        def choose_action(obs, memory): return Action.CHECK_CALL
        def on_hand_end(result, memory): raise ValueError("bad result handling")
    """)
    r = sim.run_match(bad, STATION, deals=20, seed="he")
    assert r["forfeited"]["a"] == [True, True]
    assert "on_hand_end" in r["error_messages"]["a"][0]


def test_illegal_action_is_counted(tmp_path):
    # Returns FOLD when checking is free (illegal), at most twice per half.
    bot = write_bot(tmp_path, "illegal", """
        def new_half(config, memory): memory["bad"] = 0
        def choose_action(obs, memory):
            if obs.to_call == 0 and memory["bad"] < 2:
                memory["bad"] += 1
                return Action.FOLD
            return Action.CHECK_CALL
        def on_hand_end(result, memory): pass
    """)
    r = sim.run_match(bot, STATION, deals=30, seed="ill")
    assert r["errors"]["a"] == [2, 2]
    assert r["forfeited"]["a"] == [False, False]
    assert "illegal action FOLD" in r["error_messages"]["a"][0]


def test_non_action_answer_is_counted(tmp_path):
    bot = write_bot(tmp_path, "garbage", """
        def new_half(config, memory): pass
        def choose_action(obs, memory): return 2.5
        def on_hand_end(result, memory): pass
    """)
    r = sim.run_match(bot, STATION, deals=10, seed="g")
    assert r["forfeited"]["a"] == [True, True]
    assert "not an Action" in r["error_messages"]["a"][0]


def test_globals_reset_each_half(tmp_path):
    # Like a fresh server per half: a module-level counter starts over.
    bot = write_bot(tmp_path, "globals", """
        HALVES = 0
        def new_half(config, memory):
            global HALVES
            HALVES += 1
        def choose_action(obs, memory):
            if HALVES != 1:
                raise RuntimeError("globals leaked between halves")
            return Action.CHECK_CALL
        def on_hand_end(result, memory): pass
    """)
    r = sim.run_match(bot, STATION, deals=10, seed="glob")
    assert r["errors"]["a"] == [0, 0]


def test_time_bank_runs_out_without_errors(tmp_path):
    bot = write_bot(tmp_path, "slow", """
        import time
        def new_half(config, memory): pass
        def choose_action(obs, memory):
            time.sleep(0.004)
            return Action.CHECK_CALL
        def on_hand_end(result, memory): pass
    """)
    r = sim.run_match(bot, STATION, deals=60, seed="slow", time_bank=0.05)
    assert r["timed_out"]["a"] == [True, True]
    assert r["errors"]["a"] == [0, 0]
    assert r["timing"]["a"][0]["skipped_calls"] > 0


def test_cli_pair_and_json(tmp_path, capsys):
    out = tmp_path / "out.json"
    sim.main([RANDOM, STATION, "--deals", "20", "--seeds", "2", "--procs", "1",
              "--json", str(out), "--quiet"])
    data = json.loads(out.read_text())
    assert len(data["matches"]) == 2 and data["summary"]["pooled"]["deals"] == 40
    assert "Pooled over 40 deals" in capsys.readouterr().out


def test_decision_over_one_second_is_an_error(tmp_path):
    bot = write_bot(tmp_path, "stall", """
        import time
        def new_half(config, memory): memory["slept"] = False
        def choose_action(obs, memory):
            if not memory["slept"]:
                memory["slept"] = True
                time.sleep(1.05)
            return Action.CHECK_CALL
        def on_hand_end(result, memory): pass
    """)
    r = sim.run_match(bot, STATION, deals=5, seed="stall")
    assert r["errors"]["a"] == [1, 1]
    assert "longer than 1s" in r["error_messages"]["a"][0]
    assert r["timing"]["a"][0]["max_call_ms"] > 1000
    assert r["timing"]["a"][0]["max_cpu_call_ms"] < 100   # sleeping burns no CPU


def test_cpu_time_fields_and_cpu_not_above_wall():
    r = sim.run_match(RANDOM, STATION, deals=40, seed="cpu")
    for side in ("a", "b"):
        for h in r["timing"][side]:
            for key in ("cpu_s", "max_cpu_call_ms", "mean_cpu_decision_ms",
                        "wall_s", "max_call_ms", "mean_decision_ms"):
                assert key in h
            assert 0 <= h["cpu_s"] <= h["wall_s"] + 1e-4
            assert 0 <= h["max_cpu_call_ms"] <= h["max_call_ms"] + 1e-3
            assert h["mean_cpu_decision_ms"] <= h["mean_decision_ms"] + 1e-3


def test_cpu_flag_only_when_cpu_is_slow():
    t = {"max_half_think_s": 0.1, "max_half_compute_s": 0.1, "max_call_ms": 150.0,
         "max_cpu_call_ms": 14.4, "errors": 0, "forfeits": 0, "timeouts": 0}
    assert sim._flags(t) == "ok"            # a wall spike alone is machine load
    t["max_cpu_call_ms"] = 120.0
    assert "cpu max > 100 ms" in sim._flags(t)

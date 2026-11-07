"""Tests for the agent.py shell's per-half memory setup."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent  # noqa: E402
from bot import timing  # noqa: E402
from game import NUM_DEALS, AgentConfig, Street  # noqa: E402


def _obs(hand=0):
    return SimpleNamespace(hand_index=hand, street=Street.FLOP, pot=8, to_call=0)


@pytest.mark.parametrize("n", [200, NUM_DEALS, 1])
def test_new_half_stores_num_hands(n):
    memory = {}
    agent.new_half(AgentConfig(num_hands=n, time_bank_seconds=4.0), memory)
    assert memory["_num_hands"] == n
    assert memory["_bank"] == 4.0


@pytest.mark.parametrize("bad", [None, 0, -5, "abc", float("inf")])
def test_bad_num_hands_left_unset(bad):
    memory = {}
    agent.new_half(SimpleNamespace(num_hands=bad, time_bank_seconds=8.0), memory)
    assert "_num_hands" not in memory          # timing.py falls back to NUM_DEALS
    assert timing.budget_ms(memory, _obs()) >= 0.0


def test_timing_budgets_for_the_configured_hand_count():
    short, full = {}, {}
    agent.new_half(AgentConfig(num_hands=200), short)
    agent.new_half(AgentConfig(num_hands=NUM_DEALS), full)
    b_short = timing.budget_ms(short, _obs())
    b_full = timing.budget_ms(full, _obs())
    # Same bank spread over 5x fewer hands: a clearly bigger first budget.
    assert b_short > 2.0 * b_full > 0.0

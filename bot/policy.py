"""bot/policy.py - the strategy. agent.py wraps these three functions with
crash/illegal-action/time-bank protection, so this file can focus on poker.

Placeholder heuristic until the equity-engine strategy lands.
"""
from evaluator import card_rank, card_suit, category_of, omaha_score
from game import Action, Street


def new_half(config, memory):
    memory["hands"] = 0


def _preflop_score(hole):
    ranks = sorted((card_rank(c) for c in hole), reverse=True)
    suits = [card_suit(c) for c in hole]
    score = sum(ranks) / 40.0
    if len(set(ranks)) < 5:
        score += 0.15
    if max(suits.count(s) for s in set(suits)) >= 2:
        score += 0.1
    return score


def choose_action(obs, memory):
    legal = obs.legal_actions
    if obs.street == Street.PREFLOP:
        s = _preflop_score(obs.hole_cards)
        if s > 1.0 and Action.RAISE_POT in legal and obs.raises_this_street < 2:
            return Action.RAISE_POT
        if s > 0.75 or obs.to_call == 0:
            return Action.CHECK_CALL
        return Action.FOLD if obs.to_call > 1 else Action.CHECK_CALL
    if len(obs.board) >= 3:
        cat = category_of(omaha_score(obs.hole_cards, obs.board))
        if cat >= 5 and Action.RAISE_POT in legal:
            return Action.RAISE_POT
        if cat >= 3 or obs.to_call == 0:
            return Action.CHECK_CALL
        if obs.to_call * 4 <= obs.pot and cat >= 1:
            return Action.CHECK_CALL
    return Action.FOLD if obs.to_call > 0 else Action.CHECK_CALL


def on_hand_end(result, memory):
    memory["hands"] += 1

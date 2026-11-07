# Time budget keeps charged time under 6.5 s in a simulated half
- Issue: #5 | Author: Shaswat (Claude Code) | Time: 12:36
- Claim: `bot/timing.py` keeps a simulated 1000-hand half at <= 6.49 s charged (of 8 s) whenever the per-decision fixed cost leaves room, including the worst-case 8 decisions every hand at 1x, 1.5x and 2x CPU slowdown. In typical play (3 decisions/hand) it spends 6.47 s, about 3.2-4.5 s of it on Monte Carlo, spread evenly (last 200 hands vs first 200 within 0.5x-2x).
- Evidence:
  - Worst case is 8 decisions per hand for one seat (7 on the button), from an exhaustive search of every non-fold action sequence with `game.Game.clone()` (57,442 nodes).
  - Simulated charge (agent.py's 0.5 ms/decision + non-MC policy cost + MC overshooting its budget by 10%), from `python -m pytest -q tests/test_timing.py` (17 tests pass):

    | hands | CPU | non-MC cost | charged | of which MC |
    |---|---|---|---|---|
    | worst (8/hand) | 1.0x | 1x prior | 6.49 s | 1.27 s |
    | worst | 1.0x | 2x prior | 6.49 s | 0.07 s |
    | worst | 1.5x | 1x prior | 6.49 s | 0.67 s |
    | worst | 2.0x | 1x prior | 6.49 s | 0.07 s |
    | worst | 2.0x | 2x prior | 8.86 s | 0.04 s |
    | typical (3/hand) | 1.0x | 1x | 6.47 s | 4.50 s |
    | typical | 2.0x | 2x | 6.47 s | 3.15 s |
  - The 8.86 s row is infeasible for any budget: fixed cost alone is 8.82 s. There timing.py backs off to 0.04 s of MC.
  - Baseline: with no budget manager, a flat 1 ms MC per decision at worst case charges 8000 x (1.1 + 0.65) ms = 14 s; the bank hits the 0.25 s emergency reserve around hand 550 and the bot check-folds the rest.
- So what: the bot can use Monte Carlo without ever timing out into check-or-fold. The real risk is fixed per-decision cost: at 8 decisions every hand, agent.py's 0.5 ms bookkeeping plus about 0.15 ms of policy code already uses 5.2 s. Non-MC policy code has to stay small (see #13).
- Checked by: unchecked

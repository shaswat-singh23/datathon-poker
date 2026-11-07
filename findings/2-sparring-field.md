# Sparring field pecking order (round robin, 3 seeds × 1000 deals)
- Issue: #2 | Author: Kyle (agent) | Time: 2026-11-07 14:30
- Claim: the sparring field spans a wide skill range. `exploiter` and `tag` (Monte Carlo equity + pot odds, tag ≈ exploiter) are the strongest references; the organizers' baselines and `maniac` are the weakest. Any never-fold pair chops at exactly 0.00 bb/deal.
- Evidence: `.venv/bin/python tools/sim.py --round-robin tools/opponents/*.py baseline-bots/*.py --seeds 3 --procs 9 --quiet` (198 matches, 396,000 hands, 137 s)

```
bot                          pts /n      W   L   C  avg bb/deal  max half s   max ms  errs
exploiter                   30.0 /33    27   0   6       +4.426        2.78     40.5     0
tag                         29.5 /33    26   0   7       +3.068        3.17     65.9     0
trappy                      24.5 /33    19   3  11       +1.787        3.22     89.9     0
potodds                     21.5 /33    19   9   5       +3.897        3.48     53.2     0
nit                         21.5 /33    16   6  11       +0.650        2.26     27.4     0
lag                         16.0 /33    14  15   4       +0.906        3.09    141.9     0
rock_shover                 13.5 /33     2   8  23       -0.125        0.01     12.7     0
baseline_always_half        12.0 /33     6  15  12       -2.338        0.00      1.8     0
baseline_always_pot         10.0 /33     3  16  14       -1.217        0.00      1.7     0
maniac                       9.5 /33     3  17  13       -1.468        0.01      4.7     0
baseline_calling_station     7.0 /33     0  19  14       -4.039        0.00      3.0     0
baseline_random              3.0 /33     0  27   6       -5.548        0.00      4.7     0
```
  Head-to-head highlights (row vs column, bb/deal): tag vs exploiter +0.01 (chop); potodds +14.0 vs always_half but −3.5 vs tag; always_half +2.6 vs nit; all never-fold pairs (maniac, always_pot, always_half, calling_station) exactly +0.00.
  Judge parity: deterministic bots give identical per-half chips in the sim and in `judge_engine.py --deals 200 --seed 7` (always_pot vs calling_station +240/−240; random vs always_half −2271/−2021; agent.py vs random −199/−199).
- So what: this is the baseline every strategy ticket must beat (AGENTS.md "Baseline and measurement"). Two lessons for strategy: pure pot-odds math crushes aggressive bots but bleeds ~3.5 bb/deal to equity bots that narrow ranges, and over-folding is punished (nit loses to always_half). Time: no sparring bot ever errored; worst single decision 142 ms under 9-process load.
- Checked by: unchecked

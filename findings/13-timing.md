# Timing safety sweep: 3 s bank, slow-CPU margin
- Issue: #13 | Author: Kyle (agent) | Time: 14:50
- Claim: `agent.py` cannot empty its time bank or hit the 1 s/decision limit on a machine 2-3x slower than the dev Mac. With the bank cut to 3 s (37% of the real 8 s), the field run had zero empty-bank halves, timeouts, errors and forfeits. The bot used at most 0.69 s of the 3 s. No decision used more than 21 ms of the bot's own CPU time. Startup takes 0.33 s. `bot/timing.py` was not changed.
- Evidence:
  - Field run: `python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --time-bank 3` was run twice (`--procs 8` and `--procs 1`). Each run was 12 opponents x 3 seeds x 1000 deals = 72 hero halves and about 220k decisions.

    | run | empty-bank halves | timeouts | errors | forfeits | max charged / half | max raw compute / half | mean ms/dec | max call (wall) |
    |---|---|---|---|---|---|---|---|---|
    | procs 8 | 0 | 0 | 0 | 0 | 0.64 s | 0.79 s | 0.088 | 118.9 ms |
    | procs 1 | 0 | 0 | 0 | 0 | 0.69 s | 0.84 s | 0.077 | 111.4 ms |

  - Worst single decision. A third sequential pass over the same 36 matches timed every hero call. It recorded wall time and CPU time (`time.thread_time`), and flagged calls that triggered a gen-2 GC. That was 291,426 calls in total.
    - Worst CPU time, ignoring gen-2 GC: **20.9 ms** (vs rock_shover, a Monte Carlo spot). This is the bot's real cost and is well under the 100 ms target.
    - Worst CPU time overall: 59.8 ms. That call was a gen-2 GC inside the long-lived sim process, which by then had a heap built up over 35 earlier matches. The real judge starts a fresh process for each half. In a fresh `import agent`, a full `gc.collect()` takes **3.9 ms** (55k objects). In a fresh process, the worst call vs baseline_random seed 2 was 2.9 ms, against the 139 ms it took inside the long-lived process.
    - Wall-time spikes over 100 ms: 1 call in 291k (110.8 ms vs nit seed 2). That same match's worst CPU time was 7.9 ms, so the spike came from the OS pausing the process, not from bot code. The machine's load average was 24-28 on 10 cores during all runs, from other sessions' sims. The `max call` column in the table is inflated by the same effect.
  - Startup:
    - `import agent` in a fresh interpreter: 0.30-0.41 s (3 runs).
    - Launching `python agent.py` until the first `GET /` answers: 0.33-0.34 s (3 runs). `tools/smoke_test.py` passed against that server each time.
- Slow-CPU margin:
  - A 3x slower CPU scales the worst bot decision to about 63 ms, under the 1 s limit by a factor of about 16.
  - It scales the worst raw compute per half to about 2.5 s. That stays under even the 3 s test bank, before any adaptation.
  - The real bank is 8 s. On top of that, `bot/timing.py` calibrates machine speed at import, measures the real overhead per decision after 50 decisions, and holds 1.5 s in reserve. So Monte Carlo would shrink before the bank was at risk.
  - The Monte Carlo budget is capped at 40 ms of wall time per decision (`CEIL_MS`), whatever the CPU speed.
- So what: the "any forfeit = match loss" rule cannot be triggered by time. That holds even on a tournament box 2-3x slower than ours, and even when it is heavily overloaded.
- Checked by: unchecked

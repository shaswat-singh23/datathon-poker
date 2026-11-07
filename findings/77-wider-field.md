# Wider sparring field: a value-only bettor (fitorfold) beats us at both banks
- Issue: #77 | Author: Shaswat (agent) | Time: 18:40
- Claim: Three new sparring bots in `tools/opponents/` (`fitorfold`, `cbetter`, `honest`) expose a gap the old field hid. Master loses **0-3 to `fitorfold`** at the real 8 s bank (-1.313 bb/deal [-1.715, -0.911]), only chops `cbetter`, and beats `honest`. The same holds with PR #70 (-1.272) and PR #73 (-1.476) applied, so neither fixes it.
- Evidence: `tools/sim.py --hero agent.py --field tools/opponents/{fitorfold,cbetter,honest}.py --seeds 3 --time-bank 8 --procs 4` (3 seeds x 1000 deals, duplicate format), master `07818ed` plus the three new files. PR #70 and #73 heads were run from `git archive` copies with the same bots and command.

| opponent | master 8 s bb/deal [95% CI] | pts | master 4 s | pts | PR #70 8 s | PR #73 8 s |
|---|---|---|---|---|---|---|
| honest | +1.482 [+1.066, +1.898] | 3.0 | +0.899 [+0.673, +1.126] | 3.0 | +1.529 | +1.405 |
| cbetter | -0.173 [-0.728, +0.382] | 1.5 | -0.229 [-0.793, +0.335] | 1.5 | -0.147 | -0.186 |
| fitorfold | **-1.313 [-1.715, -0.911]** | **0.0** | -0.289 [-0.584, +0.006] | 1.5 | **-1.272** | **-1.476** |
| total | -0.001 | 4.5 / 9 | +0.127 | 6.0 / 9 | +0.037 (4.5 / 9) | -0.086 (4.5 / 9) |

- Diagnosis (`tools/analyze.py --generate`, hero vs fitorfold, 2 seeds x 200 deals, 8 s, so small): showdowns cost -4.54 bb/hand on 34% of hands (-3.08 bb/deal), everything else is slightly positive. When we call a flop or turn bet we lose 13 bb per hand, and a river call costs 25 bb. fitorfold bets pot only with Monte Carlo equity > 0.68 and folds to everything else, so its bets are nearly always value. We pay them off, and our line discount (PR #70: 0.20, fading against habitual bettors) is too small for a bettor this honest.
- Caveats:
  1. Hero CPU max per decision was 144-285 ms in these runs, over the 100 ms rule. The box was loaded by two other sweeps, but it is CPU time, so treat it as unverified; worth a rerun on an idle box (tracked by #28/#53's history).
  2. At 4 s the hero empties its own bank against nobody here, but fitorfold itself emptied its bank in 6 halves, which helps us. The 4 s row understates the 8 s loss.
  3. These are my guesses at student styles, not data on the real field. Not every claim here generalizes; the point is the failure mode (value-only bettors).
- So what: a judge cares because a field of student bots will contain tight value bettors, and each is a match loss, not a small bb dent. Follow-up (separate ticket): make the opponent model learn from showdowns how strong the opponent's postflop bets are (bet frequency vs showdown equity) and fold more to bettors who only show down strong hands.
- Checked by: unchecked

"""tools/sweep_cbet.py - screen postflop PARAMS overrides against one opponent (#82).

Two roles in one file, so a sweep needs nothing outside the repo:

* As a hero (tools/sim.py loads it by path): agent.py with extra postflop PARAMS
  applied after exploit.apply, taken from the PF_OVERRIDE env var (JSON). Set
  PF_VS_CBET=0 to switch bot.vs_cbet off (the "gate off" arm of a paired run).
* As a script: runs tools/sim.py once per variant on the same seeds (paired), waits
  for a quiet box first (1-min load < cpus/2, no other sim running), and prints the
  paired bb/deal delta against the first variant.

    python tools/sweep_cbet.py --opp tools/opponents/cbetter.py --seeds 12 --seed-base scr \\
        --time-bank 8 --variants '{}' '{"bet_half_eq":0.70}' '{"bet_half_eq":0.76}'
"""
import json
import os
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

if __name__ != "__main__":  # loaded by tools/sim.py as a hero
    import agent as _a
    from bot import exploit as _ex
    from bot import vs_cbet as _vc

    _OV = json.loads(os.environ.get("PF_OVERRIDE", "{}"))
    _orig = _ex.apply

    def _apply(memory, model=None):
        r = _orig(memory) if model is None else _orig(memory, model)
        if _OV:
            memory["postflop_params"] = {**(memory.get("postflop_params") or {}), **_OV}
        return r

    _ex.apply = _apply
    if os.environ.get("PF_VS_CBET", "1") == "0":
        _vc.apply = lambda obs, memory: False
    new_half, choose_action, on_hand_end = _a.new_half, _a.choose_action, _a.on_hand_end


def _quiet_box():
    limit = (os.cpu_count() or 2) / 2
    while True:
        busy = subprocess.run(["pgrep", "-f", "tools/sim.py"], capture_output=True, text=True).stdout.split()
        if os.getloadavg()[0] < limit and len(busy) <= 1:
            return
        time.sleep(30)


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--opp", required=True, help="opponent bot file")
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--seed-base", default="scr")
    ap.add_argument("--time-bank", type=float, default=8)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--vs-cbet", choices=("0", "1"), default="1", help="0 switches bot.vs_cbet off")
    ap.add_argument("--variants", nargs="+", default=["{}"], help="JSON PARAMS overrides; the first is the control")
    args = ap.parse_args()
    base, out = None, []
    for i, ov in enumerate(args.variants):
        _quiet_box()
        path = os.path.join(os.environ.get("DATA_DIR", "data"), f"sweep_cbet_{os.getpid()}_{i}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        env = {**os.environ, "PF_OVERRIDE": ov, "PF_VS_CBET": args.vs_cbet}
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sim.py"), "--hero", os.path.abspath(__file__),
                        "--field", args.opp, "--seeds", str(args.seeds), "--seed-base", args.seed_base,
                        "--time-bank", str(args.time_bank), "--procs", str(args.procs), "--quiet", "--json", path],
                       env=env, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        ms = json.load(open(path))["matches"]
        x = [m["bb_per_deal"] for m in ms]
        base = base or x
        d = [a - b for a, b in zip(x, base)]
        se = statistics.stdev(d) / len(d) ** 0.5 if i and len(d) > 1 else 0.0
        out.append((ov, statistics.mean(x), statistics.mean(d), se, sum(m["points_a"] for m in ms), len(ms),
                    max(t["think_s"] for m in ms for t in m["timing"]["a"])))
        print(f"{ov:48s} {out[-1][1]:+.3f} bb/deal  paired {out[-1][2]:+.3f} ± {se:.3f}  "
              f"{out[-1][4]}/{out[-1][5]} pts  max half think {out[-1][6]:.2f} s", flush=True)


if __name__ == "__main__":
    main()

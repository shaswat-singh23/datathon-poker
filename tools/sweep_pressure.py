"""tools/sweep_pressure.py - sweep bot/pressure.py's PARAMS against a screening field (#68).

Each variant is an env string for PRESSURE ("off" = module disabled = master's play).
Runs tools/sim.py once per variant (same seeds, so results pair by deal), writes
data/68-sweep-<tag>.json, and prints one row per variant: points, mean bb/deal,
per-opponent bb/deal, max CPU ms, errors.

    .venv/bin/python tools/sweep_pressure.py [--deals 1000] [--seeds 1] [--time-bank 8]
                                              [--procs 3] [--variants off,default,...]
                                              [--field tools/opponents/tag.py ...]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("DATA_DIR", os.path.join(REPO, "data"))

VARIANTS = {
    "off": "off",
    "default": "",
    "s10": "called_shift=0.10",
    "s35": "called_shift=0.35",
    "m0": "margin=0.0",
    "m8": "margin=0.08",
    "turn": "min_street=2",
    "potbig": "size_pot_fold=0.5",
    "s10m0": "called_shift=0.10,margin=0.0",
    "s35m8": "called_shift=0.35,margin=0.08",
}
SCREEN = ["tools/opponents/tag.py", "tools/opponents/exploiter.py", "tools/opponents/nit.py",
          "tools/opponents/trappy.py", "tools/opponents/potodds.py",
          "baseline-bots/baseline_calling_station.py"]


def run(tag: str, env_val: str, args) -> dict:
    out = os.path.join(DATA, f"68-sweep-{args.label}{tag}.json")
    if os.path.exists(out) and not args.force:
        return json.load(open(out))
    cmd = [sys.executable, os.path.join(REPO, "tools", "sim.py"), "--hero", "agent.py",
           "--field", *args.field, "--seeds", str(args.seeds), "--deals", str(args.deals),
           "--time-bank", str(args.time_bank), "--procs", str(args.procs),
           "--seed-base", args.seed_base, "--quiet", "--json", out]
    env = dict(os.environ, PRESSURE=env_val)
    t0 = time.time()
    with open(out + ".log", "w") as log:
        subprocess.run(cmd, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    d = json.load(open(out))
    d["wall_s"] = time.time() - t0
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deals", type=int, default=1000)
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--seed-base", default="sim")
    ap.add_argument("--time-bank", type=float, default=8.0)
    ap.add_argument("--procs", type=int, default=3)
    ap.add_argument("--label", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--field", nargs="+", default=SCREEN)
    args = ap.parse_args()
    os.makedirs(DATA, exist_ok=True)
    names = None
    rows = []
    for tag in args.variants.split(","):
        d = run(tag, VARIANTS[tag], args)
        s = d["summary"]
        table = s["table"]
        if names is None:
            names = [r["opponent"] for r in table]
            print(f"{'variant':<9}{'pts':>6}{'bb/deal':>9} " + "".join(f"{n[:11]:>12}" for n in names)
                  + f"{'maxCPUms':>10}{'err':>4}{'empty':>6}", flush=True)
        by = {r["opponent"]: r for r in table}
        ht = s["hero_timing"]
        empties = sum(1 for m in d["matches"] if "crash" not in m
                      for t in m["timing"]["a"] if t.get("think_s", 0) >= args.time_bank)
        print(f"{tag:<9}{s['points']:>6.1f}{s['overall']['bb_per_deal']:>+9.3f} "
              + "".join(f"{by[n]['bb_per_deal']:>+12.3f}" for n in names)
              + f"{ht['max_cpu_call_ms']:>10.1f}{ht['errors']:>4}{empties:>6}", flush=True)
        rows.append((tag, s["points"], s["overall"]["bb_per_deal"]))


if __name__ == "__main__":
    main()

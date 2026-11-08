"""tools/sweep_family.py - hero vs a random family of equity-threshold bots (#89).

1. tools/gen_family.py writes --n bots (seeded, reproducible).
2. Screen: the hero plays every bot for --screen-seeds matches at --screen-bank (default 8 s).
3. Confirm: every bot the hero does not clearly beat (screen CI lower bound < --flag-ci, or a
   non-win match), worst first and at most --max-confirm of them, replays on --confirm-seeds
   fresh seeds at each bank in --banks.
4. Writes <out>/screen.json, <out>/confirm-tb<bank>.json, <out>/summary.json and prints tables.

Waits for a quiet box before each sim (1-min load < cpus/2), samples the load every 15 s during
it, and gives up after --wait-min. Hero timing/error counts come from tools/sim.py's summary.

    python tools/sweep_family.py --n 40 --gen-seed 1 --out /tmp/89 --procs 5
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_family  # noqa: E402

PY = sys.executable


def wait_quiet(max_min):
    limit = (os.cpu_count() or 2) / 2
    t0 = time.time()
    while os.getloadavg()[0] >= limit:
        if time.time() - t0 > max_min * 60:
            raise SystemExit("box never got quiet (load %.1f >= %.1f)" % (os.getloadavg()[0], limit))
        time.sleep(20)


def run_sim(files, seeds, seed_base, bank, procs, out_json, wait_min):
    wait_quiet(wait_min)
    cmd = [PY, os.path.join(ROOT, "tools", "sim.py"), "--hero", os.path.join(ROOT, "agent.py"),
           "--field", *files, "--seeds", str(seeds), "--seed-base", seed_base,
           "--time-bank", str(bank), "--procs", str(procs), "--quiet", "--json", out_json]
    loads, stop = [os.getloadavg()[0]], threading.Event()

    def sample():
        while not stop.wait(15):
            loads.append(os.getloadavg()[0])
    th = threading.Thread(target=sample, daemon=True)
    th.start()
    log = out_json[:-5] + ".log"
    with open(log, "w") as f:
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT).returncode
    stop.set()
    loads.append(os.getloadavg()[0])
    if rc:
        raise SystemExit("sim failed (%d), see %s" % (rc, log))
    with open(out_json) as f:
        res = json.load(f)
    res["load"] = {"start": loads[0], "peak": max(loads), "end": loads[-1]}
    return res["summary"], res["load"]


def table(rows, fam, title):
    print("\n" + title)
    print("%-12s %-24s %5s %5s  %s" % ("opponent", "hero bb/deal [95% CI]", "W-L-C", "pts", "hero max ms / opp errs"))
    for r in rows:
        ci = r["ci"]
        print("%-12s %+7.3f [%+6.3f,%+6.3f]   %d-%d-%d %5.1f  %5.1f / %d"
              % (r["opponent"], r["bb_per_deal"], ci[0], ci[1], r["W"], r["L"], r["C"], r["points"],
                 r["hero_timing"]["max_call_ms"], r["opp_timing"]["errors"]))


def safety(summary):
    t = summary["hero_timing"]
    rows = summary["table"]
    return {"hero_errors": t["errors"], "hero_max_call_ms": t["max_call_ms"],
            "hero_max_half_think_s": t["max_half_think_s"],
            "opp_errors": sum(r["opp_timing"]["errors"] for r in rows),
            "crashed": sum(r["crashed"] for r in rows)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--gen-seed", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--procs", type=int, default=5)
    ap.add_argument("--screen-seeds", type=int, default=2)
    ap.add_argument("--confirm-seeds", type=int, default=10)
    ap.add_argument("--flag-ci", type=float, default=0.5, help="confirm bots whose screen CI lower bound is below this")
    ap.add_argument("--max-confirm", type=int, default=8)
    ap.add_argument("--screen-bank", type=float, default=8)
    ap.add_argument("--banks", type=float, nargs="+", default=[8, 4], help="banks for the confirmation runs")
    ap.add_argument("--wait-min", type=float, default=30)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    fam_dir = os.path.join(a.out, "family")
    paths, fam = gen_family.generate(a.n, a.gen_seed, fam_dir)
    byname = {os.path.basename(p)[:-3]: p for p in paths}

    screen, load = run_sim(paths, a.screen_seeds, "scr%d" % a.gen_seed, a.screen_bank, a.procs,
                           os.path.join(a.out, "screen.json"), a.wait_min)
    rows = sorted(screen["table"], key=lambda r: r["ci"][0])
    table(rows, fam, "SCREEN: hero %g s, %d seeds x 1000 deals, worst first (load %s)" % (a.screen_bank, a.screen_seeds, load))
    print("screen overall: %.1f / %d pts, safety %s" % (screen["points"], screen["matches"], safety(screen)))

    flagged = [r for r in rows if r["ci"][0] < a.flag_ci or r["points"] < a.screen_seeds][:a.max_confirm]
    summary = {"screen": {"points": screen["points"], "matches": screen["matches"], "load": load,
                          "safety": safety(screen),
                          "rows": {r["opponent"]: {k: r[k] for k in ("bb_per_deal", "ci", "W", "L", "C", "points")} for r in rows}},
               "flagged": [r["opponent"] for r in flagged], "confirm": {}}
    if flagged:
        files = [byname[r["opponent"]] for r in flagged]
        for bank in a.banks:
            conf, load = run_sim(files, a.confirm_seeds, "cf%d" % a.gen_seed, bank, a.procs,
                                 os.path.join(a.out, "confirm-tb%g.json" % bank), a.wait_min)
            crow = sorted(conf["table"], key=lambda r: r["ci"][0])
            table(crow, fam, "CONFIRM: hero %g s bank, %d fresh seeds (load %s)" % (bank, a.confirm_seeds, load))
            print("confirm %g s: %.1f / %d pts, safety %s" % (bank, conf["points"], conf["matches"], safety(conf)))
            summary["confirm"]["tb%g" % bank] = {
                "points": conf["points"], "matches": conf["matches"], "load": load, "safety": safety(conf),
                "rows": {r["opponent"]: {k: r[k] for k in ("bb_per_deal", "ci", "W", "L", "C", "points")} for r in crow}}
    summary["params"] = {r["opponent"]: fam[r["opponent"]] for r in rows}
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print("\nwrote", os.path.join(a.out, "summary.json"))


if __name__ == "__main__":
    main()

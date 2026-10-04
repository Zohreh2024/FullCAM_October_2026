"""
Step 2 - run FullCAM for every period x SSP x species x configuration.

Design
------
Two climate periods, each an AVERAGE year of the prepared inputs:

    period  inputs averaged over   simulation
    mid     2035-2064              2050 -> 2150
    late    2070-2099              2085 -> 2185

For each of the four SSPs and every species x planting configuration in
config.SPECIES_GEOMETRY, one PLO per point is built from the period's average
climate, FPI and maxAbgMF, the historical soil layers and the species' TYF
parameters, and posted to the FullCAM 2024 REST simulator. The average year is
repeated for all 100 simulated years (tExtrapTS="AvgYr"; see config.py).

Resolution is config.RES_FACTOR, overridable with --res-factor: 10 simulates
every 10th cell of the 0.01-degree grid (~10 km). Results of different
resolutions go to different folders and never mix.

Restartable: each run's CSVs live in their own folder,
    output/csv/RES_<f>/<SSP>_<period>_<years>_SIM_<start>_<end>_specId_<id>_<cat>/
and a point with a CSV is never resubmitted. Points still missing after a
round are resubmitted, up to config.MAX_RETRY_ROUNDS rounds, until at most
config.MAX_MISSING remain or a round recovers nothing. Points with any
missing input (outside the input masks, zero maxAbgMF, no TYF parameters for
the configuration) are skipped and counted, not submitted.

Every run appends a line to output/run_log.csv.

Usage
-----
    python Step_02_run_fullcam.py --dry-run --limit 3        # build 3 PLOs, no API
    python Step_02_run_fullcam.py --limit 20 --ssps SSP245 --periods mid --species 8:Block
    python Step_02_run_fullcam.py --res-factor 20            # whole design, ~20 km
    python Step_02_run_fullcam.py                            # config.RES_FACTOR
"""

from __future__ import annotations

import argparse
import csv
import os
import time
from datetime import datetime

import numpy as np
from joblib import Parallel, delayed
from tqdm.auto import tqdm

import config as K
from fullcam import api, grid, inputs, plo


def parse_species(items):
    """['8:Block', '7'] -> {8: ['Block'], 7: [all of 7's configurations]}."""
    if not items:
        return K.SPECIES_GEOMETRY
    out = {}
    for it in items:
        sid, _, cat = it.partition(":")
        sid = int(sid)
        cats = [cat] if cat else K.SPECIES_GEOMETRY[sid]
        out.setdefault(sid, []).extend(cats)
    return out


def log_run(row):
    K.OUT.mkdir(parents=True, exist_ok=True)
    path = K.OUT / "run_log.csv"
    rows = []
    if path.exists():
        with open(path, newline="") as fh:
            rows = list(csv.DictReader(fh))
    fields = list(row)
    for r in rows:                       # keep columns of older log lines
        fields += [k for k in r if k not in fields]
    rows.append(row)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, restval="")
        w.writeheader()
        w.writerows(rows)


def run_one(pts, site, spec, ssp, period, specId, specCat, args, hdr):
    p = K.PERIODS[period]
    start, end = p["sim_start"], p["sim_start"] + K.SIM_LENGTH
    dst = K.csv_dir(ssp, period, specId, specCat, args.res_factor)
    g, r = spec.get(specCat, (None, None))
    if g is None:
        raise SystemExit("no TYF parameters for specId %d %s" % (specId,
                                                                 specCat))
    ok = site["valid"] & np.isfinite(g) & np.isfinite(r)
    idx = np.flatnonzero(ok)
    if args.limit:
        idx = idx[:args.limit]
    names = np.array([K.csv_name(ssp, period, specId, specCat,
                                 args.res_factor, x, y)
                      for x, y in zip(pts.x, pts.y)])
    tag = K.run_tag(ssp, period, specId, specCat)

    def build(i):
        return plo.assemble(pts.x.iat[i], pts.y.iat[i],
                            inputs.point(site, i),
                            inputs.species_point(spec, i),
                            specId, specCat, start, end)

    if args.dry_run:
        out = K.OUT / "plo_samples" / tag
        out.mkdir(parents=True, exist_ok=True)
        for i in idx[:max(args.limit or 3, 1)]:
            (out / names[i].replace(".csv", ".plo")).write_text(
                build(i), encoding="utf-8")
        print("  dry run: wrote %d PLO files to %s" % (min(len(idx),
              max(args.limit or 3, 1)), out))
        return
    dst.mkdir(parents=True, exist_ok=True)

    blocked = []                 # set by the first HTTP 403; stops the run

    def one(i):
        if blocked:              # queued points are dropped, not sent
            return False
        try:
            return api.simulate(build(i), dst / names[i], hdr)
        except api.Blocked as exc:
            blocked.append(str(exc))
            return False
        except Exception:
            return False

    t0 = time.time()
    previous = None
    for rnd in range(1, K.MAX_RETRY_ROUNDS + 1):
        if blocked:
            break
        done = set(os.listdir(dst))
        todo = [i for i in idx if names[i] not in done]
        # Round 1 always submits; after that, stop once few enough remain or
        # a round recovered nothing.
        if not todo or (rnd > 1 and (len(todo) <= K.MAX_MISSING
                                     or len(todo) == previous)):
            break
        previous = len(todo)
        print("  round %d: %s points to submit" % (rnd, format(len(todo), ",")))
        for _ in tqdm(Parallel(n_jobs=args.workers, backend="threading",
                               return_as="generator_unordered")(
                delayed(one)(i) for i in todo), total=len(todo), leave=False):
            if blocked:
                break
    done = set(os.listdir(dst))
    n_done = int(sum(names[i] in done for i in idx))
    row = {"time": datetime.now().isoformat(timespec="seconds"),
           "res_factor": args.res_factor, "run": tag,
           "land_points": len(pts), "valid_points": int(ok.sum()),
           "requested": len(idx), "done": n_done,
           "missing": len(idx) - n_done,
           "minutes": round((time.time() - t0) / 60, 1),
           "stopped": "blocked by the API" if blocked else ""}
    log_run(row)
    print("  %s: %s of %s done, %s missing (%.1f min)"
          % (tag, format(n_done, ","), format(len(idx), ","),
             format(len(idx) - n_done, ","), row["minutes"]))
    if blocked:
        raise SystemExit(
            "\nSTOPPED %s: blocked by the FullCAM API (%s).\n"
            "Every point with a CSV is kept. Restart the same command once "
            "the block is lifted (fewer --workers is gentler on the API)."
            % (datetime.now().isoformat(timespec="seconds"), blocked[0]))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--res-factor", type=int, default=K.RES_FACTOR,
                    help="simulate every Nth 0.01-degree cell (10 ~ 10 km)")
    ap.add_argument("--periods", nargs="+", default=list(K.PERIODS),
                    choices=list(K.PERIODS))
    ap.add_argument("--ssps", nargs="+", default=K.SSPS, choices=K.SSPS)
    ap.add_argument("--species", nargs="+", default=None,
                    help="e.g. 8 or 8:Block 7:BeltH (default: all)")
    ap.add_argument("--region", default=K.REGION, choices=["ALL", "LUTO"])
    ap.add_argument("--workers", type=int, default=K.N_WORKERS)
    ap.add_argument("--limit", type=int, default=None,
                    help="only the first N valid points of each run (testing)")
    ap.add_argument("--dry-run", action="store_true",
                    help="write PLO files to output/plo_samples, submit nothing")
    args = ap.parse_args()

    species = parse_species(args.species)
    pts = grid.points(args.res_factor, args.region)
    n_runs = len(args.periods) * len(args.ssps) * sum(map(len,
                                                          species.values()))
    print("resolution factor %d (%s region): %s land points; %d runs; up to "
          "%s API calls"
          % (args.res_factor, args.region, format(len(pts), ","), n_runs,
             format(len(pts) * n_runs if not args.limit
                    else args.limit * n_runs, ",")))
    hdr = None if args.dry_run else api.headers()

    for period in args.periods:
        for ssp in args.ssps:
            site = inputs.site_table(ssp, period, pts)
            print("\n%s %s: inputs sampled, %s of %s points valid"
                  % (ssp, period, format(int(site["valid"].sum()), ","),
                     format(len(pts), ",")))
            for specId, cats in species.items():
                spec = inputs.species_table(specId, pts)
                for specCat in cats:
                    print("%s %s specId %d %s" % (ssp, period, specId,
                                                  specCat))
                    run_one(pts, site, spec, ssp, period, specId, specCat,
                            args, hdr)


if __name__ == "__main__":
    main()

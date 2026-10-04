"""
Step 1 - check every prepared input before a single API call is made.

For each period (mid, late), SSP and variable it reports whether the file
exists, its grid and number of bands, the share of land points (at the chosen
resolution) with a finite value, and the value range, and flags anything
outside a plausible range. It also prints how many points and API calls a run
at that resolution means. Exits non-zero if any input is missing or wrong.

    avgAirTemp    deg C, monthly            -10 .. 45
    rainFall      mm per month               0 .. 2000
    openPanEvap   mm per month               0 .. 700
    forestProdIx  FPI index                  0 .. 40
    maxAbgMF      t DM / ha                  0 .. 3500

Run
---
    python Step_01_check_inputs.py [--res-factor 10]
"""

import argparse

import numpy as np

import config as K
from fullcam import grid
from fullcam.inputs import _sample, input_path, read_input

RANGES = {"avgAirTemp": (-10, 45), "rainFall": (0, 2000),
          "openPanEvap": (0, 700), "forestProdIx": (0, 40),
          "maxAbgMF": (0, 3500)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--res-factor", type=int, default=K.RES_FACTOR)
    ap.add_argument("--periods", nargs="+", default=list(K.PERIODS))
    ap.add_argument("--ssps", nargs="+", default=K.SSPS)
    args = ap.parse_args()

    pts = grid.points(args.res_factor)
    n_cfg = sum(len(v) for v in K.SPECIES_GEOMETRY.values())
    print("resolution factor %d: %s land points; %d species configurations"
          % (args.res_factor, format(len(pts), ","), n_cfg))
    print("a full run = %s points x %d SSPs x %d periods x %d configs = %s "
          "API calls\n" % (format(len(pts), ","), len(args.ssps),
                           len(args.periods), n_cfg,
                           format(len(pts) * len(args.ssps) * len(args.periods)
                                  * n_cfg, ",")))
    bad = 0
    for period in args.periods:
        for ssp in args.ssps:
            for var in K.MONTHLY_VARS + K.ANNUAL_VARS:
                p = input_path(var, ssp, period)
                tag = "%-5s %-7s %-13s" % (period, ssp, var)
                if not p.exists():
                    print("%s MISSING  %s" % (tag, p))
                    bad += 1
                    continue
                a = read_input(var, ssp, period)
                nb = a.shape[0]
                want = 12 if var in K.MONTHLY_VARS else 1
                s = _sample(a, pts)
                fin = np.isfinite(s).all(axis=1)
                lo, hi = (float(np.nanmin(s)), float(np.nanmax(s))) \
                    if fin.any() else (np.nan, np.nan)
                rlo, rhi = RANGES[var]
                flag = []
                if nb != want:
                    flag.append("%d bands, expected %d" % (nb, want))
                if not (rlo <= lo and hi <= rhi):
                    flag.append("values outside %g..%g" % (rlo, rhi))
                if flag:
                    bad += 1
                print("%s %s  bands %2d  finite %5.1f%%  range %9.3f .. %9.3f  %s"
                      % (tag, "BAD " if flag else "ok  ", nb, 100 * fin.mean(),
                         lo, hi, "; ".join(flag)))
    if bad:
        raise SystemExit("\n%d input problem(s) - fix before Step_02 (or edit "
                         "config.INPUT_FILES)" % bad)
    print("\nall inputs present and plausible")


if __name__ == "__main__":
    main()

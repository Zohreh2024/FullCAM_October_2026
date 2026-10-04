"""
Step 0 - extract the soil layers once.

The soil inputs - clay fraction and the initial soil carbon pools and soil
moisture deficit - do not change between scenarios or periods. They live in
the earlier toolkit's siteinfo_cache.nc (config.OLD_SITEINFO_CACHE), a
~100 GB-in-memory file that also holds 54 years of historical climate. Only
the five 2-D soil layers are read, lazily, and written to data/soil_init.nc
on the same 0.01-degree grid.

    clayFrac      soil clay fraction (0-1)
    rpmaCMInitF   initial resistant plant material carbon
    humsCMInitF   initial humus carbon
    inrtCMInitF   initial inert carbon
    TSMDInitF     initial topsoil moisture deficit

Run
---
    "C:\\ProgramData\\Anaconda3\\envs\\JinzhuLuto\\python.exe" Step_00_prepare_soil.py
"""

import sys

import numpy as np
import xarray as xr

import config as K
from fullcam.inputs import SOIL_VARS


def main():
    if K.SOIL_CACHE.exists() and "--overwrite" not in sys.argv:
        print("%s exists - kept (--overwrite to rebuild)" % K.SOIL_CACHE)
        return
    src = xr.open_dataset(K.OLD_SITEINFO_CACHE, chunks={})
    missing = [v for v in SOIL_VARS if v not in src]
    if missing:
        raise SystemExit("not in %s: %s" % (K.OLD_SITEINFO_CACHE, missing))
    ds = src[SOIL_VARS].load().astype("float32")
    if ds.sizes["y"] != 3364 or ds.sizes["x"] != 4071:
        raise SystemExit("soil layers are not on the 0.01-degree grid")
    K.DATA.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(K.SOIL_CACHE, encoding={v: {"zlib": True, "complevel": 4}
                                         for v in SOIL_VARS})
    for v in SOIL_VARS:
        a = ds[v].values
        print("  %-12s finite cells %9d  median %.4g"
              % (v, int(np.isfinite(a).sum()), float(np.nanmedian(a))))
    print("wrote %s" % K.SOIL_CACHE)


if __name__ == "__main__":
    main()

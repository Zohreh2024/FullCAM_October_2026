"""
Step 3 - turn each run's per-point CSVs into a NetCDF and GeoTIFFs.

For every run folder under output/csv/RES_<f>/ (one per SSP x period x
species x configuration) the CSVs are read and placed on the coarse grid of
that resolution (fullcam.grid.out_grid - the same cells Step_02 simulated),
giving three carbon stocks by year:

    TREE_C_HA     C mass of plants  (t C / ha)
    DEBRIS_C_HA   C mass of debris  (t C / ha)
    SOIL_C_HA     C mass of soil    (t C / ha)

for every year from the simulation start to its end (2050-2150 mid,
2085-2185 late).

Writes, per run,
    output/netcdf/RES_<f>/carbonstock_<run>.nc     dims VARIABLE, YEAR, y, x
    output/tiff/RES_<f>/<VAR>_<run>.tif            one band per year, band
                                                   descriptions are the years
EPSG:4283, NaN where a point was not simulated. A run whose NetCDF is newer
than all its CSVs is skipped unless --overwrite. Read the NetCDF with
xr.open_dataset(path)["data"] (it also carries the CRS in spatial_ref).

Memory: one run is held as 3 x 101 x rows x cols float32 - about 40 MB at
factor 20, 170 MB at 10, 17 GB at factor 1.

Usage
-----
    python Step_03_results_to_netcdf_tiff.py                    # config.RES_FACTOR
    python Step_03_results_to_netcdf_tiff.py --res-factor 20 --overwrite
"""

from __future__ import annotations

import argparse
import re

import numpy as np
import pandas as pd
import xarray as xr
from joblib import Parallel, delayed

import config as K
from fullcam import grid

RUN_RE = re.compile(r"^(SSP\d+)_(mid|late)_[\d-]+_SIM_(\d+)_(\d+)"
                    r"_specId_(\d+)_(\w+)$")


def read_csv(path, years):
    df = pd.read_csv(path, usecols=["Year"] + list(K.CARBON_VARS))
    df = (df[df.Year >= years[0]].rename(columns=K.CARBON_VARS)
          .set_index("Year").reindex(years))
    return df[list(K.CARBON_VARS.values())].to_numpy("float32")


def write_geotiff(a, path, years, trans, crs):
    import rasterio
    with rasterio.open(path, "w", driver="GTiff", dtype="float32",
                       width=a.shape[2], height=a.shape[1], count=a.shape[0],
                       crs=crs, transform=trans, nodata=np.nan,
                       compress="lzw", tiled=True, blockxsize=256,
                       blockysize=256) as d:
        d.write(a)
        for b, y in enumerate(years, 1):
            d.set_band_description(b, str(y))


def convert(run_dir, pts, xs, ys, trans, crs, res_factor, overwrite):
    m = RUN_RE.match(run_dir.name)
    if not m:
        return "skipped (name) %s" % run_dir.name
    start, end = int(m.group(3)), int(m.group(4))
    years = np.arange(start, end + 1)
    nc_dir = K.NC_DIR / ("RES_%d" % res_factor)
    tif_dir = K.TIF_DIR / ("RES_%d" % res_factor)
    nc_dir.mkdir(parents=True, exist_ok=True)
    tif_dir.mkdir(parents=True, exist_ok=True)
    nc = nc_dir / ("carbonstock_%s.nc" % run_dir.name)
    ssp, period, specId, specCat = (m.group(1), m.group(2), int(m.group(5)),
                                    m.group(6))
    if specCat not in K.SPECIES_GEOMETRY.get(specId, []):
        return "skipped (not in config.SPECIES_GEOMETRY) %s" % run_dir.name
    files = sorted(run_dir.glob("*.csv"))
    if not files:
        return "empty %s" % run_dir.name
    if (nc.exists() and not overwrite
            and nc.stat().st_mtime > max(f.stat().st_mtime for f in files)):
        return "up to date %s" % run_dir.name

    key = {K.csv_name(ssp, period, specId, specCat, res_factor, x, y): (r, c)
           for x, y, r, c in
           zip(pts.x, pts.y, pts.row_r, pts.col_r)}
    nv = len(K.CARBON_VARS)
    out = np.full((nv, len(years), len(ys), len(xs)), np.nan, "float32")
    loc = [key.get(f.name) for f in files]
    use = [(f, l) for f, l in zip(files, loc) if l is not None]
    vals = Parallel(n_jobs=16, backend="threading")(
        delayed(read_csv)(f, years) for f, _ in use)
    for (f, (r, c)), v in zip(use, vals):
        out[:, :, r, c] = v.T
    da = xr.DataArray(out, dims=("VARIABLE", "YEAR", "y", "x"),
                      coords={"VARIABLE": list(K.CARBON_VARS.values()),
                              "YEAR": years, "y": ys, "x": xs},
                      name="data")
    da.rio.write_crs(crs, inplace=True)
    da.rio.write_transform(trans, inplace=True)
    da.attrs.update(units="t C / ha", run=run_dir.name,
                    res_factor=res_factor, points=len(use))
    da.to_netcdf(nc, encoding={"data": {"zlib": True, "complevel": 5}})
    for k, var in enumerate(K.CARBON_VARS.values()):
        write_geotiff(out[k], tif_dir / ("%s_%s.tif" % (var, run_dir.name)),
                      years, trans, crs)
    return "%s: %s points -> %s" % (run_dir.name, format(len(use), ","),
                                    nc.name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--res-factor", type=int, default=K.RES_FACTOR)
    ap.add_argument("--region", default=K.REGION, choices=["ALL", "LUTO"])
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()
    import rioxarray  # noqa: F401  registers .rio

    root = K.CSV_DIR / ("RES_%d" % args.res_factor)
    runs = sorted(p for p in root.glob("*") if p.is_dir()) if root.exists() \
        else []
    if not runs:
        raise SystemExit("no runs under %s - run Step_02 at this resolution "
                         "first" % root)
    pts = grid.points(args.res_factor, args.region)
    xs, ys, trans, crs = grid.out_grid(args.res_factor)
    for run_dir in runs:
        print(convert(run_dir, pts, xs, ys, trans, crs, args.res_factor,
                      args.overwrite))


if __name__ == "__main__":
    main()

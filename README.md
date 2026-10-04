# Run_FullCAM/

Runs FullCAM (2024 REST simulator) on the mid- and late-century FullCAM inputs,
for every SSP and every species × planting configuration, at a resolution you
choose. The results are converted to NetCDF and GeoTIFF.

Adapted from the earlier toolkit in
`00_previous_attempt/Run_Automated_fullcam/.../FullCAM_REST_API_GET_DATA-main`:
`RUN_FullCAM2024.py`, `FullCAM2NC.py` and `tools/__init__.py`. The PLO
templates and species TYF layers are copied from there.

## The design

| period | inputs averaged over | simulation | years |
|---|---|---|---|
| `mid` | 2035–2064 | 2050 → 2150 | 101 |
| `late` | 2070–2099 | 2085 → 2185 | 101 |

The design is 4 SSPs (126, 245, 370, 585) × 2 periods × 7 species ×
configuration pairs:

| specId | species | configurations |
|---|---|---|
| 7 | Environmental plantings | BeltH, BlockES, Water |
| 8 | Carbon plantings (*Eucalyptus globulus*) | Belt, Block |
| 23 | Mallee plantings | BeltHW, BlockES |

That makes **56 runs**, one FullCAM call per point per run.

**What an input is.** Each input is one average year: 12 monthly values of
`avgAirTemp`, `rainFall` and `openPanEvap`, and one value of `forestProdIx`
and `maxAbgMF`.
- The PLO time series use `tExtrapTS="AvgYr"`, so FullCAM repeats that year
  for all 100 simulated years. Each run is the period's climate held constant,
  not a transient projection.
- `yr0TS` is the simulation start year.
- `fpiAvgLT` is set to the period's FPI, as in the earlier future runs, so
  `maxAbgMF` acts directly as the site maximum.
- Soil clay and the initial soil pools come from the historical site cache,
  as before.

## Resolution

`RES_FACTOR` in `config.py`, or `--res-factor N` on the command line, runs
every Nth cell of the 0.01° grid:

| factor | spacing | land points | API calls (56 runs) |
|---|---|---|---|
| 50 | ~50 km | 2,783 | 155,848 |
| 20 | ~20 km | 17,382 | 973,392 |
| **10** (default) | ~10 km | 69,564 | 3,895,584 |
| 5 | ~5 km | 278,275 | 15,583,400 |
| 1 | ~1 km | 6,956,407 | 389,558,792 |

Start coarse. Each resolution writes to its own `RES_<f>` folders, so runs at
different resolutions never mix, and Step_03 must use the same factor.

## Inputs you must provide

`config.INPUT_FILES`, under `FullCAM_input_CSIRO_data/Mid/` (2035-2064) and
`Late/` (2070-2099):

| FullCAM variable | file | variable read |
|---|---|---|
| `avgAirTemp` | `avgAirTemp_<SSP>_<years>.nc` | `avgAirTemp` (12 months, °C) |
| `rainFall` | `rainfall_<SSP>_<years>.nc` | `rainfall` (12 months, mm) |
| `openPanEvap` | `openPanEvap_<SSP>_<years>.nc` | `openPanEvap` (12 months, mm) |
| `forestProdIx` | `forestProdIx_<SSP>_<years>.nc` | `fpi_mean` (mean of the 30 annual random-forest FPI) |
| `maxAbgMF` | `maxAbgMF_<SSP>_<years>.nc` | its one gridded variable (t DM/ha) |

Rainfall and pan evaporation are ANUClimate × the CSIRO change factor, already
in mm per month. All files must be on the 0.01° NLUM grid
(4071 × 3364). A `.tif` with the same stem is also accepted. Step_01 lists
every missing or implausible file.

## Running it

```powershell
$py = "C:\ProgramData\Anaconda3\envs\JinzhuLuto\python.exe"
cd Run_FullCAM
& $py Step_00_prepare_soil.py                    # once; done (data/soil_init.nc)
& $py Step_01_check_inputs.py --res-factor 10    # inputs present? how many calls?
& $py Step_02_run_fullcam.py --dry-run --limit 3 # writes PLO files only, no API
& $py Step_02_run_fullcam.py --res-factor 10     # the whole design
& $py Step_03_results_to_netcdf_tiff.py --res-factor 10
```

Step_02 options:
- `--periods mid`, `--ssps SSP245`, `--species 8:Block 7` (a species alone
  means all its configurations) to run part of the design;
- `--limit N` for the first N points of each run;
- `--workers` for parallel requests (default 32);
- `--region LUTO` for the LUTO study area only.

Step_02 needs the `FULLCAM_API_KEY` environment variable. It is
**restartable**: a point that already has a CSV is never resubmitted. Missing
points are resubmitted in up to 10 rounds, and every run appends a line to
`output/run_log.csv` with its counts and minutes. Points with any missing
input are skipped and counted, not sent.

## Outputs

```
output/csv/RES_<f>/<run>/df_<lon>_<lat>_specId_<id>_specCat_<config>_<SSP>_InData_<y0>_<y1>_SIM_YR_<start>_<end>.csv
                                                  FullCAM's table, one per point, e.g.
                                                  df_112.93_-25.62_specId_7_specCat_BeltH_SSP126_InData_2035_2064_SIM_YR_2050_2150.csv
                                                  InData = years the inputs average; SIM_YR = simulated years
output/netcdf/RES_<f>/carbonstock_<run>.nc        VARIABLE x YEAR x y x
output/tiff/RES_<f>/<VAR>_<run>.tif               one band per year (band name = year)
output/run_log.csv
<run> = <SSP>_<period>_<years>_SIM_<start>_<end>_specId_<id>_<cat>
        e.g. SSP245_mid_2035-2064_SIM_2050_2150_specId_8_Block
```

The variables are `TREE_C_HA`, `DEBRIS_C_HA` and `SOIL_C_HA`, all t C/ha.
Files are EPSG:4283 on the coarse grid, NaN where a point was not simulated.

## Files

| file | what it does |
|---|---|
| `config.py` | every setting: periods, SSPs, resolution, species, paths, API |
| `fullcam/plo.py` | builds a PLO file from one point's values and the templates |
| `fullcam/inputs.py` | reads the inputs and samples them at the run's points |
| `fullcam/grid.py` | the point set for a resolution, and the matching output grid |
| `fullcam/api.py` | posts a PLO and saves the CSV (retries, atomic write) |
| `Step_00_prepare_soil.py` | soil layers from the old site cache → `data/soil_init.nc` |
| `Step_01_check_inputs.py` | checks every input and prints the size of the run |
| `Step_02_run_fullcam.py` | the runs |
| `Step_03_results_to_netcdf_tiff.py` | CSVs → NetCDF + GeoTIFF |
| `templates/` | PLO section templates (copied unchanged) |
| `data/species/` | TYF growth parameters for species 7, 8, 23 (copied) |
| `data/lumap.tif` | the 0.01° land template (copied) |

## Tested

On stand-in inputs (the existing 2041–2060 files), factor 20, SSP245, both
periods, species 8 Block and 7 BeltH, 3 points each:
- all 12 FullCAM calls returned;
- the CSVs cover 2050–2150 and 2085–2185;
- the NetCDF and the 101-band GeoTIFFs place each point in the right cell,
  with values matching the CSVs.

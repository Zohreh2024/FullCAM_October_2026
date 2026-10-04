"""
Settings shared by every step of Run_FullCAM. Change things here, not in the
step scripts; the run and the conversion must agree on all of it, because
together these values identify the result files.

Most of them can also be overridden on the command line of Step_02 / Step_03
(e.g. `--res-factor 10`), which is the easy way to try a coarse run first.
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                                   # 000_Zohreh_paper_1_refactor

# --------------------------------------------------------------------------- #
# Time: two climate periods, each run from a single start year for 100 years
# --------------------------------------------------------------------------- #
PERIODS = {
    # period : climate window averaged in the inputs, and the simulation start
    "mid":  {"data_years": "2035-2064", "sim_start": 2050, "folder": "Mid"},
    "late": {"data_years": "2070-2099", "sim_start": 2085, "folder": "Late"},
}
SIM_LENGTH = 100
"""Years simulated after the start year: 2050-2150 (mid), 2085-2185 (late).

Each input is ONE average year (12 monthly values for climate, one value for
FPI and M). The site time series use tExtrapTS="AvgYr", so FullCAM repeats that
average year for every simulated year - the run is the mid- or late-century
climate held constant for 100 years, not a transient projection. yr0TS of the
series is the simulation start year.
"""

SSPS = ["SSP126", "SSP245", "SSP370", "SSP585"]

# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
RES_FACTOR = 10
"""Every RES_FACTOR-th cell of the 0.01-degree grid is simulated.

    RES_FACTOR   spacing           land points   API calls, full design (x56)
         1       0.01 deg ~1 km     6,956,407      389,558,792
         2       0.02 deg ~2 km     1,739,147       97,392,232
         5       0.05 deg ~5 km       278,275       15,583,400
        10       0.10 deg ~10 km       69,564        3,895,584
        20       0.20 deg ~20 km       17,382          973,392
        50       0.50 deg ~50 km        2,783          155,848

The full design is 4 SSPs x 2 periods x 7 species-configurations = 56 runs,
one API call per point per run. Start coarse (20 or 10), check the maps, then
refine. Step_01 and Step_02 print the exact count before submitting anything.
Step_03 must use the same factor.
"""

REGION = "ALL"
"""'ALL' = every land cell of continental Australia; 'LUTO' = LUTO study area
only (data/lumap.tif >= 0)."""

# --------------------------------------------------------------------------- #
# Vegetation and planting configurations
# --------------------------------------------------------------------------- #
SPECIES_GEOMETRY = {
    7:  ["BeltH", "BlockES", "Water"],       # Environmental plantings
    8:  ["Belt", "Block"],                   # Carbon plantings (E. globulus)
    23: ["BeltHW", "BlockES"],               # Mallee plantings
}
"""The species x planting configurations to run: 7 runs in all. templates/
and data/species/ also hold 7/BeltL, 23/BeltHN and 23/BeltL, which are not
needed and are left out on purpose."""

SPECIES_NAME = {7: "Environmental plantings",
                8: "Carbon plantings (Eucalyptus globulus)",
                23: "Mallee plantings"}
SPECIES_SHORT = {7: "EnvPlantings", 8: "CarbonPlantings", 23: "Mallee"}
"""Species tag used in the CSV file names."""

# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
INPUT_DIR = ROOT / "FullCAM_input_CSIRO_data"
INPUT_FILES = {
    # FullCAM variable : (file under INPUT_DIR/<Mid|Late>/, variable inside)
    "avgAirTemp":   ("avgAirTemp_{ssp}_{years}.nc",         "avgAirTemp"),
    "rainFall":     ("rainfall_{ssp}_{years}.nc",           "rainfall"),
    "openPanEvap":  ("openPanEvap_{ssp}_{years}.nc",        "openPanEvap"),
    "forestProdIx": ("forestProdIx_{ssp}_{years}.nc",       "fpi_mean"),
    "maxAbgMF":     ("maxAbgMF_{ssp}_{years}.nc",           None),
}
"""Where each prepared input lives, e.g.

    FullCAM_input_CSIRO_data/Mid/rainfall_SSP245_2035-2064.nc

and which variable inside the file is the period average:
- rainfall and openPanEvap are ANUClimate 1985-2014 x the CSIRO change
  factor, already in mm per month.
- forestProdIx files hold one layer, `fpi_mean`, the mean of the 30 annual
  random-forest FPI rasters (Random_forest_CSIRO/output/netcdf_period_means).
- maxAbgMF files hold one layer whose name carries a lower-case ssp
  (e.g. maxAbgMF_ssp245_2035-2064_mean); None means "the one data variable
  on the grid", skipping spatial_ref.
A .tif with the same stem is accepted if the .nc is absent (12 bands for the
monthly variables). Step_01 reports every file it cannot find."""

MONTHLY_VARS = ["avgAirTemp", "rainFall", "openPanEvap"]
ANNUAL_VARS = ["forestProdIx", "maxAbgMF"]

FPI_AVG_LT = "period"
"""fpiAvgLT in the PLO. 'period' sets it to the period's forestProdIx, as the
earlier future runs did, so growth is not rescaled by an FPI anomaly and the
period's maxAbgMF acts directly as the site maximum."""

# Static inputs made by Step_00
DATA = HERE / "data"
LUMAP = DATA / "lumap.tif"
SPECIES_DIR = DATA / "species"
SOIL_CACHE = DATA / "soil_init.nc"
OLD_SITEINFO_CACHE = Path(
    r"N:\Current-Users\ZOHREH-KALAHROUDI\00_previous_attempt"
    r"\Run_Automated_fullcam\FullCAM_Zohreh\FullCAM_REST_API_GET_DATA-main"
    r"\FullCAM_REST_API_GET_DATA-main\data\data_assembled\siteinfo_cache.nc")
"""Source of the soil layers (clay fraction and initial soil carbon pools),
which do not change between scenarios. Step_00 extracts them once."""

TEMPLATES = HERE / "templates"

# --------------------------------------------------------------------------- #
# FullCAM REST API
# --------------------------------------------------------------------------- #
API_URL = ("https://api.climatechange.gov.au/climate/carbon-accounting/2024"
           "/plot/v1/2024/fullcam-simulator/run-plotsimulation")
API_KEY_ENV = "FULLCAM_API_KEY"
N_WORKERS = 32               # parallel requests
TRY_NUMBER = 5               # attempts per point, with exponential back-off
TIMEOUT = 60                 # seconds per request
MAX_RETRY_ROUNDS = 10        # resubmission rounds per run
MAX_MISSING = 10             # stop resubmitting once this few points remain

# --------------------------------------------------------------------------- #
# Outputs
# --------------------------------------------------------------------------- #
OUT = HERE / "output"
CSV_DIR = OUT / "csv"
NC_DIR = OUT / "netcdf"
TIF_DIR = OUT / "tiff"
CARBON_VARS = {                                  # CSV column -> output name
    "C mass of plants  (tC/ha)": "TREE_C_HA",
    "C mass of debris  (tC/ha)": "DEBRIS_C_HA",
    "C mass of soil  (tC/ha)": "SOIL_C_HA",
}


def run_tag(ssp, period, specId, specCat):
    """Name of one run: scenario, period, species and configuration."""
    p = PERIODS[period]
    return ("%s_%s_%s_SIM_%d_%d_specId_%d_%s"
            % (ssp, period, p["data_years"], p["sim_start"],
               p["sim_start"] + SIM_LENGTH, specId, specCat))


def csv_dir(ssp, period, specId, specCat, res_factor):
    """One folder per run and resolution, so no folder holds millions of
    files and runs at different resolutions never mix."""
    return CSV_DIR / ("RES_%d" % res_factor) / run_tag(ssp, period, specId,
                                                       specCat)


def csv_name(ssp, period, specId, specCat, res_factor, lon, lat):
    """One point's CSV, named so it identifies its run on its own, e.g.
    df_112.93_-25.62_specId_7_specCat_BeltH_SSP126_InData_2035_2064_SIM_YR_2050_2150.csv
    (InData = the years the inputs average, SIM_YR = the simulated years).
    The resolution is not in the name; it is the RES_<f> folder."""
    p = PERIODS[period]
    y0, y1 = p["data_years"].split("-")
    return ("df_%s_%s_specId_%d_specCat_%s_%s_InData_%s_%s_SIM_YR_%d_%d.csv"
            % (lon, lat, specId, specCat, ssp, y0, y1, p["sim_start"],
               p["sim_start"] + SIM_LENGTH))

# ICOS Soil Moisture & Flux Data Download Scripts

This directory contains scripts to discover and download ICOS ecosystem (ES) station data at Level 2: surface soil moisture (SWC) and carbon fluxes (GPP, NEE, ...).

- **ETC L2 Meteo** — meteorological variables, including soil water content (SWC - Soil Water Content) at various depths
- **ETC L2 FluxNet** — ecosystem carbon fluxes in FluxNet format (`GPP_NT_CUT_REF`, `NEE_CUT_REF`, `RECO_NT_CUT_REF`, ...). **This is where GPP lives** (source unit `µmol m-2 s-1`).
- **ETC L2 Fluxes** — ecosystem fluxes (`NEE`, `CO2`, `H`, `H2O`, `LE`, ...; source unit `g C/m2/s`). This product does **not** contain GPP.

ICOS (Integrated Carbon Observation System) provides soil moisture measurements (SWC - Soil Water Content) at various depths as part of their ETC L2 Meteo data product, and carbon fluxes (GPP, NEE, H, LE) in the ETC L2 Fluxnet / ETC L2 Fluxes data products. These scripts help you:

1. **Discover** which stations have which variables (no authentication required)
2. **Download** the time series data you need, including soil moisture (SWC) and GPP **combined in a single output file** (authentication required)

## Prerequisites

### 1. Virtual Environment

A virtual environment exists at `./evaluation/.venv` with the required packages. To recreate it:

```bash
# Ensure uv is installed (or use pip/venv as alternative)
uv venv .venv
uv pip install -r requirements.txt
```

Or with standard Python:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The `requirements.txt` file lists the dependencies:
- `icoscp==0.2.3`
- `icoscp-core==0.3.13`
- `pandas==3.0.5`
- `pint==0.25.3` (unit conversion, see below)
- `pytest==9.1.1`

### 2. Authentication

**Metadata discovery does NOT require authentication**, but **downloading actual data DOES require authentication**.

To authenticate, you need ICOS Carbon Portal credentials. Choose one method:

#### Method 1: Credentials File (Recommended for local use)
```bash
python -c "from icoscp_core.icos import auth; auth.init_config_file()"
```
This will prompt for your username/password and store an encrypted version locally.

#### Method 2: API Token via Command Line (Quick & Temporary)
Get a token from your "My Account" page at https://meta.icos-cp.eu/ and use it directly:

1. Log in to https://meta.icos-cp.eu/
2. Click on "My Account" (top right)
3. Copy the full token value (it starts with `cpauthToken=`)
4. Use it in the command:
```bash
python download.py --cpauthtoken cpauthToken=[the-actual-token-value]
```

**Important**: Make sure to include the `cpauthToken=` prefix. The token looks like a long encoded string (e.g. `cpauthToken=WzE2OTY2NzQ5OD...]`).

**Note**: Tokens expire after approximately 27 hours.

#### Method 3: API Token in Code
```python
from icoscp_core.icos import bootstrap
cookie_token = 'cpauthToken=YOUR_TOKEN_HERE'
meta, data = bootstrap.fromCookieToken(cookie_token)
```

Full authentication documentation: https://icos-carbon-portal.github.io/pylib/icoscp/authentication/

## Scripts

### 1. metadata.py - Discover Stations and Their Data Objects

This script queries the ICOS Carbon Portal metadata service to find all ecosystem stations that have the requested Level 2 data product. By default it discovers **etcL2Meteo** (soil moisture) and **etcL2Fluxnet** (GPP/NEE) stations.

**Usage:**
```bash
python metadata.py                      # etcL2Meteo + etcL2Fluxnet
python metadata.py --datatype etcL2Meteo,etcL2Fluxes,etcL2Fluxnet
python metadata.py --variable-pattern GPP,NEE   # only stations with these variables
```

**Output (one CSV per data type, with station metadata + data object URIs):**
- `stations_soil_moisture.csv` (etcL2Meteo)
- `stations_fluxnet.csv` (etcL2Fluxnet - the product that contains GPP)
- `stations_flux.csv` (etcL2Fluxes - NEE/H/LE/CO2, no GPP)

### 2. download.py - Download ICOS Time Series Data

### 2. download.py - Download ICOS Time Series Data

This script downloads time series data (soil moisture, GPP, NEE, etc.) from the stations discovered by `metadata.py`.

**Usage**:
```bash
# Download only SWC_1 (default, from stations_soil_moisture.csv):
python download.py

# Download multiple variables (soil layers and/or fluxes such as GPP):
python download.py --variables SWC_1,SWC_2,GPP

# Download all soil layers ('SWC' matches SWC_1, SWC_2, ...):
python download.py --variables SWC

# Download GPP from the ETC L2 Fluxnet data objects (discover them first):
python metadata.py --datatype etcL2Fluxnet
python download.py --input-csv stations_fluxnet.csv --variables GPP_NT_VUT_REF

# Resample to daily means:
python download.py --variables SWC_1 --resample 1D

# Daily mean and standard deviation:
python download.py --variables SWC_1 --resample 1D --agg mean,std

# With authentication token:
python download.py --cpauthtoken cpauthToken=YOUR_TOKEN_HERE --variables SWC_1

# Limit the number of data objects processed (useful for testing):
python download.py --limit 5

# Specify input/output files:
python download.py --input-csv stations_soil_moisture.csv --output soil_data.csv

# Show help:
python download.py --help
```

**Options**:
- `--input-csv`: Input CSV file with station information (default: `stations_sm.csv`). Use `stations_combined.csv` to fetch variables from multiple data types (e.g. SWC and GPP) in one run
- `--output`: Output CSV file for time series data (default: `icos_timeseries.csv`)
- `--variables`: Comma-separated variable names to download (default: `SWC_1`). A bare family prefix matches all variants starting with `<prefix>_` (e.g., `SWC` matches `SWC_1`, `SWC_2`, ...; `GPP` matches all four `GPP_*_REF` model variants — prefer the explicit name `GPP_NT_CUT_REF`)
- `--resample`: Pandas resample rule applied after downloading (e.g., `1D` for daily). No resampling by default.
- `--agg`: Comma-separated aggregation functions used with `--resample` (default: `mean`)
- `--unit`: Target unit for a variable, `VAR:UNIT` (repeatable, e.g. `--unit GPP_NT_CUT_REF:gC/m2/h`). By default the `GPP*`/`NEE*`/`RECO*` columns of the FluxNet product are converted to `gC/m2/d`; all other variables keep their ICOS source unit
- `--no-unit-conversion`: Disable automatic unit conversion (keep the units as reported by ICOS, e.g. FluxNet GPP in `µmol m-2 s-1`)
- `--limit`: Maximum number of data objects to process (default: all)
- `--cpauthtoken`: ICOS Carbon Portal authentication token (use for temporary access without credentials file)

**How mixed variables work**: `download.py` matches each requested variable against the columns of each data object individually — a variable that a data object does not contain is simply skipped. So with `stations_combined.csv` and `--variables SWC_1,GPP_NT_CUT_REF`, the SWC values come from the ETC L2 Meteo data objects and the GPP values from the ETC L2 FluxNet data objects, all written into the **same output file**.

**Output**:
- A single CSV with TIMESTAMP as the index and one column per station-variable time series

**Output format**:
- Index: TIMESTAMP (pandas DatetimeIndex, written as the first CSV column)
- Columns: `STATION_ID_VARIABLE (unit)` (e.g., `FI-Lom_SWC_1 (m3/m3)`, `FI-Lom_GPP_NT_CUT_REF (gC/m2/d)`)
  - With `--resample` and multiple `--agg`: `STATION_ID_VARIABLE_AGG (unit)` (e.g., `FI-Lom_SWC_1_MEAN (m3/m3)`)
- Units: Inferred from ICOS data object metadata; for variables that are converted (GPP*/NEE*/RECO* columns by default) the target unit is shown instead
- Missing values: Empty cells where data is not available. Note that SWC and GPP come from different data objects, so their time spans may differ — the index is the union of timestamps.

**Sample output**:
```
TIMESTAMP,FI-Lom_SWC_1 (m3/m3),FI-Lom_GPP_NT_CUT_REF (gC/m2/d),...
2020-01-01 00:00:00,0.25,-10.7,...
2020-01-01 01:00:00,0.26,-8.3,...
```

## Unit conversion (`units.py`)

`download.py` uses [pint](https://pint.readthedocs.io/) to convert variable values to sensible target units before any resampling:

| Variables | Default target unit |
|-----------|---------------------|
| `GPP_NT_CUT_REF`, `GPP_NT_VUT_REF`, `GPP_DT_CUT_REF`, `GPP_DT_VUT_REF` | `gC/m2/d` (grams of carbon per m² per day) |
| `NEE_CUT_REF`, `NEE_VUT_REF`, `RECO_NT_CUT_REF`, `RECO_NT_VUT_REF` | `gC/m2/d` |
| GPP, NEE, RE, NBP (legacy names) | `gC/m2/d` |

- Other variables (e.g. SWC in `m3/m3`) keep the unit reported by ICOS.
- Molar source units (e.g. `mol C/m2/s`, or `µmol m-2 s-1` as reported by the FluxNet product) are converted with the standard atomic weight of carbon (12.011 g/mol). `µmol m-2 s-1 -> gC/m2/d` uses a factor of ≈1.0378 (1e-6 mol × 12.011 g/mol × 86400 s/d).
- A conversion is only applied when the source unit is known from the data object metadata and dimensionally compatible with the target; otherwise the variable is left as-is and a warning is printed.
- Column headers always show the unit the values are expressed in (e.g. `FI-Lom_GPP_NT_CUT_REF (gC/m2/d)`).

To use a different target unit, pass `--unit VAR:UNIT` (repeatable):

```bash
python download.py --input-csv stations_combined.csv --variables SWC_1,GPP_NT_CUT_REF \
    --unit GPP_NT_CUT_REF:gC/m2/h --output gpp_sm_timeseries.csv
```

To keep the ICOS source units (e.g. FluxNet GPP in `µmol m-2 s-1`), disable automatic conversion:

```bash
python download.py --variables GPP_NT_CUT_REF --no-unit-conversion
```

## Workflow

1. **Discover stations** (no authentication needed):
   ```bash
   python metadata.py
   ```
   This creates `stations_soil_moisture.csv` and `stations_fluxnet.csv` (see the product notes in *Data Information*).

2. **Review the output CSV files** to see which stations have which variables and their data object URIs.

3. **Authenticate** (if you want to download data):
   ```bash
   python -c "from icoscp_core.icos import auth; auth.init_config_file()"
   ```

4. **Download both in a single run**:
   ```bash
   # Download SWC_1 from all stations:
   python download.py

   # Download SWC_1, SWC_2, SWC_3 from all stations:
   python download.py --variables SWC_1,SWC_2,SWC_3

   # Download all soil layers using family prefix:
   python download.py --variables SWC

   # Download GPP from the ETC L2 Fluxnet data objects:
   python download.py --input-csv stations_fluxnet.csv --variables GPP_NT_VUT_REF

   # Resample to daily means:
   python download.py --variables SWC_1 --resample 1D

   # Daily mean and standard deviation:
   python download.py --variables SWC_1 --resample 1D --agg mean,std
   ```
   Add `--resample 1D` (and optionally `--agg mean,std`) for daily aggregates.

### Soil moisture only

```bash
python metadata.py --datatype etcL2Meteo
python download.py --variables SWC
```

### Fluxes only

```bash
# GPP, NEE, RECO (FluxNet-format L2 product):
python metadata.py --datatype etcL2Fluxnet
python download.py --input-csv stations_fluxnet.csv --variables GPP_NT_CUT_REF,NEE_CUT_REF

# NEE, CO2, H, H2O, LE (Fluxes product — no GPP):
python metadata.py --datatype etcL2Fluxes
python download.py --input-csv stations_flux.csv --variables NEE
```

## Data Information

### Soil Moisture Variables (SWC)
- **SWC_1, SWC_2, ...** - Soil Water Content at different depths
- The number of available levels varies by station (typically 1-7 levels)
- Values are typically in m³/m³ (volumetric water content)
- Product: **ETC L2 Meteo** (`etcL2Meteo`) - this product contains **no carbon fluxes**

### Flux Variables (GPP / NEE)

GPP is **not** in the ETC L2 Meteo product. The carbon flux products use
FluxNet-style variable names:

- **ETC L2 Fluxnet** (`etcL2Fluxnet`, 83 stations) - the product that contains GPP:
  - `GPP_NT_VUT_REF` - GPP from the night-time leg, VUT reference (standard choice; all 83 stations)
  - `GPP_NT_CUT_REF` - GPP, night-time leg, CUT reference (80 stations)
  - `GPP_DT_VUT_REF` / `GPP_DT_CUT_REF` - daytime GPP variants (80 / 77 stations)
  - `NEE_VUT_REF` / `NEE_CUT_REF` (+ `_QC` flag columns) - net ecosystem exchange
- **ETC L2 Fluxes** (`etcL2Fluxes`, 93 stations) - `NEE`, `H`, `LE`, `CO2` and `*_UNCLEANED` variants, but **no GPP**

Soil moisture and GPP can be combined per station: all 83 fluxnet stations also have ETC L2 Meteo data.

> **Gotcha:** requesting bare `GPP` matches all `GPP_*` variants in a data object
> (prefix matching). To get a single series, request the exact name, e.g. `GPP_NT_VUT_REF`.

### Data Format
- The source data is in ETC L2 format (Level 2, Quality Controlled)
- Time series are at the station's native reporting frequency
- Missing values may occur depending on station operation

## Notes

- **93 ecosystem stations** currently have ETC L2 Meteo data, **83** have ETC L2 Fluxnet data (GPP)
- Data is distributed across European countries (FI, SE, DE, FR, IT, etc.)
- Some stations have measurements at multiple soil depths
- Authentication is required only for data download, not for station discovery
- The scripts use the official `icoscp_core` and `icoscp` Python libraries
- Files left over from an older version of these scripts (e.g. `station_metadata.csv`, `stations_soil_moisture.csv`) are no longer produced and can be deleted

## Quick Authentication Test

To verify your authentication is working, run:

**Test with credentials file**:
```bash
python -c "from icoscp.dobj import Dobj; d = Dobj('https://meta.icos-cp.eu/objects/g7pMywPrXoof0vu9rtg-nYAY'); print('Auth OK' if d.colNames else 'No data')"
```

**Test with token** (create a small test script `test_auth.py`):
```python
from icoscp_core.icos import bootstrap
from icoscp import cpauth
from icoscp.dobj import Dobj

token = 'cpauthToken=YOUR_TOKEN_HERE'
meta, data = bootstrap.fromCookieToken(token)
cpauth.init_by(data.auth)

d = Dobj('https://meta.icos-cp.eu/objects/g7pMywPrXoof0vu9rtg-nYAY')
print('Auth OK' if d.colNames else 'No data')
```
Then run: `python test_auth.py`

## Troubleshooting

### "Authentication error" when downloading

**If using a token**:
1. Make sure the token format is correct: `--cpauthtoken cpauthToken=cpauthToken_TOKEN_VALUE`
2. Ensure the `cpauthToken=` prefix is included
3. Check that the token hasn't expired (tokens last ~27 hours)
4. Verify you have accepted the ICOS Data Licence in your profile

**If using credentials file**:
1. Verify the credentials file was created correctly
2. Re-initialize with: `python -c "from icoscp_core.icos import auth; auth.init_config_file()"`

### "No stations found"
Run `metadata.py` first to create the required CSV files.

Run `metadata.py` first to create the station CSVs, then pass the right one via `--input-csv`:
- `stations_sm.csv` - soil moisture only
- `stations_fluxnet.csv` - FluxNet carbon fluxes (GPP, NEE, RECO)
- `stations_flux.csv` - Fluxes product (NEE, CO2, H, H2O, LE)
- `stations_combined.csv` - all queried data types (written when multiple data types are queried)

### "No stations found"

Check the `--datatype` and `--variable-pattern` arguments of `metadata.py` — a too-restrictive variable filter (e.g. `--variable-pattern GPP` while querying `etcL2Meteo`) matches no stations.

### "Found 0 stations with matching variables" when looking for GPP

GPP is **not** part of the `etcL2Fluxes` product (that product contains NEE, CO2, H, H2O, LE, ...). GPP is in the **`etcL2Fluxnet`** product as `GPP_NT_CUT_REF` (and related `GPP_*_REF` columns). Query it with `--datatype etcL2Fluxnet`.

### Specific soil layer or variable not available

Check the corresponding CSV to see which variables each station has (`stations_sm.csv` for SWC levels, `stations_fluxnet.csv` for GPP/NEE/RECO, `stations_flux.csv` for NEE/CO2/H2O/...). Not all stations have all levels or variables. In a combined run, a missing combination simply shows up as empty cells in the output.

## References

- ICOS Carbon Portal: https://www.icos-cp.eu/
- Python Library Documentation: https://icos-carbon-portal.github.io/pylib/
- Authentication Guide: https://icos-carbon-portal.github.io/pylib/icoscp/authentication/
- Data Products: https://www.icos-cp.eu/data-products

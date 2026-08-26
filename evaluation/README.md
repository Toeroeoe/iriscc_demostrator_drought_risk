# ICOS Soil Moisture Data Download Scripts

This directory contains scripts to discover and download ICOS surface soil moisture data from ecosystem (ES) stations with Level 2 data.

## Overview

ICOS (Integrated Carbon Observation System) provides soil moisture measurements (SWC - Soil Water Content) at various depths as part of their ETC L2 Meteo data products. These scripts help you:

1. **Discover** which stations have soil moisture data and their metadata
2. **Download** the actual soil moisture time series data

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
python download_soil_moisture.py --cpauthtoken cpauthToken=[the-actual-token-value]
```

**Important**: Make sure to include the `cpauthToken=` prefix. The token looks like a long encoded string (e.g., `cpauthToken=WzE2OTY2NzQ5OD...]`).

**Note**: Tokens expire after approximately 27 hours.

#### Method 3: API Token in Code
```python
from icoscp_core.icos import bootstrap
cookie_token = 'cpauthToken=YOUR_TOKEN_HERE'
meta, data = bootstrap.fromCookieToken(cookie_token)
```

Full authentication documentation: https://icos-carbon-portal.github.io/pylib/icoscp/authentication/

## Scripts

### 1. evaluation_icos.py - Discover Stations with Soil Moisture Data

This script queries the ICOS Carbon Portal metadata service to find all ecosystem stations that have Level 2 soil moisture data.

**Usage:**
```bash
python evaluation_icos.py
```

**Output:**
- `station_metadata.csv` - Metadata for all stations with soil moisture data
- `stations_soil_moisture.csv` - List of stations with data object URIs for downloading

**What it does:**
- Finds ecosystem (ES) stations with ETC L2 Meteo data
- Identifies which stations have soil moisture (SWC) variables
- Extracts station metadata: name, coordinates, elevation, country
- Lists available SWC levels per station (SWC_1, SWC_2, etc.)

**Sample output (station_metadata.csv):**
```csv
station_uri,station_id,station_name,latitude,longitude,elevation,country_code,ecosystem_type,soil_moisture_variables
http://meta.icos-cp.eu/resources/stations/ES_FI-Lom,FI-Lom,Lompolojankka (FI-Lom),67.99724,24.209179,247.0,FI,Ecosystem (ES),SWC_1
http://meta.icos-cp.eu/resources/stations/ES_FR-Hes,FR-Hes,Hesse (FR-Hes),48.6741,7.06465,310.0,FR,Ecosystem (ES),SWC_1; SWC_2; SWC_3; SWC_4; SWC_5
...
```

### 2. download_soil_moisture.py - Download ICOS Time Series Data

This script downloads time series data (soil moisture, GPP, NEE, etc.) from the stations discovered by `evaluation_icos.py`.

**Usage**:
```bash
# Download only SWC_1 (default):
python download_soil_moisture.py

# Download multiple variables (soil layers and/or fluxes such as GPP):
python download_soil_moisture.py --variables SWC_1,SWC_2,GPP

# Download all soil layers ('SWC' matches SWC_1, SWC_2, ...):
python download_soil_moisture.py --variables SWC

# Resample to daily means:
python download_soil_moisture.py --variables SWC_1 --resample 1D

# Daily mean and standard deviation:
python download_soil_moisture.py --variables SWC_1 --resample 1D --agg mean,std

# With authentication token:
python download_soil_moisture.py --cpauthtoken cpauthToken=YOUR_TOKEN_HERE --variables SWC_1

# Limit the number of data objects processed (useful for testing):
python download_soil_moisture.py --limit 5

# Specify input/output files:
python download_soil_moisture.py --input-csv stations_soil_moisture.csv --output soil_data.csv

# Show help:
python download_soil_moisture.py --help
```

**Options**:
- `--input-csv`: Input CSV file with station information (default: `stations_soil_moisture.csv`)
- `--output`: Output CSV file for time series data (default: `icos_timeseries.csv`)
- `--variables`: Comma-separated variable names to download (default: `SWC_1`). A bare family prefix matches all numbered variants (e.g., `SWC` matches `SWC_1`, `SWC_2`, ...)
- `--resample`: Pandas resample rule applied after downloading (e.g., `1D` for daily). No resampling by default.
- `--agg`: Comma-separated aggregation functions used with `--resample` (default: `mean`)
- `--limit`: Maximum number of data objects to process (default: all)
- `--cpauthtoken`: ICOS Carbon Portal authentication token (use for temporary access without credentials file)

**Output**:
- `icos_timeseries.csv` - Time series data with TIMESTAMP as the index and one column per station-variable time series

**Sample output**:
```
TIMESTAMP,FI-Lom (m3/m3),FR-Hes (m3/m3),...
2020-01-01 00:00:00,0.25,0.30,...
2020-01-01 01:00:00,0.26,0.31,...
```

**Output format**:
- Index: TIMESTAMP (pandas DatetimeIndex, written as the first CSV column)
- Columns: One column per station-variable pair
  - Single variable: `"STATION_ID (unit)"` (e.g., `"FI-Lom (m3/m3)"`)
  - Multiple variables: `"STATION_ID_VARIABLE (unit)"` (e.g., `"FI-Lom_SWC_1 (m3/m3)"`)
  - With `--resample` and multiple `--agg`: `"STATION_ID_VARIABLE_AGG (unit)"` (e.g., `"FI-Lom_SWC_1_MEAN (m3/m3)"`)
- Units: Inferred from ICOS data object metadata
- Missing values: Empty cells where data is not available

## Workflow

1. **Discover stations**:
   ```bash
   python evaluation_icos.py
   ```

2. **Review the output CSV files** to see which stations have soil moisture data and which levels are available.

3. **Authenticate** (if you want to download data):
   ```bash
   python -c "from icoscp_core.icos import auth; auth.init_config_file()"
   ```

4. **Download data**:
   ```bash
   # Download SWC_1 from all stations:
   python download_soil_moisture.py
   
   # Download SWC_1, SWC_2, SWC_3 from all stations:
   python download_soil_moisture.py --variables SWC_1,SWC_2,SWC_3
   
   # Download all soil layers using family prefix:
   python download_soil_moisture.py --variables SWC
   
   # Download multiple variables including GPP:
   python download_soil_moisture.py --variables SWC_1,GPP
   
   # Resample to daily means:
   python download_soil_moisture.py --variables SWC_1 --resample 1D
   
   # Daily mean and standard deviation:
   python download_soil_moisture.py --variables SWC_1 --resample 1D --agg mean,std
   ```

## Data Information

### Soil Moisture Variables (SWC)
- **SWC_1, SWC_2, ...** - Soil Water Content at different depths
- The number of available levels varies by station (typically 1-7 levels)
- Values are typically in m³/m³ (volumetric water content)

### Data Format
- The source data is in ETC L2 Meteo format (Level 2, Quality Controlled)
- Time series data includes timestamps and measurements at regular intervals
- Missing values may occur depending on station operation

## Notes

- **78 ecosystem stations** currently have soil moisture data available
- Data is distributed across European countries (FI, SE, DE, FR, IT, etc.)
- Some stations have measurements at multiple soil depths
**Note**: Authentication is required only for data download, not for station discovery
- The scripts use the official `icoscp_core` and `icoscp` Python libraries

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
1. Make sure the token format is correct: `--cpauthtoken cpauthToken=YOUR_TOKEN_VALUE`
2. Ensure the `cpauthToken=` prefix is included
3. Check that the token hasn't expired (tokens last ~27 hours)
4. Verify you have accepted the ICOS Data Licence in your profile

**If using credentials file**:
1. Verify the credentials file was created correctly
2. Re-initialize with: `python -c "from icoscp_core.icos import auth; auth.init_config_file()"`

### "No stations found"
Run `evaluation_icos.py` first to create the required CSV files.

### Specific soil layer not available
Check `stations_soil_moisture.csv` to see which SWC levels each station has. Not all stations have all levels.

## References

- ICOS Carbon Portal: https://www.icos-cp.eu/
- Python Library Documentation: https://icos-carbon-portal.github.io/pylib/
- Authentication Guide: https://icos-carbon-portal.github.io/pylib/icoscp/authentication/
- Data Products: https://www.icos-cp.eu/data-products

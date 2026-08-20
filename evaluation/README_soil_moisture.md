# ICOS Soil Moisture Data Download Scripts

This directory contains scripts to discover and download ICOS surface soil moisture data from ecosystem (ES) stations with Level 2 data.

## Overview

ICOS (Integrated Carbon Observation System) provides soil moisture measurements (SWC - Soil Water Content) at various depths as part of their ETC L2 Meteo data products. These scripts help you:

1. **Discover** which stations have soil moisture data and their metadata
2. **Download** the actual soil moisture time series data

## Prerequisites

### 1. Virtual Environment

A virtual environment has been created at `./evaluation/.venv` with the required packages:
- `icoscp_core` - for metadata access
- `icoscp` - for data download

Activate it with:
```bash
source .venv/bin/activate
```

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

### 2. download_soil_moisture.py - Download Soil Moisture Time Series

This script downloads actual soil moisture time series data from the stations discovered by `evaluation_icos.py`.

**Usage**:
```bash
# Download only the first soil layer (default):
python download_soil_moisture.py

# Download only the first soil layer with a token:
python download_soil_moisture.py --cpauthtoken cpauthToken=YOUR_TOKEN_HERE

# Download multiple soil layers:
python download_soil_moisture.py --levels 1,2,3

# Download multiple soil layers with a token:
python download_soil_moisture.py --cpauthtoken cpauthToken=YOUR_TOKEN_HERE --levels 1,2,3

# Limit the number of data objects processed (useful for testing):
python download_soil_moisture.py --limit 5

# Specify input/output files:
python download_soil_moisture.py --input-csv stations_soil_moisture.csv --output soil_data.csv

# Show help:
python download_soil_moisture.py --help
```

**Options:**
- `--input-csv`: Input CSV file with station information (default: `stations_soil_moisture.csv`)
- `--output`: Output CSV file for time series data (default: `soil_moisture_timeseries.csv`)
- `--levels`: Comma-separated list of soil moisture levels to download (default: `1`)
- `--limit`: Maximum number of data objects to process (default: all)
- `--cpauthtoken`: ICOS Carbon Portal authentication token (use for temporary access without credentials file)

**Output:**
- `soil_moisture_timeseries.csv` - Time series data with TIMESTAMP as index and each station as a column

**Sample output (soil_moisture_timeseries.csv):**
```
TIMESTAMP,FI-Lom (m³/m³),FR-Hes (m³/m³),DE-Tha (m³/m³),...
2020-01-01 00:00:00,0.25,0.30,0.28,...
2020-01-01 01:00:00,0.26,0.31,0.29,...
2020-01-01 02:00:00,0.27,0.32,0.30,...
```

**Output format:**
- Index: TIMESTAMP (datetime)
- Columns: Each station ID with units (e.g., `FI-Lom (m³/m³)`)
- Values: Soil water content in m³/m³ (volumetric water content)
- Missing values: Empty cells where data is not available

## Workflow

1. **Discover stations:**
   ```bash
   python evaluation_icos.py
   ```

2. **Review the output CSV files** to see which stations have soil moisture data and which levels are available.

3. **Authenticate** (if you want to download data):
   ```bash
   python -c "from icoscp_core.icos import auth; auth.init_config_file()"
   ```

4. **Download data:**
   ```bash
   # Download SWC_1 from all stations:
   python download_soil_moisture.py
   
   # Download SWC_1, SWC_2, SWC_3 from all stations:
   python download_soil_moisture.py --levels 1,2,3
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

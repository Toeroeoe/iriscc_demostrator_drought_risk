
import glob
from pathlib import Path
import pandas as pd
import netCDF4 as nc
import re
import numpy as np

app_dir = Path(__file__).parent
data_dir = Path(__file__).parent.parent.parent / "data"
images = Path(__file__).parent.parent.parent / "images"

df = pd.read_csv(data_dir / "penguins.csv")

# Load decadal data files
decadal_means_clm5_files = sorted(glob.glob(str(data_dir / "decadal_SMI/CLM5/decadal_stats_*timmean.nc_classic.nc")))
decadal_means_mhm_files = sorted(glob.glob(str(data_dir / "decadal_SMI/mHM/decadal_stats_*timmean.nc.nc_classic.nc")))

if len(decadal_means_clm5_files) == 0 or len(decadal_means_mhm_files) == 0:
    raise FileNotFoundError("No decadal means files found in the data directory.")
elif len(decadal_means_clm5_files) != len(decadal_means_mhm_files):
    raise ValueError("The number of CLM5 and mHM decadal means files do not match.")

# Extract decade years from filenames
decade_years = []
for file in decadal_means_clm5_files:
    match = re.search(r'(\d{4})_(\d{4})', file)
    if match:
        decade_years.append(int(match.group(1)))

# Load complete datasets with MFDataset
clm5_ds = nc.MFDataset(decadal_means_clm5_files)
mhm_ds = nc.MFDataset(decadal_means_mhm_files)

# Load full arrays (time, lat, lon)
CLM5_smi_full = clm5_ds.variables["SMI"][:]
mHM_smi_full = mhm_ds.variables["SMI"][:]

# Extract coordinates (try different variable names)
if 'lon' in clm5_ds.variables:
    lon = clm5_ds.variables['lon'][:]
    lat = clm5_ds.variables['lat'][:]
elif 'rlon' in clm5_ds.variables:
    lon = clm5_ds.variables['rlon'][:]
    lat = clm5_ds.variables['rlat'][:]
else:
    coord_vars = list(clm5_ds.variables.keys())
    raise ValueError(f"Could not find lat/lon or rlon/rlat in dataset. Available: {coord_vars}")

# Create mapping from decade year to array index
decade_to_index = {year: idx for idx, year in enumerate(decade_years)}


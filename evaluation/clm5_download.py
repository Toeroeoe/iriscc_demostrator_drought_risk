#!/usr/bin/env python3
"""
Extract CLM5 (CESM) model time series for the stations listed in a CSV file.

This is the model-side counterpart of download.py (the ICOS observation
downloader): for every station it finds the closest CLM5 grid cell and
extracts the requested daily variables:

  SM  -> H2OSOI (volumetric soil water, soil layer `soil_layer_i` from the yaml)
  GPP -> GPP    (gross primary production)

IMPORTANT: the lat/lon coordinates stored inside the CLM5 history files are
wrong. Grid-cell coordinates are taken exclusively from the land-domain file
(`grid` section of the yaml). The domain grid is curvilinear, so `yc`/`xc`
are 2D arrays and the nearest cell is found by searching the whole grid.

Output format mirrors download.py exactly: TIMESTAMP as the first column and
one "STATION_ID_VARIABLE (unit)" column per station-variable pair (plus _AGG
suffixes when several --agg functions are used with --resample).

Defaults are fitted to the ICOS downloader:
  - --agg mean, no resampling (the model data are already daily)
  - unit conversion: GPP gC/m^2/s -> gC/m2/d (same as download.py) and
    SM mm3/mm3 -> % (the ICOS SWC columns are reported in %)

The run is described by a small YAML file (default: clm5_files.yaml) holding
the model output path/glob, the variable mapping, the soil layer index and
the grid domain file.

Usage:
    # Default: SM (top soil layer) and GPP for all stations, daily output:
    python clm5_download.py

    # Resample to monthly means:
    python clm5_download.py --resample 1MS --agg mean

    # Monthly mean and standard deviation:
    python clm5_download.py --resample 1MS --agg mean,std

    # Keep the CLM5 source units (GPP in gC/m^2/s, SM in mm3/mm3):
    python clm5_download.py --no-unit-conversion

    # Target unit overrides:
    python clm5_download.py --unit SM:m3/m3 --unit GPP:gC/m2/s

    # Only GPP:
    python clm5_download.py --variables GPP

    # Limit the number of model files (years) processed:
    python clm5_download.py --limit 2

    # Specify input/output files:
    python clm5_download.py --input-csv stations_combined.csv \
        --output clm5_timeseries.csv
"""

import os
import csv
import glob
import math
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import netCDF4
import yaml

from units import apply_unit_conversions

# Target units applied by default, keyed by variable label. Chosen to match
# the units of the ICOS observation output (gpp_sm_timeseries.csv), so the
# model and observation columns are directly comparable: GPP in gC/m2/d
# (same default as download.py) and SM in % (ICOS SWC is reported in %).
CLM5_DEFAULT_TARGET_UNITS = {
    'SM': '%',
    'GPP': 'gC/m2/d',
}


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Extract CLM5 model time series at the grid cell closest '
                    'to each station'
    )
    parser.add_argument(
        '--config',
        default='clm5_files.yaml',
        help='YAML file with CLM5 output and grid information '
             '(default: clm5_files.yaml)'
    )
    parser.add_argument(
        '--input-csv',
        default='stations_combined.csv',
        help='Input CSV file with station information: station_id, latitude, '
             'longitude (default: stations_combined.csv, as written by '
             'metadata.py)'
    )
    parser.add_argument(
        '--output',
        default='clm5_timeseries.csv',
        help='Output CSV file for time series data (default: clm5_timeseries.csv)'
    )
    parser.add_argument(
        '--cell-report',
        default='clm5_cells.csv',
        help='Sidecar CSV describing the grid cell matched to each station '
             '(default: clm5_cells.csv; empty string disables it)'
    )
    parser.add_argument(
        '--variables',
        default='SM,GPP',
        help="Comma-separated variables to extract (default: SM,GPP). "
             "Names are the keys of the 'variables' mapping in the yaml "
             "(SM, GPP); the raw NetCDF names (H2OSOI, GPP) are accepted too."
    )
    parser.add_argument(
        '--resample',
        default=None,
        help="Pandas resample rule applied after extraction "
             "(e.g. '1MS' for monthly). No resampling by default; the CLM5 "
             "data are already daily."
    )
    parser.add_argument(
        '--agg',
        default='mean',
        help="Comma-separated aggregation functions used with --resample (default: mean)"
    )
    parser.add_argument(
        '--unit',
        action='append',
        default=None,
        metavar='VAR:UNIT',
        help="Target unit for a variable, e.g. --unit SM:m3/m3. Repeatable. "
             "By default GPP is converted to gC/m2/d and SM to % (to match "
             "the ICOS observation output)."
    )
    parser.add_argument(
        '--no-unit-conversion',
        action='store_true',
        help='Disable automatic unit conversion (keep the units as stored '
             'in the CLM5 files, e.g. GPP in gC/m^2/s and SM in mm3/mm3).'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Maximum number of model files (years) to process (default: all)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=4,
        help='Number of files to read in parallel (default: 4; 1 for serial)'
    )
    return parser.parse_args()


def parse_unit_overrides(pairs):
    """
    Parse repeated 'VAR:UNIT' values from --unit into a dict.

    Mirrors parse_unit_overrides() in download.py.

    Args:
        pairs: List of 'VAR:UNIT' strings (or None)

    Returns:
        Dict mapping variable name -> target unit

    Raises:
        ValueError: if a value is malformed
    """
    overrides = {}
    for pair in pairs or []:
        var, sep, unit = pair.partition(':')
        var, unit = var.strip(), unit.strip()
        if not sep or not var or not unit:
            raise ValueError(
                f"Invalid --unit value {pair!r}. Expected VAR:UNIT, "
                f"e.g. SM:m3/m3"
            )
        overrides[var] = unit
    return overrides


def read_stations_from_csv(csv_path):
    """
    Read station information from the CSV file.

    Mirrors read_stations_from_csv() in download.py.

    Returns:
        List of dicts with station information
    """
    stations = []
    with open(csv_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stations.append(row)
    print(f"Read {len(stations)} stations from {csv_path}")
    return stations


def load_config(config_path):
    """
    Load the YAML configuration.

    Args:
        config_path: Path to the yaml file (clm5_files.yaml)

    Returns:
        Tuple (clm5_cfg, grid_cfg)

    Raises:
        ValueError: if required sections/keys are missing
    """
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)

    try:
        clm5_cfg = data['clm5']
        grid_cfg = data['grid']
    except (TypeError, KeyError) as e:
        raise ValueError(
            f"Config {config_path} must contain 'clm5' and 'grid' sections "
            f"(missing: {e})"
        ) from e

    for key in ('path', 'files', 'variables'):
        if key not in clm5_cfg:
            raise ValueError(f"clm5 section missing key: {key!r}")
    grid_file = os.path.join(grid_cfg['path'], grid_cfg['file'])
    if not os.path.exists(grid_file):
        raise ValueError(f"Grid domain file not found: {grid_file}")
    for key in ('lat', 'lon'):
        if key not in grid_cfg['variables']:
            raise ValueError(f"grid section missing variables key: {key!r}")
    return clm5_cfg, grid_cfg


def list_clm5_files(clm5_cfg):
    """
    Resolve the model file glob to a chronologically sorted file list.

    Args:
        clm5_cfg: 'clm5' section of the yaml

    Returns:
        Sorted list of file paths (filenames carry the year, so sorted
        order is chronological)

    Raises:
        ValueError: if the glob matches no files
    """
    pattern = os.path.join(clm5_cfg['path'], clm5_cfg['files'])
    files = sorted(glob.glob(pattern))
    if not files:
        raise ValueError(f"No model files match {pattern}")
    return files


def resolve_variables(requested, cfg_vars):
    """
    Resolve requested variable names to (label, netcdf_name) pairs.

    Both the yaml keys (SM, GPP) and the raw NetCDF names (H2OSOI, GPP) are
    accepted, case-insensitively. Duplicates are dropped.

    Args:
        requested: List of requested variable names
        cfg_vars: 'clm5.variables' mapping, e.g. {'SM': 'H2OSOI', 'GPP': 'GPP'}

    Returns:
        List of (label, netcdf_name) tuples in request order

    Raises:
        ValueError: if a requested name is unknown
    """
    known = {}
    for label, nc_name in cfg_vars.items():
        known[label.upper()] = (label, nc_name)
        known.setdefault(nc_name.upper(), (label, nc_name))

    resolved = []
    for spec in requested:
        key = spec.strip().upper()
        if key not in known:
            raise ValueError(
                f"Unknown variable {spec!r}. Known variables: "
                f"{sorted(cfg_vars)} (raw names: {sorted(set(cfg_vars.values()))})"
            )
        pair = known[key]
        if pair not in resolved:
            resolved.append(pair)
    return resolved


def load_grid(grid_cfg):
    """
    Load the grid-cell coordinates from the land-domain file.

    NOTE: the CLM5 history files also carry lat/lon variables, but their
    values are wrong and are never used. Only the domain file defines the
    grid-cell coordinates. The grid is curvilinear: `yc`/`xc` are 2D arrays.

    Args:
        grid_cfg: 'grid' section of the yaml

    Returns:
        Tuple (grid_lat, grid_lon, land_mask) where grid_lat/grid_lon are
        2D float arrays (row, col) and land_mask is a 2D array with non-zero
        values for land cells (None if the file has no 'mask' variable)
    """
    grid_file = os.path.join(grid_cfg['path'], grid_cfg['file'])
    print(f"Loading grid from {grid_file}")
    with netCDF4.Dataset(grid_file) as ds:
        lat_name = grid_cfg['variables']['lat']
        lon_name = grid_cfg['variables']['lon']
        grid_lat = np.asarray(ds[lat_name][:], dtype=np.float64)
        grid_lon = np.asarray(ds[lon_name][:], dtype=np.float64)
        land_mask = None
        if 'mask' in ds.variables:
            land_mask = np.asarray(ds['mask'][:])
    print(f"Grid: {grid_lat.shape[0]} x {grid_lat.shape[1]} cells, "
          f"lat {grid_lat.min():.3f}..{grid_lat.max():.3f}, "
          f"lon {grid_lon.min():.3f}..{grid_lon.max():.3f}")
    if land_mask is not None:
        print(f"Land cells: {int((land_mask > 0).sum())} of {land_mask.size}")
    return grid_lat, grid_lon, land_mask


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two (lat, lon) points."""
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2.0) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2)
    return 2.0 * radius * math.asin(math.sqrt(a))


def find_nearest_cell(lat, lon, grid_lat, grid_lon, land_mask=None):
    """
    Find the closest grid cell to a (lat, lon) point on the curvilinear grid.

    Distance is the planar (lat, lon) difference with the longitude term
    weighted by cos(station latitude); this is accurate to well below one
    grid cell (cells are ~2 km). If land_mask is given, only land cells are
    considered (so a coastal station falls back to the nearest land cell).

    Args:
        lat, lon: Station coordinates (degrees)
        grid_lat, grid_lon: 2D arrays of cell coordinates
        land_mask: 2D array with non-zero values for land cells (or None)

    Returns:
        Dict with row, col, cell_lat, cell_lon, distance_km -- or None if
        the grid contains no land cell at all
    """
    lat = float(lat)
    lon = ((float(lon) + 180.0) % 360.0) - 180.0
    weight = math.cos(math.radians(lat))
    dlat = grid_lat - lat
    dlon = (grid_lon - lon) * weight
    d2 = dlat * dlat + dlon * dlon
    if land_mask is not None:
        d2 = np.where(land_mask > 0, d2, np.inf)
    if not np.isfinite(d2.min()):
        return None
    flat = int(np.argmin(d2))
    row, col = np.unravel_index(flat, grid_lat.shape)
    cell_lat = float(grid_lat[row, col])
    cell_lon = float(grid_lon[row, col])
    return {
        'row': int(row),
        'col': int(col),
        'cell_lat': cell_lat,
        'cell_lon': cell_lon,
        'distance_km': haversine_km(lat, lon, cell_lat, cell_lon),
    }


def match_station_cells(stations, grid_lat, grid_lon, land_mask=None):
    """
    Match every station to its closest grid cell.

    Args:
        stations: List of station dicts (need station_id, latitude, longitude)
        grid_lat, grid_lon: 2D arrays of cell coordinates
        land_mask: 2D land mask (or None)

    Returns:
        Tuple (cells, match_info):
        - cells: dict station_id -> (row, col)
        - match_info: list of dicts, one per matched station, with the
          station coordinates and the cell coordinates/distance
    """
    cells = {}
    match_info = []
    for station in stations:
        sid = station['station_id']
        try:
            lat = float(station['latitude'])
            lon = float(station['longitude'])
        except (KeyError, TypeError, ValueError):
            print(f"  ! Station {sid}: missing/invalid coordinates, skipping")
            continue
        match = find_nearest_cell(lat, lon, grid_lat, grid_lon, land_mask)
        if match is None:
            print(f"  ! Station {sid}: no land grid cell found, skipping")
            continue
        cells[sid] = (match['row'], match['col'])
        match_info.append({
            'station_id': sid,
            'station_name': station.get('station_name', ''),
            'latitude': lat,
            'longitude': lon,
            'cell_row': match['row'],
            'cell_col': match['col'],
            'cell_latitude': match['cell_lat'],
            'cell_longitude': match['cell_lon'],
            'distance_km': match['distance_km'],
        })
        print(f"  {sid} ({lat:.5f}, {lon:.5f}) -> cell "
              f"({match['row']}, {match['col']}) at "
              f"({match['cell_lat']:.4f}, {match['cell_lon']:.4f}), "
              f"{match['distance_km']:.2f} km")
    return cells, match_info


def write_cell_report(match_info, output_path):
    """Write the station -> grid cell mapping to a CSV sidecar."""
    fieldnames = ['station_id', 'station_name', 'latitude', 'longitude',
                  'cell_row', 'cell_col', 'cell_latitude', 'cell_longitude',
                  'distance_km']
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in match_info:
            writer.writerow({k: row[k] for k in fieldnames})
    print(f"Wrote cell mapping for {len(match_info)} stations to {output_path}")


def decode_time(time_values, time_var):
    """
    Decode a NetCDF time variable to a pandas DatetimeIndex.

    Each file must be decoded with its own `units`/`calendar` attributes:
    the run contains restart epochs where the raw time values reset to 0.0,
    so raw values must never be concatenated across files.

    Args:
        time_values: Raw time values (array)
        time_var: netCDF4 Variable with `units` and `calendar` attributes

    Returns:
        pandas DatetimeIndex
    """
    decoded = netCDF4.num2date(time_values, time_var.units,
                               calendar=time_var.calendar)
    ts = []
    for d in decoded:
        try:
            ts.append(datetime(d.year, d.month, d.day,
                               d.hour, d.minute, d.second))
        except ValueError:
            # The date does not exist in the proleptic Gregorian calendar
            # (e.g. Feb 29 of a 366-day/360-day CF calendar). Snap it to the
            # next day so the time axis stays usable. (The current run uses
            # the 'noleap' calendar, whose dates are all valid Gregorian
            # dates, so this branch is not taken for it.)
            d = d + timedelta(days=1)
            ts.append(datetime(d.year, d.month, d.day,
                               d.hour, d.minute, d.second))
    return pd.DatetimeIndex(ts)


def _apply_fill_value(arr, var):
    """Replace the variable's fill/missing value with NaN, in place."""
    for attr in ('_FillValue', 'missing_value'):
        try:
            fill = var.getncattr(attr)
        except Exception:
            fill = None
        if fill is None:
            continue
        arr[arr == fill] = np.nan
        return arr
    return arr


def process_clm5_file(path, cells, specs, soil_layer):
    """
    Read one annual CLM5 file and extract the requested variables at the
    matched grid cells.

    Each requested variable is read as one bulk time slab (a full year:
    (time, lat, lon)); per-point strided reads on these files are far too
    slow (see benchmarks). Station columns are then cut out with numpy
    fancy indexing.

    Args:
        path: NetCDF file path
        cells: dict station_id -> (row, col)
        specs: list of (label, netcdf_name) pairs
        soil_layer: Soil layer index for 4D variables (yaml soil_layer_i)

    Returns:
        Tuple (time_index, units, per_label) with a DatetimeIndex, a dict
        label -> source unit, and a dict label -> dict station_id -> values
        (np.ndarray, one value per time step)
    """
    station_ids = list(cells)
    rows = np.array([cells[s][0] for s in station_ids], dtype=int)
    cols = np.array([cells[s][1] for s in station_ids], dtype=int)

    with netCDF4.Dataset(path) as ds:
        time_index = decode_time(ds['time'][:], ds['time'])
        units = {}
        per_label = {}
        for label, nc_name in specs:
            var = ds[nc_name]
            try:
                units[label] = str(var.getncattr('units'))
            except Exception:
                units[label] = ''

            if var.ndim == 4:
                # (time, levsoi, lat, lon)
                if not 0 <= soil_layer < var.shape[1]:
                    raise ValueError(
                        f"soil_layer_i={soil_layer} out of range for "
                        f"{nc_name} ({var.shape[1]} soil layers) in {path}"
                    )
                arr = np.asarray(var[:, soil_layer, :, :], dtype=np.float32)
            elif var.ndim == 3:
                # (time, lat, lon)
                arr = np.asarray(var[:], dtype=np.float32)
            else:
                raise ValueError(
                    f"Unexpected dimensions {var.dimensions} for {nc_name} "
                    f"in {path}"
                )

            if rows.size and (rows.max() >= arr.shape[1]
                              or cols.max() >= arr.shape[2]):
                raise ValueError(
                    f"Grid cell index out of range for {nc_name} in {path}: "
                    f"max row {int(rows.max())} / col {int(cols.max())} vs "
                    f"spatial shape {arr.shape[1:]} (model file and domain "
                    f"grid are inconsistent)"
                )

            _apply_fill_value(arr, var)
            stack = arr[:, rows, cols]  # (time, nstations)
            per_label[label] = {
                sid: np.asarray(stack[:, k], dtype=np.float32)
                for k, sid in enumerate(station_ids)
            }
            del arr, stack
    return time_index, units, per_label


def extract_all_files(files, cells, specs, soil_layer, workers=1):
    """
    Process all model files, optionally in parallel.

    Args:
        files: List of NetCDF file paths
        cells: dict station_id -> (row, col)
        specs: list of (label, netcdf_name) pairs
        soil_layer: Soil layer index for 4D variables
        workers: Number of parallel file readers (1 = serial)

    Returns:
        List of (time_index, units, per_label) tuples (one per successful
        file, in completion order)
    """
    results = []
    if workers <= 1:
        for i, path in enumerate(files):
            print(f"[{i+1}/{len(files)}] {os.path.basename(path)}")
            try:
                results.append(process_clm5_file(path, cells, specs, soil_layer))
            except Exception as e:
                print(f"  ! Error processing {os.path.basename(path)}: {e}")
        return results

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_clm5_file, path, cells, specs, soil_layer): path
            for path in files
        }
        for i, future in enumerate(as_completed(futures)):
            path = futures[future]
            print(f"[{i+1}/{len(files)}] {os.path.basename(path)}")
            try:
                results.append(future.result())
            except Exception as e:
                print(f"  ! Error processing {os.path.basename(path)}: {e}")
    return results


def assemble_timeseries(file_results):
    """
    Combine the per-file results into one station/variable DataFrame.

    Mirrors the assembly in download.py: one series per (station, variable)
    pair, overlapping timestamps deduplicated (keep first).

    Args:
        file_results: List of (time_index, units, per_label) tuples

    Returns:
        Tuple (df, variable_units) with a DataFrame (TIMESTAMP DatetimeIndex,
        MultiIndex columns (station_id, variable)) and a dict variable ->
        source unit
    """
    variable_units = {}
    station_data = {}
    for time_index, units, per_label in file_results:
        for label, source_unit in units.items():
            if source_unit:
                variable_units.setdefault(label, source_unit)
        for label, sid_map in per_label.items():
            for sid, values in sid_map.items():
                key = (sid, label)
                series = pd.Series(values, index=time_index, name=label)
                if key not in station_data:
                    station_data[key] = series
                else:
                    station_data[key] = pd.concat(
                        [station_data[key], series]
                    ).loc[lambda x: ~x.index.duplicated(keep='first')]

    if not station_data:
        return pd.DataFrame(), variable_units

    df = pd.DataFrame(station_data)
    df.index.name = 'TIMESTAMP'
    return df.sort_index().sort_index(axis=1), variable_units


def resample_timeseries(df, rule, aggs):
    """
    Resample a time series DataFrame to the given rule.

    Mirrors resample_timeseries() in download.py: a single aggregation
    keeps the column structure; several aggregations add the aggregation
    function name as the outermost column level.

    Args:
        df: DataFrame with TIMESTAMP as Datetime index
        rule: Pandas resample rule (e.g. '1MS')
        aggs: List of aggregation function names

    Returns:
        Resampled DataFrame

    Raises:
        ValueError: if the rule or an aggregation function is invalid
    """
    if df.empty:
        return df
    try:
        if len(aggs) == 1:
            return df.resample(rule).agg(aggs[0])
        return df.resample(rule).agg(list(aggs))
    except (ValueError, TypeError, AttributeError) as e:
        raise ValueError(
            f"Resampling failed (rule={rule!r}, aggs={aggs!r}): {e}"
        ) from e


def build_output_columns(df, variable_units):
    """
    Build flat, human-readable column names for the output DataFrame.

    Mirrors build_output_columns() in download.py.

    Args:
        df: DataFrame with MultiIndex columns as produced by
            assemble_timeseries / resample_timeseries
        variable_units: Dict mapping variable name to unit (where known)

    Returns:
        List of column name strings
    """
    names = []
    multi_agg = df.columns.nlevels == 3
    # Column layout is (station, variable) or (station, variable, agg)
    # Always include variable name for clarity
    for col in df.columns:
        if multi_agg:
            # pandas appends the aggregation function as the last level
            station, var, agg = col
        else:
            station, var = col
            agg = None
        parts = [str(station)]
        parts.append(str(var))
        if multi_agg:
            parts.append(str(agg).upper())
        name = '_'.join(parts)
        unit = variable_units.get(var)
        if unit:
            name = f"{name} ({unit})"
        names.append(name)
    return names


def write_timeseries_csv(df, output_path, variable_units=None):
    """
    Write time series data to CSV with TIMESTAMP as index and one column
    per station-variable time series. Units (where known) are part of the
    column headers.

    Mirrors write_timeseries_csv() in download.py.

    Args:
        df: DataFrame with time series data (index should be TIMESTAMP)
        output_path: Path to output CSV file
        variable_units: Optional dict mapping variable name to unit
    """
    if variable_units is None:
        variable_units = {}

    if df is None or len(df) == 0:
        print("\nNo data to write. Exiting.")
        return

    out = df.copy()
    out.columns = pd.Index(build_output_columns(out, variable_units))
    out.index.name = 'TIMESTAMP'

    print(f"\nWriting {len(out)} records to {output_path}")
    print(f"Format: TIMESTAMP as index, {len(out.columns)} columns")
    out.to_csv(output_path)
    print(f"Successfully wrote {len(out)} records to {output_path}")

    # Print summary of data
    print("\nData summary:")
    print(f"  - Columns: {len(out.columns)}")
    if isinstance(out.index, pd.DatetimeIndex):
        print(f"  - Date range: {out.index.min()} to {out.index.max()}")
    print(f"  - Total observations: {out.size}")

    print("\nColumns:")
    for col in out.columns[:10]:
        print(f"  - {col}")
    if len(out.columns) > 10:
        print(f"  ... and {len(out.columns) - 10} more")


def main():
    """Main function."""
    args = parse_args()

    print("=" * 70)
    print("CLM5 Model Time Series Extractor")
    print("=" * 70)
    print(f"Started at: {datetime.now().isoformat()}")
    print()

    requested = [v.strip() for v in args.variables.split(',') if v.strip()]
    aggs = [a.strip() for a in args.agg.split(',') if a.strip()]
    if not requested:
        print("Error: --variables must not be empty.")
        return

    # Load configuration and model files
    try:
        clm5_cfg, grid_cfg = load_config(args.config)
    except (OSError, ValueError) as e:
        print(f"Error: {e}")
        return
    try:
        specs = resolve_variables(requested, clm5_cfg['variables'])
    except ValueError as e:
        print(f"Error: {e}")
        return
    soil_layer = int(clm5_cfg.get('soil_layer_i', 0))
    files = list_clm5_files(clm5_cfg)
    if args.limit:
        files = files[:args.limit]

    print(f"Config: {args.config}")
    print(f"Requested variables: {[label for label, _ in specs]} "
          f"-> {[nc for _, nc in specs]} (soil layer index: {soil_layer})")
    print(f"Model files: {len(files)} ({os.path.basename(files[0])} .. "
          f"{os.path.basename(files[-1])})")
    if args.resample:
        print(f"Resampling: rule={args.resample}, agg={aggs}")
    print()

    # Read stations
    if not os.path.exists(args.input_csv):
        print(f"Error: Input file not found: {args.input_csv}")
        print("Please run metadata.py first to create the station CSV files.")
        return
    print(f"Reading stations from: {args.input_csv}")
    stations = read_stations_from_csv(args.input_csv)
    if not stations:
        print("No stations found in input file. Exiting.")
        return
    print()

    # Match stations to grid cells (grid from the domain file only!)
    print("Matching stations to closest CLM5 grid cells...")
    grid_lat, grid_lon, land_mask = load_grid(grid_cfg)
    cells, match_info = match_station_cells(stations, grid_lat, grid_lon, land_mask)
    del grid_lat, grid_lon  # free the ~40 MB of 2D arrays
    if not cells:
        print("\nNo station could be matched to a grid cell. Exiting.")
        return
    if args.cell_report:
        write_cell_report(match_info, args.cell_report)
    print()

    # Extract the time series (bulk read per file, optionally in parallel)
    print(f"Extracting data from {len(files)} files "
          f"({args.workers} parallel worker(s))...")
    file_results = extract_all_files(
        files, cells, specs, soil_layer, workers=args.workers
    )
    if not file_results:
        print("\nNo data extracted. Exiting.")
        return

    all_data, variable_units = assemble_timeseries(file_results)
    if all_data.empty:
        print("\nNo data to write. Exiting.")
        return

    # Convert units before resampling (the conversion factor is constant,
    # so it commutes with resampling) -- same order as in download.py
    if not args.no_unit_conversion:
        try:
            overrides = parse_unit_overrides(args.unit)
        except ValueError as e:
            print(f"Error: {e}")
            return
        print("\nConverting units (defaults: GPP -> gC/m2/d, SM -> %)...")
        merged = {**CLM5_DEFAULT_TARGET_UNITS, **overrides}
        all_data, variable_units = apply_unit_conversions(
            all_data, variable_units, merged
        )

    # Optional resampling
    if not all_data.empty and args.resample:
        print(f"\nResampling to '{args.resample}' with agg={aggs}...")
        all_data = resample_timeseries(all_data, args.resample, aggs)

    # Write results to CSV
    write_timeseries_csv(all_data, args.output, variable_units)

    # Summary
    print("\n" + "=" * 70)
    print("Extraction Summary:")
    print(f"  - Stations in input: {len(stations)}")
    print(f"  - Stations matched to a grid cell: {len(cells)}")
    print(f"  - Requested variables: {[label for label, _ in specs]}")
    print(f"  - Model files processed: {len(file_results)}/{len(files)}")
    print(f"  - Resampling: {args.resample or 'none'}")
    print(f"  - Unit conversion: {'off' if args.no_unit_conversion else 'on'}")
    print(f"  - Output rows: {len(all_data) if all_data is not None else 0}")
    print(f"  - Output columns: {all_data.shape[1] if all_data is not None else 0}")
    print(f"  - Output file: {args.output}")
    print("=" * 70)
    print(f"Completed at: {datetime.now().isoformat()}")


if __name__ == '__main__':
    main()

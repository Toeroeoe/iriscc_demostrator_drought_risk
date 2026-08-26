#!/usr/bin/env python3
"""
Download ICOS station time series data (soil moisture, GPP, NEE, ...) for the
stations listed in a CSV file.

This script:
1. Reads station data from a CSV file (default: stations_soil_moisture.csv,
   created by evaluation_icos.py)
2. Downloads the requested variables for every data object of each station
3. Combines all data into a single CSV with one column per
   station-variable time series

Output Format:
- TIMESTAMP as the index (pandas DatetimeIndex, written as first CSV column)
- One column per station-variable pair:
    - "STATION_ID (unit)"            when a single variable is downloaded
    - "STATION_ID_VARIABLE (unit)"   when multiple variables are downloaded
    - plus "_AGG" suffixes (e.g. _MEAN, _STD) when several --agg functions
      are used together with --resample
- Units are inferred from the ICOS data object metadata

Note: Authentication with ICOS Carbon Portal is required to download data.
See: https://icos-carbon-portal.github.io/pylib/icoscp/authentication/

Usage:
    # Download only the first soil layer (default):
    python download_soil_moisture.py

    # Download multiple variables (soil layers and/or fluxes such as GPP):
    python download_soil_moisture.py --variables SWC_1,SWC_2,GPP

    # Download all soil layers of every station ('SWC' matches SWC_1, SWC_2, ...):
    python download_soil_moisture.py --variables SWC

    # Resample to daily means:
    python download_soil_moisture.py --variables SWC_1 --resample 1D

    # Daily mean and standard deviation:
    python download_soil_moisture.py --variables SWC_1 --resample 1D --agg mean,std

    # Limit the number of data objects processed:
    python download_soil_moisture.py --limit 5

    # Specify input/output files:
    python download_soil_moisture.py --input-csv stations_soil_moisture.csv --output soil_data.csv
"""

import os
import re
import csv
import argparse
from datetime import datetime

import pandas as pd
from icoscp.dobj import Dobj

# Matches column labels that carry their unit in square brackets,
# e.g. 'SWC_1 [m3/m3]'.
UNIT_LABEL_RE = re.compile(r'^(?P<name>.+?)\s*\[(?P<unit>[^\]]+)\]$')


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Download ICOS station time series data'
    )
    parser.add_argument(
        '--input-csv',
        default='stations_soil_moisture.csv',
        help='Input CSV file with station information (default: stations_soil_moisture.csv)'
    )
    parser.add_argument(
        '--output',
        default='icos_timeseries.csv',
        help='Output CSV file for time series data (default: icos_timeseries.csv)'
    )
    parser.add_argument(
        '--variables',
        default='SWC_1',
        help="Comma-separated variable names to download (default: SWC_1). "
             "A bare family prefix matches all numbered variants, "
             "e.g. 'SWC' matches SWC_1, SWC_2, ..."
    )
    parser.add_argument(
        '--resample',
        default=None,
        help="Pandas resample rule applied after downloading "
             "(e.g. '1D' for daily). No resampling by default."
    )
    parser.add_argument(
        '--agg',
        default='mean',
        help="Comma-separated aggregation functions used with --resample (default: mean)"
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Maximum number of data objects to process (default: all)'
    )
    parser.add_argument(
        '--cpauthtoken',
        type=str,
        default=None,
        help='ICOS Carbon Portal authentication token (cpauthtoken). If provided, '
             'this will be used for authentication instead of credentials file.'
    )
    return parser.parse_args()


def read_stations_from_csv(csv_path):
    """
    Read station information from the CSV file.

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


def match_variables(requested, labels):
    """
    Match requested variable names (or family prefixes) against the column
    labels available in a data object.

    'SWC_1' matches exactly 'SWC_1' (but not 'SWC_10'); a bare prefix like
    'SWC' matches 'SWC_1', 'SWC_2', ... Labels that embed their unit in
    square brackets (e.g. 'SWC_1 [m3/m3]') are matched by their bare name.

    Args:
        requested: List of requested variable names/prefixes
        labels: List of available column labels (e.g. dobj.colNames)

    Returns:
        List of matched labels in the order they appear in `labels`
    """
    matched = []
    for label in labels:
        m = UNIT_LABEL_RE.match(label)
        base = m.group('name') if m else label
        for spec in requested:
            if base == spec or base.startswith(spec + '_'):
                matched.append(label)
                break
    return matched


def extract_units(dobj):
    """
    Extract column units from a data object's metadata.

    Args:
        dobj: Dobj instance

    Returns:
        Dict mapping column name to unit (only entries with a known unit)
    """
    units = {}
    try:
        variables = dobj.variables
    except Exception:
        return units
    if variables is None or not isinstance(variables, pd.DataFrame):
        return units
    if 'name' not in variables.columns:
        return units
    for _, row in variables.iterrows():
        name = row.get('name')
        unit = row.get('unit')
        if isinstance(name, str) and isinstance(unit, str) and unit.strip():
            units.setdefault(name, unit.strip())
    return units


def download_dobj_data(dobj_uri, requested):
    """
    Download the requested variables from a single data object.

    Args:
        dobj_uri: URI of the data object
        requested: List of requested variable names/prefixes

    Returns:
        Tuple (df, units): pandas DataFrame with a 'TIMESTAMP' column plus
        the matched variable columns (None on failure) and a dict of column
        name -> unit extracted from the data object metadata.
    """
    units = {}
    try:
        dobj = Dobj(dobj_uri)
    except Exception as e:
        print(f"    ! Could not load data object: {e}")
        return None, units

    try:
        labels = list(dobj.colNames)
    except Exception:
        labels = []

    matched = match_variables(requested, labels)
    if not matched:
        print(f"    ! No requested variables available. Available: {labels}")
        return None, units

    units = extract_units(dobj)

    columns_to_download = ['TIMESTAMP'] + matched
    print(f"    Downloading columns: {columns_to_download}")
    try:
        df = dobj.get(columns=columns_to_download)
    except Exception as e:
        print(f"    ! Download error: {e}")
        return None, units

    if df is None or len(df) == 0:
        print("    ! No data returned")
        return None, units

    print(f"    \u2713 Downloaded {len(df)} records")
    return df, units


def process_stations(stations, requested, limit=None):
    """
    Process all stations and download the requested variables.

    Returns a tuple (result_df, variable_units) with:
    - result_df: DataFrame with TIMESTAMP as (Datetime) index and MultiIndex
      columns (station_id, variable), one series per station-variable pair
    - variable_units: dict mapping variable name to unit (where known)

    Args:
        stations: List of station dicts from CSV
        requested: List of requested variable names/prefixes
        limit: Maximum number of data objects to process
    """
    # (station_id, variable) -> Series indexed by TIMESTAMP
    station_data = {}
    variable_units = {}
    processed = 0
    successful = 0
    failed = 0

    print(f"\nStarting data download for {len(stations)} stations...")
    print(f"Requested variables: {requested}")
    print()

    for i, station in enumerate(stations):
        station_id = station['station_id']
        station_name = station.get('station_name', station_id)
        dobj_uris = [uri.strip() for uri in (station.get('data_object_uris') or '').split('; ') if uri.strip()]

        print(f"[{i+1}/{len(stations)}] Station: {station_name} ({station_id})")
        sm_vars = station.get('soil_moisture_variables')
        if sm_vars:
            print(f"  Soil moisture variables (info): {sm_vars}")
        print(f"  Data objects: {len(dobj_uris)}")

        stop_requested = False
        for dobj_uri in dobj_uris:
            if limit and processed >= limit:
                print(f"  Reached limit of {limit} data objects, stopping...")
                stop_requested = True
                break

            processed += 1
            df, units = download_dobj_data(dobj_uri, requested)

            if df is None:
                failed += 1
                continue

            if 'TIMESTAMP' not in df.columns:
                print("    ! No TIMESTAMP column found")
                failed += 1
                continue

            variables = [col for col in df.columns if col != 'TIMESTAMP']

            # Collect units: metadata first, then bracketed-label fallback
            for label in variables:
                unit = units.get(label)
                if not unit:
                    m = UNIT_LABEL_RE.match(label)
                    if m:
                        unit = m.group('unit').strip()
                if unit:
                    variable_units.setdefault(label, unit)

            for label in variables:
                sub = df[['TIMESTAMP', label]].dropna(subset=[label])
                series = sub.set_index('TIMESTAMP')[label]
                key = (station_id, label)
                if key not in station_data:
                    station_data[key] = series
                else:
                    station_data[key] = pd.concat(
                        [station_data[key], series]
                    ).loc[lambda x: ~x.index.duplicated(keep='first')]

            successful += 1
            print(f"    \u2713 Stored {len(df)} records for {variables}")

        if stop_requested:
            break

    print()
    print("Download complete:")
    print(f"  - Data objects processed: {processed}")
    print(f"  - Successful: {successful}")
    print(f"  - Failed/No data: {failed}")

    if not station_data:
        return pd.DataFrame(), variable_units

    result_df = pd.DataFrame(station_data)
    result_df.index.name = 'TIMESTAMP'
    result_df = result_df.sort_index().sort_index(axis=1)
    return result_df, variable_units


def resample_timeseries(df, rule, aggs):
    """
    Resample a time series DataFrame to the given rule.

    A single aggregation keeps the column structure; several aggregations
    add the aggregation function name as the outermost column level.

    Args:
        df: DataFrame with TIMESTAMP as Datetime index
        rule: Pandas resample rule (e.g. '1D')
        aggs: List of aggregation function names (e.g. ['mean'] or ['mean', 'std'])

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

    Columns are (station, variable) tuples, or (agg, station, variable)
    tuples after multi-agg resampling.

    Args:
        df: DataFrame with MultiIndex columns as produced by
            process_stations / resample_timeseries
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


def initialize_auth_with_token(token):
    """
    Initialize authentication using a cpauthtoken.

    Args:
        token: The cpauthtoken string from ICOS Carbon Portal

    Returns:
        Tuple of (meta_client, data_client, success) on success,
        (None, None, False) on failure
    """
    try:
        from icoscp_core.icos import bootstrap
        from icoscp import cpauth

        # Ensure token has the correct format
        if not token.startswith('cpauthToken='):
            token = f'cpauthToken={token}'

        print("  Initializing authentication with provided token...")
        meta_client, data_client = bootstrap.fromCookieToken(token)

        # Initialize cpauth for the legacy icoscp.dobj module to work
        cpauth.init_by(data_client.auth)

        print("  \u2713 Authentication initialized successfully")
        return meta_client, data_client, True

    except Exception as e:
        print(f"  \u2717 Error initializing authentication: {e}")
        return None, None, False


def main():
    """Main function."""
    args = parse_args()

    print("=" * 70)
    print("ICOS Station Time Series Downloader")
    print("=" * 70)
    print(f"Started at: {datetime.now().isoformat()}")
    print()

    requested = [v.strip() for v in args.variables.split(',') if v.strip()]
    aggs = [a.strip() for a in args.agg.split(',') if a.strip()]
    if not requested:
        print("Error: --variables must not be empty.")
        return

    print(f"Requested variables: {requested}")
    if args.resample:
        print(f"Resampling: rule={args.resample}, agg={aggs}")
    print()

    # Handle authentication
    if args.cpauthtoken:
        print("Using provided cpauthtoken for authentication...")
        auth_meta, auth_data, success = initialize_auth_with_token(args.cpauthtoken)
        if not success:
            print("\nFailed to authenticate with provided token. Exiting.")
            return
        print()
    else:
        print("Note: No authentication token provided. Using default credentials file if available.")
        print("To use a token directly, provide --cpauthtoken YOUR_TOKEN_HERE\n")

    # Check input file exists
    if not os.path.exists(args.input_csv):
        print(f"Error: Input file not found: {args.input_csv}")
        print("Please run evaluation_icos.py first to create the CSV files.")
        return

    # Read stations from CSV
    print(f"Reading stations from: {args.input_csv}")
    stations = read_stations_from_csv(args.input_csv)

    if not stations:
        print("No stations found in input file. Exiting.")
        return

    # Test authentication with a small metadata access
    print("\nTesting authentication...")
    try:
        test_uri = stations[0]['data_object_uris'].split('; ')[0].strip()
        dobj = Dobj(test_uri)
        _ = dobj.colNames
        print("  \u2713 Authentication successful (metadata access)")

    except Exception as e:
        print(f"  \u2717 Authentication error: {e}")
        print("\nPlease authenticate with ICOS Carbon Portal first:")
        print("  https://icos-carbon-portal.github.io/pylib/icoscp/authentication/")
        print("\nOption 1: Initialize credentials file (recommended for local use):")
        print('  python -c "from icoscp_core.icos import auth; auth.init_config_file()"')
        print("\nOption 2: Use a token from 'My Account' page:")
        print("  python download_soil_moisture.py --cpauthtoken YOUR_TOKEN_HERE")
        print("  (Make sure token includes 'cpauthToken=' prefix)")
        print()

        response = input("Continue without authentication? (y/n): ")
        if response.lower() != 'y':
            return
        print()

    # Download data from all stations
    all_data, variable_units = process_stations(stations, requested, limit=args.limit)

    # Optional resampling
    if not all_data.empty and args.resample:
        print(f"\nResampling to '{args.resample}' with agg={aggs}...")
        all_data = resample_timeseries(all_data, args.resample, aggs)

    # Write results to CSV
    write_timeseries_csv(all_data, args.output, variable_units)

    # Summary
    print("\n" + "=" * 70)
    print("Download Summary:")
    print(f"  - Stations in input: {len(stations)}")
    print(f"  - Requested variables: {requested}")
    print(f"  - Resampling: {args.resample or 'none'}")
    print(f"  - Output rows: {len(all_data) if all_data is not None else 0}")
    print(f"  - Output columns: {all_data.shape[1] if all_data is not None else 0}")
    print(f"  - Output file: {args.output}")
    print("=" * 70)
    print(f"Completed at: {datetime.now().isoformat()}")


if __name__ == '__main__':
    main()

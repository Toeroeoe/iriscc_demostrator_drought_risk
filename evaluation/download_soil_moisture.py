#!/usr/bin/env python3
"""
Download ICOS surface soil moisture time series data from stations listed in the CSV files.

This script:
1. Reads station data from stations_soil_moisture.csv
2. Downloads soil moisture data for specified soil layers (default: SWC_1)
3. Combines all data into a single CSV file with time series

Output Format:
- TIMESTAMP as the index (datetime)
- Each station as a separate column with units in header: "STATION_ID (m³/m³)"
- Values: Soil water content in m³/m³ (volumetric water content)

Note: Authentication with ICOS Carbon Portal is required to download data.
See: https://icos-carbon-portal.github.io/pylib/icoscp/authentication/

Usage:
    # Download only the first soil layer (default):
    python download_soil_moisture.py

    # Download multiple soil layers:
    python download_soil_moisture.py --levels 1,2,3

    # Limit the number of data objects processed:
    python download_soil_moisture.py --limit 5

    # Specify input/output files:
    python download_soil_moisture.py --input-csv stations_soil_moisture.csv --output soil_data.csv
"""

import os
import csv
import argparse
from datetime import datetime
from icoscp.dobj import Dobj


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Download ICOS soil moisture time series data'
    )
    parser.add_argument(
        '--input-csv', 
        default='stations_soil_moisture.csv',
        help='Input CSV file with station information (default: stations_soil_moisture.csv)'
    )
    parser.add_argument(
        '--output', 
        default='soil_moisture_timeseries.csv',
        help='Output CSV file for time series data (default: soil_moisture_timeseries.csv)'
    )
    parser.add_argument(
        '--levels', 
        default='1',
        help='Comma-separated list of soil moisture levels to download (default: 1)'
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
        help='ICOS Carbon Portal authentication token (cpauthtoken). If provided, this will be used for authentication instead of credentials file.'
    )
    return parser.parse_args()


def get_soil_moisture_columns(levels):
    """
    Generate list of soil moisture column names for specified levels.
    
    Args:
        levels: List of integers representing soil levels
        
    Returns:
        List of column names (e.g., ['SWC_1', 'SWC_2'])
    """
    return [f'SWC_{level}' for level in levels]


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


def check_available_swc_columns(dobj):
    """
    Check which SWC columns are available in the data object.
    
    Args:
        dobj: Dobj instance
        
    Returns:
        List of available SWC column names
    """
    if not dobj.colNames:
        return []
    
    available = []
    for col in dobj.colNames:
        if col.startswith('SWC_'):
            available.append(col)
    
    return available


def download_station_data(dobj_uri, requested_columns, use_default_auth=True):
    """
    Download soil moisture data from a single data object.
    
    Args:
        dobj_uri: URI of the data object
        requested_columns: List of SWC column names requested
        use_default_auth: If True, use default authentication; otherwise, token auth is assumed
        
    Returns:
        pandas DataFrame with data, or None on error
    """
    try:
        # Create Dobj instance
        dobj = Dobj(dobj_uri)
        
        # Check validity (suppress deprecation warning)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            if not dobj.valid:
                print(f"    ! Invalid data object: {dobj_uri}")
                return None
        
        # Check which requested columns are actually available
        available_swc = check_available_swc_columns(dobj)
        
        # Find intersection of requested and available columns
        columns_to_download = ['TIMESTAMP']  # Always include timestamp
        for col in requested_columns:
            if col in available_swc:
                columns_to_download.append(col)
        
        # Check if we have any SWC columns to download
        swc_to_download = [c for c in columns_to_download if c != 'TIMESTAMP']
        if not swc_to_download:
            print(f"    ! No requested SWC columns available. Available: {available_swc}")
            return None
        
        # Download data
        print(f"    Downloading columns: {columns_to_download}")
        df = dobj.get(columns=columns_to_download)
        
        if df is None or len(df) == 0:
            print(f"    ! No data returned")
            return None
        
        print(f"    ✓ Downloaded {len(df)} records")
        return df
        
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return None


def process_stations(stations, swc_columns, limit=None):
    """
    Process all stations and download soil moisture data.
    Returns a pivoted DataFrame with:
    - TIMESTAMP as index
    - Each station's SWC_1 as a separate column (with units in header)
    
    Args:
        stations: List of station dicts from CSV
        swc_columns: List of SWC column names to download
        limit: Maximum number of data objects to process
        
    Returns:
        pandas DataFrame with time series (TIMESTAMP as index, stations as columns)
    """
    import pandas as pd
    
    # Dictionary to collect data: {station_id: {timestamp: swc_value}}
    station_data = {}
    processed = 0
    successful = 0
    failed = 0
    
    print(f"\nStarting data download for {len(stations)} stations...")
    print(f"Requested SWC columns: {swc_columns}")
    print(f"Output format: TIMESTAMP as index, each station as a column")
    print()
    
    for i, station in enumerate(stations):
        station_id = station['station_id']
        station_name = station['station_name']
        dobj_uris = [uri.strip() for uri in station['data_object_uris'].split('; ') if uri.strip()]
        
        print(f"[{i+1}/{len(stations)}] Station: {station_name} ({station_id})")
        print(f"  Available SWC: {station['soil_moisture_variables']}")
        print(f"  Data objects: {len(dobj_uris)}")
        
        for dobj_uri in dobj_uris:
            processed += 1
            
            if limit and processed > limit:
                print(f"  Reached limit of {limit} data objects, stopping...")
                break
            
            df = download_station_data(dobj_uri, swc_columns)
            
            if df is not None and len(df) > 0:
                # Extract TIMESTAMP and the first requested SWC column (e.g., SWC_1)
                if 'TIMESTAMP' not in df.columns:
                    print(f"    ! No TIMESTAMP column found")
                    failed += 1
                    continue
                
                # Find the SWC column to use (prefer SWC_1, or first available)
                swc_col = None
                for col in swc_columns:
                    if col in df.columns:
                        swc_col = col
                        break
                
                if swc_col is None:
                    print(f"    ! No requested SWC column available")
                    failed += 1
                    continue
                
                # Create a Series with TIMESTAMP as index and SWC values
                df_clean = df[[ 'TIMESTAMP', swc_col ]].copy()
                df_clean.columns = ['TIMESTAMP', 'value']
                df_clean = df_clean.dropna(subset=['value'])
                df_clean = df_clean.set_index('TIMESTAMP')['value']
                
                # Store in dictionary
                if station_id not in station_data:
                    station_data[station_id] = df_clean
                else:
                    # Combine with existing data (union of timestamps)
                    station_data[station_id] = pd.concat([station_data[station_id], df_clean]).loc[lambda x: ~x.index.duplicated(keep='first')]
                
                successful += 1
                print(f"    ✓ Downloaded {len(df_clean)} records")
            else:
                failed += 1
        
        if limit and processed >= limit:
            break
    
    print()
    print(f"Download complete:")
    print(f"  - Data objects processed: {processed}")
    print(f"  - Successful: {successful}")
    print(f"  - Failed/No data: {failed}")
    
    if not station_data:
        return pd.DataFrame()
    
    # Create pivoted DataFrame: timestamps as index, stations as columns
    result_df = pd.DataFrame(station_data)
    
    # Sort by timestamp
    result_df = result_df.sort_index()
    
    return result_df


def write_timeseries_csv(df, output_path, station_names=None):
    """
    Write time series data to CSV file with TIMESTAMP as index and stations as columns.
    Column headers include units: "STATION_ID (m³/m³)"
    
    Args:
        df: pandas DataFrame with time series data (index should be TIMESTAMP)
        output_path: Path to output CSV file
        station_names: Optional dict mapping station_id to station_name for reference
    """
    if df is None or len(df) == 0:
        print("\nNo data to write. Exiting.")
        return
    
    # Rename columns to include units: "STATION_ID (m³/m³)"
    df_with_units = df.copy()
    df_with_units.columns = [f"{col} (m³/m³)" for col in df_with_units.columns]
    
    print(f"\nWriting {len(df)} records to {output_path}")
    print(f"Format: TIMESTAMP as index, {len(df.columns)} stations as columns")
    
    # Write to CSV with index (TIMESTAMP)
    df_with_units.to_csv(output_path)
    print(f"Successfully wrote {len(df)} records to {output_path}")
    
    # Print summary of data
    print("\nData summary:")
    print(f"  - Unique stations: {len(df.columns)}")
    print(f"  - Date range: {df.index.min()} to {df.index.max()}")
    print(f"  - Total observations: {df.size}")
    
    # Show column names
    print("\nColumns (stations with units):")
    for col in df_with_units.columns[:10]:
        print(f"  - {col}")
    if len(df_with_units.columns) > 10:
        print(f"  ... and {len(df_with_units.columns) - 10} more")


def initialize_auth_with_token(token):
    """
    Initialize authentication using a cpauthtoken.
    
    Args:
        token: The cpauthtoken string from ICOS Carbon Portal
        
    Returns:
        Tuple of (meta_client, data_client, success) on success, (None, None, False) on failure
    """
    try:
        from icoscp_core.icos import bootstrap
        from icoscp import cpauth
        
        # Ensure token has the correct format
        if not token.startswith('cpauthToken='):
            token = f'cpauthToken={token}'
        
        print(f"  Initializing authentication with provided token...")
        meta_client, data_client = bootstrap.fromCookieToken(token)
        
        # Initialize cpauth for the legacy icoscp.dobj module to work
        cpauth.init_by(data_client.auth)
        
        print("  ✓ Authentication initialized successfully")
        return meta_client, data_client, True
        
    except Exception as e:
        print(f"  ✗ Error initializing authentication: {e}")
        return None, None, False


def main():
    """Main function."""
    args = parse_args()
    
    print("=" * 70)
    print("ICOS Soil Moisture Time Series Downloader")
    print("=" * 70)
    print(f"Started at: {datetime.now().isoformat()}")
    print()
    
    # Parse soil moisture levels
    levels = [int(x.strip()) for x in args.levels.split(',')]
    swc_columns = get_soil_moisture_columns(levels)
    print(f"Downloading soil moisture levels: {swc_columns}")
    print()
    
    # Handle authentication
    auth_meta = None  # Will use default auth
    auth_data = None
    
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
    
    # Test authentication with a small download attempt
    print("\nTesting authentication...")
    try:
        # Try to access a data object (this will fail without auth)
        test_uri = stations[0]['data_object_uris'].split('; ')[0].strip()
        
        # Use default Dobj which will check credentials or cpauth
        from icoscp.dobj import Dobj
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            dobj = Dobj(test_uri)
        
        # This will trigger authentication check
        cols = dobj.colNames
        print("  ✓ Authentication successful (metadata access)")
        
    except Exception as e:
        print(f"  ✗ Authentication error: {e}")
        print("\nPlease authenticate with ICOS Carbon Portal first:")
        print("  https://icos-carbon-portal.github.io/pylib/icoscp/authentication/")
        print("\nOption 1: Initialize credentials file (recommended for local use):")
        print('  python -c "from icoscp_core.icos import auth; auth.init_config_file()"')
        print("\nOption 2: Use a token from 'My Account' page:")
        print("  python download_soil_moisture.py --cpauthtoken YOUR_TOKEN_HERE")
        print("  (Make sure token includes 'cpauthToken=' prefix)")
        print("\nOption 3: Use a token in code:")
        print("  from icoscp_core.icos import bootstrap")
        print("  from icoscp import cpauth")
        print("  meta, data = bootstrap.fromCookieToken('cpauthToken=YOUR_TOKEN_HERE')")
        print("  cpauth.init_by(data.auth)")
        print()
        
        response = input("Continue without authentication? (y/n): ")
        if response.lower() != 'y':
            return
        print()
    
    # Download data from all stations
    import pandas as pd
    all_data = process_stations(stations, swc_columns, limit=args.limit)
    
    # Write results to CSV
    write_timeseries_csv(all_data, args.output)
    
    # Summary
    print("\n" + "=" * 70)
    print("Download Summary:")
    print(f"  - Stations in input: {len(stations)}")
    print(f"  - Total records downloaded: {len(all_data) if all_data is not None else 0}")
    print(f"  - Output file: {args.output}")
    print(f"  - Soil moisture levels: {swc_columns}")
    print("=" * 70)
    print(f"Completed at: {datetime.now().isoformat()}")


if __name__ == '__main__':
    main()

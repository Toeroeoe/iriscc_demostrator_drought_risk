#!/usr/bin/env python3
"""
Discover ICOS stations and their available variables from specified data products.
Creates one CSV file per data type (default: stations_soil_moisture.csv for
etcL2Meteo and stations_fluxnet.csv for etcL2Fluxnet), each with station
metadata (name, coordinates, elevation, country) and the station's data
object URIs ready for use with download.py.

Flux data products and their carbon flux content:
- etcL2Meteo   (ETC L2 Meteo):     SWC_1..n (soil moisture), TA, RH, ...
- etcL2Fluxnet (ETC L2 Fluxnet):   GPP_NT_VUT_REF, GPP_NT_CUT_REF, GPP_DT_*,
                                   NEE_VUT_REF, NEE_CUT_REF, ... (GPP lives here)
- etcL2Fluxes  (ETC L2 Fluxes):    NEE, H, LE, CO2 (no GPP)

Note: This script uses icoscp_core for metadata access. Data downloading requires authentication
with ICOS Carbon Portal (see documentation at https://icos-carbon-portal.github.io/pylib/icoscp/authentication/)

Usage:
    # Default: discover stations with ETC L2 Meteo (soil moisture) AND ETC L2 Fluxnet (GPP/NEE):
    python metadata.py
    
    # Only ETC L2 Meteo (soil moisture):
    python metadata.py --datatype etcL2Meteo
    
    # Only ETC L2 Fluxnet (GPP/NEE, FluxNet-style names):
    python metadata.py --datatype etcL2Fluxnet
    
    # Only ETC L2 Fluxes (NEE/H/LE/CO2; no GPP):
    python metadata.py --datatype etcL2Fluxes
    
    # Multiple data types:
    python metadata.py --datatype etcL2Meteo,etcL2Fluxnet
    
    # Filter variables by pattern (e.g., only SWC variables):
    python metadata.py --variable-pattern SWC
    
    # Filter for GPP and NEE:
    python metadata.py --variable-pattern GPP,NEE
    
    # Show help:
    python metadata.py --help
"""

import os
import re
import csv
import argparse
from datetime import datetime
from icoscp_core.icos import meta

# Data type URIs.
# NOTE: an unknown data type URI silently returns zero data objects, so
# verify URIs against meta.list_datatypes() if a product yields nothing.
# Flux coverage differs per product:
#   etcL2Fluxes  -> NEE, H, LE, CO2 (NO GPP)
#   etcL2Fluxnet -> GPP_NT_VUT_REF, GPP_NT_CUT_REF, GPP_DT_*, NEE_VUT_REF, ...
DATA_TYPES = {
    'etcL2Meteo': 'http://meta.icos-cp.eu/resources/cpmeta/etcL2Meteo',
    'etcL2Fluxes': 'http://meta.icos-cp.eu/resources/cpmeta/etcL2Fluxes',
    'etcL2Fluxnet': 'http://meta.icos-cp.eu/resources/cpmeta/etcL2Fluxnet',
}


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Discover ICOS stations and their available variables'
    )
    parser.add_argument(
        '--datatype',
        default='etcL2Meteo,etcL2Fluxnet',
        help='Comma-separated list of data types to query (default: etcL2Meteo,etcL2Fluxnet). '
             'Options: etcL2Meteo, etcL2Fluxes, etcL2Fluxnet'
    )
    parser.add_argument(
        '--variable-pattern',
        default=None,
        help='Comma-separated list of variable patterns to filter by (e.g., SWC,GPP,NEE). '
             'If not provided, all variables are included.'
    )
    parser.add_argument(
        '--output-dir',
        default=None,
        help='Output directory for CSV files (default: script directory)'
    )
    return parser.parse_args()


def match_variable_patterns(patterns, variables):
    """
    Filter variables by patterns.
    
    Args:
        patterns: List of patterns (e.g., ['SWC', 'GPP'])
        variables: List of variable names
    
    Returns:
        Filtered list of variables matching any pattern
    """
    if not patterns:
        return variables
    
    matched = []
    for var in variables:
        var_upper = var.upper()
        for pattern in patterns:
            pattern_upper = pattern.upper()
            # Exact match or prefix match (e.g., 'SWC' matches 'SWC_1', 'SWC_2')
            if var_upper == pattern_upper or var_upper.startswith(pattern_upper + '_'):
                matched.append(var)
                break
    return matched


def find_stations_with_variables(datatypes, var_patterns):
    """
    Find all ecosystem stations that have data from the specified data types.
    Returns a list of tuples: (station_id, station_uri, all_variables, data_objects)
    
    Args:
        datatypes: List of data type names (e.g., ['etcL2Meteo', 'etcL2Flux'])
        var_patterns: List of variable patterns to filter by (or None for all)
    """
    all_data_objects = []
    
    for dt in datatypes:
        if dt not in DATA_TYPES:
            print(f"  Warning: Unknown data type '{dt}', skipping")
            continue
        
        uri = DATA_TYPES[dt]
        print(f"Fetching {dt} data objects...")
        try:
            objs = meta.list_data_objects(datatype=uri)
            print(f"Found {len(objs)} {dt} data objects")
            if not objs:
                print(f"  Warning: data type '{dt}' returned no data objects. The URI may be "
                      "invalid - check available data types with meta.list_datatypes().")
            all_data_objects.extend(objs)
        except Exception as e:
            print(f"  Error fetching {dt}: {e}")
    
    if not all_data_objects:
        print("No data objects found.")
        return []
    
    # Group by station ID
    station_data = {}
    for obj in all_data_objects:
        if not obj.station_uri:
            continue
        
        station_uri_parts = obj.station_uri.split('/')
        station_id_with_prefix = station_uri_parts[-1]
        
        if station_id_with_prefix.startswith('ES_'):
            station_id = station_id_with_prefix[3:]
        else:
            station_id = station_id_with_prefix
        
        if station_id not in station_data:
            station_data[station_id] = {'uri': obj.station_uri, 'objects': [], 'variables': set()}
        station_data[station_id]['objects'].append(obj)
    
    print(f"Found {len(station_data)} unique stations")
    
    # Check each station for variables
    result = []
    for station_id, data in station_data.items():
        col_labels = []
        try:
            # Union the column labels of ALL data objects of the station:
            # objects can differ (e.g. a variable only present in some years)
            for obj in data['objects']:
                detailed = meta.get_dobj_meta(obj.uri)
                specific_info = getattr(detailed, 'specific_info', None) or getattr(detailed, 'specificInfo', None)
                if specific_info and hasattr(specific_info, 'columns') and specific_info.columns:
                    for col in specific_info.columns:
                        label = getattr(col, 'label', None) or getattr(col, 'name', None) or str(col)
                        if label and label not in col_labels:
                            col_labels.append(label)
        except Exception as e:
            print(f"  Warning: Could not process station {station_id}: {e}")

        if col_labels:
            # Filter by variable patterns if specified
            matched = match_variable_patterns(var_patterns, col_labels) if var_patterns else col_labels
            if matched:
                data['variables'] = set(matched)
                result.append((station_id, data['uri'], list(data['variables']), data['objects']))
    
    print(f"Found {len(result)} stations with matching variables")
    return result


def get_all_stations_metadata(station_ids):
    """
    Get metadata for all stations from the stations list.
    Returns a dict mapping station_id to station metadata.
    """
    print("\nFetching station metadata...")
    all_stations = meta.list_stations()
    
    # Create a lookup dict
    station_lookup = {}
    for station in all_stations:
        station_lookup[station.id] = {
            'station_id': station.id,
            'station_name': station.label,
            'latitude': station.lat,
            'longitude': station.lon,
            'elevation': station.elevation,
            'country_code': station.country_code,
            'ecosystem_type': 'Ecosystem (ES)'
        }
    
    # Filter to only the stations we need
    result = {}
    for station_id in station_ids:
        if station_id in station_lookup:
            result[station_id] = station_lookup[station_id]
        else:
            print(f"  Warning: Station {station_id} not found in station list")
    
    print(f"Retrieved metadata for {len(result)} stations")
    return result


def create_station_metadata_csv(stations_with_sm, station_metadata, output_path):
    """
    Create a CSV file with station metadata including coordinates and landcover.
    """
    print(f"\nCreating station metadata CSV: {output_path}")
    
    fieldnames = ['station_uri', 'station_id', 'station_name', 'latitude', 'longitude', 
                  'elevation', 'country_code', 'ecosystem_type', 'soil_moisture_variables']
    
    with open(output_path, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for station_id, station_uri, soil_cols, objs in stations_with_sm:
            metadata = station_metadata.get(station_id, {})
            row = {
                'station_uri': station_uri,
                'station_id': station_id,
                'station_name': metadata.get('station_name', ''),
                'latitude': metadata.get('latitude', ''),
                'longitude': metadata.get('longitude', ''),
                'elevation': metadata.get('elevation', ''),
                'country_code': metadata.get('country_code', ''),
                'ecosystem_type': metadata.get('ecosystem_type', 'Ecosystem (ES)'),
                'soil_moisture_variables': '; '.join(soil_cols)
            }
            writer.writerow(row)
    
    print(f"  Wrote {len(stations_with_sm)} stations to {output_path}")


def create_stations_csv(stations, station_metadata, output_path, variable_label="variables"):
    """
    Create a CSV file listing stations and their variables.
    
    Args:
        stations: List of tuples (station_id, station_uri, variables, data_objects)
        station_metadata: Dict of station metadata
        output_path: Output file path
        variable_label: Label for the variable column header (e.g., 'soil_moisture_variables' or 'flux_variables')
    """
    print(f"\nCreating stations list CSV: {output_path}")
    
    fieldnames = ['station_uri', 'station_id', 'station_name', 'latitude', 'longitude',
                  variable_label, 'num_data_objects', 'data_object_uris']
    
    with open(output_path, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for station_id, station_uri, variables, objs in stations:
            metadata = station_metadata.get(station_id, {})
            row = {
                'station_uri': station_uri,
                'station_id': station_id,
                'station_name': metadata.get('station_name', ''),
                'latitude': metadata.get('latitude', ''),
                'longitude': metadata.get('longitude', ''),
                variable_label: '; '.join(sorted(variables)),
                'num_data_objects': len(objs),
                'data_object_uris': '; '.join([obj.uri for obj in objs])
            }
            writer.writerow(row)
    
    print(f"  Wrote {len(stations)} stations to {output_path}")


def print_station_summary(stations_with_sm, station_metadata):
    """
    Print a summary of stations with soil moisture data.
    """
    print("\n" + "=" * 70)
    print("Stations with Soil Moisture Data Summary")
    print("=" * 70)
    
    for station_id, station_uri, soil_cols, objs in stations_with_sm:
        metadata = station_metadata.get(station_id, {})
        name = metadata.get('station_name', station_id)
        country = metadata.get('country_code', '')
        lat = metadata.get('latitude', '')
        lon = metadata.get('longitude', '')
        
        print(f"\n  Station: {name} ({station_id})")
        print(f"    Country: {country}")
        print(f"    Coordinates: {lat}, {lon}")
        print(f"    Soil moisture variables: {', '.join(soil_cols)}")
        print(f"    Data objects: {len(objs)}")


def main():
    """
    Main function to discover stations and create CSV files.
    Respects --datatype and --variable-pattern arguments.
    """
    args = parse_args()
    
    print("=" * 70)
    print("ICOS Station Discovery Script")
    print("=" * 70)
    print(f"Started at: {datetime.now().isoformat()}")
    print()
    
    # Output directory
    output_dir = args.output_dir or os.path.dirname(os.path.abspath(__file__))
    
    # Parse datatypes
    datatypes = [dt.strip() for dt in args.datatype.split(',') if dt.strip()]
    
    # Parse variable patterns
    var_patterns = None
    if args.variable_pattern:
        var_patterns = [p.strip() for p in args.variable_pattern.split(',') if p.strip()]
    
    print(f"Querying data types: {datatypes}")
    print(f"Variable patterns: {var_patterns or 'all'}")
    print()
    
    # Discover stations for each data type
    all_stations = []
    output_files = {}
    
    for dt in datatypes:
        if dt not in DATA_TYPES:
            print(f"Warning: Unknown data type '{dt}', skipping")
            continue
        
        print("-" * 70)
        print(f"Discovering stations with {dt} data...")
        print("-" * 70)
        
        stations = find_stations_with_variables([dt], var_patterns)
        all_stations.extend(stations)
        
        # Determine output filename based on data type
        if dt == 'etcL2Meteo':
            output_file = 'stations_soil_moisture.csv'
            label = 'soil_moisture_variables'
        elif dt == 'etcL2Fluxes':
            output_file = 'stations_flux.csv'
            label = 'flux_variables'
        elif dt == 'etcL2Fluxnet':
            output_file = 'stations_fluxnet.csv'
            label = 'fluxnet_variables'
        else:
            output_file = f'stations_{dt}.csv'
            label = 'variables'
        
        if stations:
            output_files[output_file] = (stations, label)
    
    if not all_stations:
        print("\nNo stations found with the requested data types/variables. Exiting.")
        return
    
    # Get metadata for all unique stations
    all_station_ids = list(set([s[0] for s in all_stations]))
    station_metadata = get_all_stations_metadata(all_station_ids)
    
    # Create CSV files
    print("\n" + "-" * 70)
    print("Creating CSV files...")
    print("-" * 70)
    
    for filename, (stations, label) in output_files.items():
        csv_path = os.path.join(output_dir, filename)
        create_stations_csv(stations, station_metadata, csv_path, label)
    
    # Summary
    print("\n" + "=" * 70)
    print("Discovery Summary:")
    for filename, (stations, _) in output_files.items():
        print(f"  - {filename}: {len(stations)} stations")
    print("\nTo download data:")
    for filename in output_files.keys():
        print(f"  python download.py --input-csv {filename} --variables YOUR_VARIABLES")
    print("=" * 70)
    print(f"Completed at: {datetime.now().isoformat()}")


if __name__ == '__main__':
    main()

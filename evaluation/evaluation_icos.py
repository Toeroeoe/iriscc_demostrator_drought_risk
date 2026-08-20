#!/usr/bin/env python3
"""
Download ICOS surface soil moisture data for all ecosystem (ES) stations with Level 2 data.
Creates two CSV files:
1. stations_soil_moisture.csv - List of stations with soil moisture data
2. station_metadata.csv - Metadata including landcover, coordinates for all ES stations with L2 data

Note: This script uses icoscp_core for metadata access. Data downloading requires authentication
with ICOS Carbon Portal (see documentation at https://icos-carbon-portal.github.io/pylib/icoscp/authentication/)
"""

import os
import csv
from datetime import datetime
from icoscp_core.icos import meta

# Data type URI for ETC L2 Meteo (contains soil moisture variables)
ETC_L2_METEO_URI = 'http://meta.icos-cp.eu/resources/cpmeta/etcL2Meteo'


def find_stations_with_soil_moisture():
    """
    Find all ecosystem stations that have ETC L2 Meteo data with soil moisture variables.
    Returns a list of tuples: (station_id, station_uri, soil_moisture_columns, data_objects)
    """
    print("Fetching ETC L2 Meteo data objects...")
    meteo_objs = meta.list_data_objects(datatype=ETC_L2_METEO_URI)
    print(f"Found {len(meteo_objs)} ETC L2 Meteo data objects")
    
    # Group by station ID (extract from station_uri)
    station_data = {}
    for obj in meteo_objs:
        if not obj.station_uri:
            continue
        
        # Extract station ID from URI (format: http://meta.icos-cp.eu/resources/stations/ES_XXX)
        station_uri_parts = obj.station_uri.split('/')
        station_id_with_prefix = station_uri_parts[-1]  # e.g., "ES_FI-Lom"
        
        # Remove the "ES_" prefix to get the actual station ID
        if station_id_with_prefix.startswith('ES_'):
            station_id = station_id_with_prefix[3:]  # Remove "ES_" prefix
        else:
            station_id = station_id_with_prefix
        
        if station_id not in station_data:
            station_data[station_id] = {'uri': obj.station_uri, 'objects': []}
        station_data[station_id]['objects'].append(obj)
    
    print(f"Found {len(station_data)} unique stations with ETC L2 Meteo data")
    
    # Check each station for soil moisture variables
    stations_with_sm = []
    for station_id, data in station_data.items():
        obj = data['objects'][0]
        try:
            detailed = meta.get_dobj_meta(obj.uri)
            specific_info = getattr(detailed, 'specific_info', None) or getattr(detailed, 'specificInfo', None)
            
            if specific_info and hasattr(specific_info, 'columns') and specific_info.columns:
                col_labels = []
                for col in specific_info.columns:
                    if hasattr(col, 'label'):
                        col_labels.append(col.label)
                    elif hasattr(col, 'name'):
                        col_labels.append(col.name)
                    else:
                        col_labels.append(str(col))
                
                # Find soil moisture columns
                soil_cols = [c for c in col_labels if 'soil' in c.lower() or 'moisture' in c.lower() or 
                           'swc' in c.lower() or 'theta' in c.lower() or 'vwc' in c.lower()]
                
                if soil_cols:
                    stations_with_sm.append((station_id, data['uri'], soil_cols, data['objects']))
        except Exception as e:
            print(f"  Warning: Could not process station {station_id}: {e}")
    
    print(f"Found {len(stations_with_sm)} stations with soil moisture data")
    return stations_with_sm


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


def create_stations_list_csv(stations_with_sm, station_metadata, output_path):
    """
    Create a CSV file listing stations with soil moisture data and their data objects.
    """
    print(f"\nCreating stations soil moisture list CSV: {output_path}")
    
    fieldnames = ['station_uri', 'station_id', 'station_name', 'latitude', 'longitude',
                  'soil_moisture_variables', 'num_data_objects', 'data_object_uris']
    
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
                'soil_moisture_variables': '; '.join(soil_cols),
                'num_data_objects': len(objs),
                'data_object_uris': '; '.join([obj.uri for obj in objs])
            }
            writer.writerow(row)
    
    print(f"  Wrote {len(stations_with_sm)} stations to {output_path}")


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
    Main function to orchestrate the CSV creation.
    """
    print("=" * 70)
    print("ICOS Surface Soil Moisture Data Discovery Script")
    print("=" * 70)
    print(f"Started at: {datetime.now().isoformat()}")
    print()
    
    # Output directory (same as script location)
    output_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Step 1: Find stations with soil moisture data
    print("\nStep 1: Finding ecosystem stations with soil moisture data...")
    stations_with_sm = find_stations_with_soil_moisture()
    
    if not stations_with_sm:
        print("\nNo stations with soil moisture data found. Exiting.")
        return
    
    # Step 2: Get station metadata
    station_ids = [s[0] for s in stations_with_sm]
    station_metadata = get_all_stations_metadata(station_ids)
    
    # Step 3: Create station metadata CSV
    metadata_csv = os.path.join(output_dir, 'station_metadata.csv')
    create_station_metadata_csv(stations_with_sm, station_metadata, metadata_csv)
    
    # Step 4: Create stations list CSV
    stations_csv = os.path.join(output_dir, 'stations_soil_moisture.csv')
    create_stations_list_csv(stations_with_sm, station_metadata, stations_csv)
    
    # Step 5: Print summary
    print_station_summary(stations_with_sm, station_metadata)
    
    print("\n" + "=" * 70)
    print("Summary:")
    print(f"  - Total stations with soil moisture data: {len(stations_with_sm)}")
    print(f"  - Station metadata CSV: {metadata_csv}")
    print(f"  - Stations soil moisture list CSV: {stations_csv}")
    print("\nNote: To download actual data, authentication with ICOS Carbon Portal")
    print("      is required. See: https://icos-carbon-portal.github.io/pylib/icoscp/authentication/")
    print("=" * 70)
    print(f"Completed at: {datetime.now().isoformat()}")


if __name__ == '__main__':
    main()

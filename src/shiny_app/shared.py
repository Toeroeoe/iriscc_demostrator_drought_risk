import glob
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pandas as pd

app_dir = Path(__file__).parent
data_dir = Path(__file__).parent.parent.parent / "data"
images = Path(__file__).parent.parent.parent / "images"


class _LazyStatFiles:
    """Lazy, dict-like access to one decadal statistic stored as per-decade files.

    Maps ``decade_start_year -> 2-D float32 array`` but only reads a decade's
    file the first time that year is requested. Implements just the mapping
    operations the app uses: truthiness, ``in``, ``keys()`` and indexing.
    """

    def __init__(self, files: dict, varname: str):
        self._files = dict(files)
        self._var = varname
        self._cache: dict = {}

    def __bool__(self) -> bool:
        return bool(self._files)

    def __contains__(self, year: int) -> bool:
        return year in self._files

    def keys(self):
        return self._files.keys()

    def __getitem__(self, year: int):
        if year not in self._cache:
            with nc.Dataset(self._files[year]) as ds:
                self._cache[year] = np.ma.filled(
                    ds.variables[self._var][0].astype(np.float32), np.nan
                )
        return self._cache[year]


# ── Agricultural (SMI) decadal data ─────────────────────────────────────────
# Files: data/decadal_SMI/<model>/<model><decade>_<stat>.nc  (variable "SMI"),
# e.g. CLM5/CLM51960_dfreq.nc. Two hydrological models (CLM5, mHM) are shown
# side by side; each statistic/decade is loaded lazily on first access.

_smi_dir = data_dir / "decadal_SMI"
SMI_MODELS = ("CLM5", "mHM")
SMI_STATS = ("mean", "dfreq", "min", "maxspell")


def _discover_smi_files(model: str, stat: str) -> dict:
    """Map decade start year → file path for a given SMI model and statistic.
    
    Handles both filename formats:
    - CLM5_0.2_1960_mean.nc (with threshold)
    - CLM51960_mean.nc (legacy, no threshold)
    """
    out: dict = {}
    # Try the format with threshold first: CLM5_0.2_1960_mean.nc
    pattern_with_thresh = _smi_dir / model / f"{model}_*_{stat}.nc"
    for _f in sorted(glob.glob(str(pattern_with_thresh))):
        _m = re.search(rf"{model}_[\d.]+_(\d{{4}})_{stat}\.nc$", _f)
        if _m:
            out[int(_m.group(1))] = _f
            continue
    # Try legacy format without threshold: CLM51960_mean.nc
    pattern_legacy = _smi_dir / model / f"{model}*_{stat}.nc"
    for _f in sorted(glob.glob(str(pattern_legacy))):
        _m = re.search(rf"{model}(\d{{4}})_{stat}\.nc$", _f)
        if _m:
            out[int(_m.group(1))] = _f
    return out


_smi_files = {
    model: {stat: _discover_smi_files(model, stat) for stat in SMI_STATS}
    for model in SMI_MODELS
}

# Helper to discover files for a specific threshold
def _discover_smi_files_by_thresh(model: str, threshold: float, stat: str) -> dict:
    """Map decade start year → file path for a given SMI model, threshold, and statistic."""
    out: dict = {}
    pattern = f"{model}_{threshold}_*{stat}.nc"
    for _f in sorted(glob.glob(str(_smi_dir / model / pattern))):
        _m = re.search(rf"{model}_{threshold}_(\d{{4}})_{stat}\.nc$", _f)
        if _m:
            out[int(_m.group(1))] = _f
    return out

# Per-model, per-statistic lazy data: SMI_STAT_DATA[model][stat][decade_year].
SMI_STAT_DATA = {
    model: {
        stat: _LazyStatFiles(_smi_files[model][stat], "SMI") for stat in SMI_STATS
    }
    for model in SMI_MODELS
}

# 1-D lat/lon (regular grid) – identical across files, loaded once if present.
# None when the SMI dataset has not been synced yet (app degrades gracefully).
SMI_lat = None
SMI_lon = None
_clm5_mean_files = _smi_files["CLM5"]["mean"]
if _clm5_mean_files:
    with nc.Dataset(_clm5_mean_files[min(_clm5_mean_files)]) as _ds:
        SMI_lat = _ds.variables["lat"][:].astype(np.float32)
        SMI_lon = _ds.variables["lon"][:].astype(np.float32)

# Decade start years available for SMI (from the CLM5 mean files).
smi_decade_years = sorted(_clm5_mean_files.keys())

# ── SMI Threshold configuration ───────────────────────────────────────────────
# SMI uses soil moisture thresholds (0.2, 0.3, etc.)
# Discover available thresholds from files
SMI_THRESHOLDS = []
_smi_pattern = _smi_dir / "*/*_*_*.nc"
for _f in sorted(glob.glob(str(_smi_pattern))):
    # Pattern: <model>_<threshold>_<decade>_<stat>.nc
    _m = re.search(r"[A-Z]+_(-?[\d.]+)_\d{4}_\w+\.nc$", _f)
    if _m:
        thresh = float(_m.group(1))
        if thresh not in SMI_THRESHOLDS:
            SMI_THRESHOLDS.append(thresh)
SMI_THRESHOLDS.sort()

DEFAULT_SMI_THRESH = 0.2 if 0.2 in SMI_THRESHOLDS else (
    SMI_THRESHOLDS[0] if SMI_THRESHOLDS else None
)

# Per-model, per-threshold, per-statistic lazy data
SMI_STAT_DATA_BY_THRESH: dict = {
    model: {}
    for model in SMI_MODELS
}
for model in SMI_MODELS:
    for thresh in SMI_THRESHOLDS:
        SMI_STAT_DATA_BY_THRESH[model][thresh] = {}
        for stat in SMI_STATS:
            files = _discover_smi_files_by_thresh(model, thresh, stat)
            SMI_STAT_DATA_BY_THRESH[model][thresh][stat] = _LazyStatFiles(files, "SMI")




# Default SMI data access
SMI_STAT_DATA_DEFAULT = {}
if DEFAULT_SMI_THRESH is not None:
    # Build default data mapping only when a valid default threshold exists.
    SMI_STAT_DATA_DEFAULT = {
        model: {
            stat: SMI_STAT_DATA_BY_THRESH[model][DEFAULT_SMI_THRESH][stat]
            for stat in SMI_STATS
        }
        for model in SMI_MODELS
    }

# ── Streamflow / discharge data ───────────────────────────────────────────────
# Loaded only when present. When the discharge dataset has not been synced yet
# the app degrades gracefully: an empty gauge map and no time series, instead
# of failing to import.

_streamflow_dir = data_dir / "streamflow"
_discharge_path = _streamflow_dir / "discharge.nc"
_gauge_csv_path = _streamflow_dir / "grdc_iriscc_pass2_subset_extended.csv"

_base_dt = datetime(1950, 1, 1)

# Defaults used when the dataset is absent.
_discharge_ds = None
discharge_time = pd.DatetimeIndex([])
gauge_meta = pd.DataFrame(
    columns=["gauge_id", "lat", "long", "station", "river", "country"]
)

if _discharge_path.exists() and _gauge_csv_path.exists():
    # Gauge metadata (all stations in the CSV)
    _gauge_meta_raw = pd.read_csv(_gauge_csv_path)

    # Open discharge NetCDF – kept open for the app lifetime; vars load lazily
    _discharge_ds = nc.Dataset(_discharge_path)

    # Set of gauge IDs present in the NC file (zero-padded 10-digit strings)
    _nc_gauge_ids = frozenset(
        v[5:] for v in _discharge_ds.variables if v.startswith("Qobs_")
    )

    # Filter metadata to gauges that have NC data and valid coordinates
    gauge_meta = _gauge_meta_raw.assign(
        gauge_id=_gauge_meta_raw["grdc_no"].astype(str).str.zfill(10)
    )
    gauge_meta = (
        gauge_meta[gauge_meta["gauge_id"].isin(list(_nc_gauge_ids))]
        .dropna(subset=["lat", "long"])  # type: ignore[call-overload]
        .reset_index(drop=True)
    )

    # Precompute daily time axis: hours since 1950-01-01 → pandas DatetimeIndex
    _time_hours = _discharge_ds.variables["time"][:]
    discharge_time = pd.DatetimeIndex(
        [_base_dt + timedelta(hours=int(h)) for h in _time_hours]
    )


def get_gauge_discharge(gauge_id: str):
    """Return (qobs, qsim) float64 numpy arrays for a gauge_id.

    gauge_id must be a zero-padded 10-digit string (e.g. '0006112080').
    Masked / fill values are replaced with NaN.
    Returns (None, None) when the gauge is absent, or when the discharge
    dataset has not been synced yet.
    """
    if _discharge_ds is None:
        return None, None
    qobs_var = _discharge_ds.variables.get(f"Qobs_{gauge_id}")
    qsim_var = _discharge_ds.variables.get(f"Qsim_{gauge_id}")
    if qobs_var is None and qsim_var is None:
        return None, None
    qobs = (
        np.ma.filled(qobs_var[:].astype(float), np.nan)
        if qobs_var is not None
        else None
    )
    qsim = (
        np.ma.filled(qsim_var[:].astype(float), np.nan)
        if qsim_var is not None
        else None
    )
    return qobs, qsim


def _build_gauge_map_html(gauge_df: pd.DataFrame) -> str:
    """Generate a self-initialising Leaflet.js map HTML string.

    Uses EPSG:3035 LAEA Europe (equal-area projection) via Proj4Leaflet.
    Background is Natural Earth 50 m land + lakes GeoJSON (no tile server needed).
    Gauge markers live in a dedicated pane (z-index 620) so they always render
    above the GeoJSON land layer, while the tooltip pane (z-index 650) stays on top.
    Communicates marker clicks back to Shiny via Shiny.setInputValue('selected_gauge').
    """
    markers = [
        {
            "id": str(row["gauge_id"]),
            "lat": float(row["lat"]),
            "lon": float(row["long"]),
            "station": str(row["station"]),
            "river": str(row["river"]),
            "country": str(row["country"]),
        }
        for _, row in gauge_df.iterrows()
    ]
    markers_json = json.dumps(markers)

    return f"""
<div id="gauge-map"
     style="height:450px; width:100%; max-width: 600px; margin: 0 auto; border-radius:6px; overflow:hidden;">
</div>
<style>
  .gauge-tooltip {{
    background: #2a2a2a !important;
    border: 1px solid #555 !important;
    color: #eee !important;
    font-family: Inter, system-ui, sans-serif;
    font-size: 12px;
    padding: 4px 8px;
    border-radius: 4px;
  }}
  .gauge-tooltip.leaflet-tooltip-top::before   {{ border-top-color:   #555 !important; }}
  .gauge-tooltip.leaflet-tooltip-left::before  {{ border-left-color:  #555 !important; }}
  /* Keep attribution readable on the light ocean background */
  .leaflet-control-attribution {{ background: rgba(255,255,255,0.7) !important; color: #333 !important; font-size: 10px; }}
</style>
<script>
(function () {{
  var data   = {markers_json};
  var active = null;

  var defaultStyle = {{
    radius: 6, fillColor: '#375a7f', color: '#46b8da',
    weight: 1.5, opacity: 0.9, fillOpacity: 0.75
  }};
  var hoverStyle = {{
    radius: 8, fillColor: '#46b8da', color: '#ffffff',
    weight: 2, opacity: 1, fillOpacity: 0.9
  }};
  var activeStyle = {{
    radius: 9, fillColor: '#f0ad4e', color: '#ffffff',
    weight: 2, opacity: 1, fillOpacity: 1
  }};

  var map;

  function initMap() {{
    // EPSG:3035 LAEA Europe — true equal-area projection (EU standard).
    // Resolutions are in metres/pixel; the array index is the Leaflet zoom level.
    var laea = new L.Proj.CRS(
      'EPSG:3035',
      '+proj=laea +lat_0=52 +lon_0=10 +x_0=4321000 +y_0=3210000 +ellps=GRS80 +units=m +no_defs',
      {{ resolutions: [8000, 4000, 2000, 1000, 500, 250, 125, 62.5, 31.25] }}
    );

    map = L.map('gauge-map', {{ crs: laea, maxZoom: 8 }});

    // Calculate bounds from all markers and fit the map to show all of them
    if (data.length > 0) {{
      var bounds = L.latLngBounds(data.map(function(d) {{ return [d.lat, d.lon]; }}));
      map.fitBounds(bounds, {{ padding: [50, 50] }});
    }} else {{
      map.setView([54.0, 15.0], 1);
    }}

    // Set up listener for station selector dropdown changes (using jQuery)
    // This needs to be set up after map is created
    $(document).on('change', '#station_select', function() {{
      var gaugeId = $(this).val();
      if (gaugeId) {{
        // Find the marker with this gaugeId
        map.eachLayer(function (layer) {{
          if (layer.gaugeId === gaugeId) {{
            // Activate this marker
            if (active && active !== layer) active.setStyle(defaultStyle);
            layer.setStyle(activeStyle);
            active = layer;
            // Set the selected_gauge input value
            if (typeof Shiny !== 'undefined') {{
              Shiny.setInputValue('selected_gauge', gaugeId, {{ priority: 'event' }});
            }}
            // Pan map to the marker
            map.panTo([layer.getLatLng()]);
          }}
        }});
      }}
    }});

    // Check if there's a default selection and apply it
    if (typeof Shiny !== 'undefined' && $('#station_select').val()) {{
      setTimeout(function() {{
        $('#station_select').trigger('change');
      }}, 100);  // Small delay to ensure map is fully initialized
    }}

    // Ocean colour via CSS (no tile layer needed)
    document.getElementById('gauge-map').style.background = '#a6cee3';

    // Dedicated pane for gauge markers so they always render above the GeoJSON
    // land layer regardless of the order in which async fetches complete.
    // z-index 620: above overlayPane (400), below tooltipPane (650).
    map.createPane('gaugePane');
    map.getPane('gaugePane').style.zIndex = 620;
    map.getPane('gaugePane').style.pointerEvents = 'auto';

    // Land masses: Natural Earth 50 m – better coastline detail.
    // Leaflet reprojects WGS-84 GeoJSON to the map CRS automatically.
    fetch('https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson')
      .then(function (r) {{ return r.json(); }})
      .then(function (geo) {{
        L.geoJSON(geo, {{
          style: {{
            fillColor: '#636363',
            fillOpacity: 0.9,
            color:      '#999',
            weight:     0.5
          }}
        }}).addTo(map);
      }})
      .catch(function (err) {{
        console.warn('Basemap land layer not available:', err.message);
        // Fallback: draw simplified Europe outline
        var europeOutline = [[71, -25], [71, 40], [35, 40], [35, -25], [71, -25]];
        L.polygon(europeOutline, {{
          fillColor: '#636363',
          fillOpacity: 0.2,
          color: '#999',
          weight: 1
        }}).addTo(map).bindTooltip('Land layer unavailable', {{permanent: true, direction: 'center'}});
      }});

    // Major lakes (50 m) – paint them in ocean colour so they read as water.
    fetch('https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_lakes.geojson')
      .then(function (r) {{ return r.json(); }})
      .then(function (geo) {{
        L.geoJSON(geo, {{
          style: {{
            fillColor: '#a6cee3',
            fillOpacity: 1.0,
            color:      '#888',
            weight:     0.4
          }}
        }}).addTo(map);
      }})
      .catch(function (err) {{
        console.warn('Basemap lakes layer not available:', err.message);
      }});

    data.forEach(function (g) {{
      var m = L.circleMarker([g.lat, g.lon],
                             Object.assign({{pane: 'gaugePane'}}, defaultStyle)).addTo(map);

      // Store gauge ID on the marker for easy lookup
      m.gaugeId = g.id;

      m.bindTooltip(
        '<b>' + g.station + '</b><br><i>' + g.river + '</i> &mdash; ' + g.country,
        {{ sticky: true, className: 'gauge-tooltip' }}
      );

      m.on('mouseover', function () {{
        if (m !== active) m.setStyle(hoverStyle);
      }});
      m.on('mouseout', function () {{
        if (m !== active) m.setStyle(defaultStyle);
      }});
      m.on('click', function () {{
        if (active && active !== m) active.setStyle(defaultStyle);
        m.setStyle(activeStyle);
        m.bringToFront();
        active = m;
        if (typeof Shiny !== 'undefined') {{
          Shiny.setInputValue('selected_gauge', g.id, {{ priority: 'event' }});
        }}
        // Also update the dropdown to match the selected station
        $('#station_select').val(g.id).trigger('change');
      }});
    }});
  }}

  // Initialise only once the container is visible (Shiny hides inactive tabs).
  var el = document.getElementById('gauge-map');
  if (el.offsetWidth > 0 && el.offsetHeight > 0) {{
    initMap();
    // Bring the initially selected marker to front after map initialization
    setTimeout(function() {{
      var selectedId = $('#station_select').val();
      if (selectedId) {{
        data.forEach(function(g) {{
          if (g.id === selectedId) {{
            // Find the marker with this ID and bring to front
            map.eachLayer(function(layer) {{
              if (layer.gaugeId === selectedId && layer.bringToFront) {{
                layer.setStyle(activeStyle); // Ensure active style
                layer.bringToFront();
              }}
            }});
          }}
        }});
      }}
    }}, 100); // Small delay to ensure map is fully rendered
  }} else {{
    var ro = new ResizeObserver(function (entries) {{
      if (entries[0].contentRect.width > 0 && entries[0].contentRect.height > 0) {{
        ro.disconnect();
        initMap();
      }}
    }});
    ro.observe(el);
  }}
}})();
</script>
"""


# Built once at import time – reused for the lifetime of the Shiny process
gauge_map_html = _build_gauge_map_html(gauge_meta)

# ── SPI (Standardized Precipitation Index) decadal data ──────────────────────
# All SPI data is loaded lazily (see _LazyStatFiles): only the file paths are
# discovered at import time, and each decade's grid is read on first access.
# If the SPI dataset has not been added yet, the app degrades gracefully — the
# meteorological maps show an "not available" message instead of crashing.
#
# File naming: SXI_P_<agg>_<threshold>_<decade>_<stat>.nc
#   - agg: aggregation period (e.g., 31D, 92D, 183D, 365D)
#   - threshold: drought threshold (e.g., -1, -1.5, -2)
#   - decade: start year of decade (1960, 1970, ..., 2010)
#   - stat: statistic (mean, dfreq, min, maxspell)

_spi_dir = data_dir / "decadal_SPI"

# Available SPI aggregation periods and thresholds (determined from files)
SPI_AGGREGATION_PERIODS = []
SPI_THRESHOLDS = []
SPI_MODELS = ["ERA5"]  # Currently only ERA5 forcing data available

# Parse file patterns to discover available dimensions
_spi_pattern = _spi_dir / "SXI_P_*_*_*.nc"
for _f in sorted(glob.glob(str(_spi_pattern))):
    _m = re.search(r"SXI_P_([\d]+D)_(-?[\d.]+)_\d{4}_\w+\.nc$", _f)
    if _m:
        agg = _m.group(1)
        thresh = float(_m.group(2))
        if agg not in SPI_AGGREGATION_PERIODS:
            SPI_AGGREGATION_PERIODS.append(agg)
        if thresh not in SPI_THRESHOLDS:
            SPI_THRESHOLDS.append(thresh)

SPI_AGGREGATION_PERIODS.sort()
SPI_THRESHOLDS.sort()


def _discover_spi_files(pattern_suffix: str) -> dict:
    """Map (aggregation, threshold, decade) → file path for SPI data.
    
    Returns a nested dict: agg_period → threshold → decade → file_path
    """
    out: dict = {}
    for _f in sorted(glob.glob(str(_spi_dir / f"SXI_P_*_*_{pattern_suffix}.nc"))):
        _m = re.search(rf"SXI_P_([\d]+D)_(-?[\d.]+)_(\d{{4}})_{pattern_suffix}\.nc$", _f)
        if _m:
            agg = _m.group(1)
            thresh = float(_m.group(2))
            decade = int(_m.group(3))
            if agg not in out:
                out[agg] = {}
            if thresh not in out[agg]:
                out[agg][thresh] = {}
            out[agg][thresh][decade] = _f
    return out


def _discover_spi_mean_files() -> dict:
    """Map (aggregation, threshold, decade_start) → file path for SPI mean files.
    
    The repository contains two possible naming conventions for the mean statistic:
    * ``SXI_P_<agg>_<thresh>_<start>_<end>_timmean.nc`` (timmean files)
    * ``SXI_P_<agg>_<thresh>_<start>_mean.nc`` (simple mean files).  This function
      discovers both and stores them under the same ``out`` structure so the rest of
      the code can treat ``"mean"`` like any other statistic.
    """
    out: dict = {}
    # 1. Timmean style (if present)
    for _f in sorted(glob.glob(str(_spi_dir / "SXI_P_*_*_*_timmean.nc"))):
        _m = re.search(r"SXI_P_([\d]+D)_(-?[\d.]+)_(\d{4})_\d{4}_timmean.nc$", _f)
        if _m:
            agg = _m.group(1)
            thresh = float(_m.group(2))
            decade = int(_m.group(3))
            out.setdefault(agg, {}).setdefault(thresh, {})[decade] = _f
    # 2. Simple mean style (the files that actually exist in this repo)
    for _f in sorted(glob.glob(str(_spi_dir / "SXI_P_*_*_*_mean.nc"))):
        _m = re.search(r"SXI_P_([\d]+D)_(-?[\d.]+)_(\d{4})_mean.nc$", _f)
        if _m:
            agg = _m.group(1)
            thresh = float(_m.group(2))
            decade = int(_m.group(3))
            out.setdefault(agg, {}).setdefault(thresh, {})[decade] = _f
    return out


# Discover SPI mean files
_spi_mean_files_raw = _discover_spi_mean_files()

# Extract decade years from mean files (all combinations that exist)
_spi_decade_years = set()
for agg in _spi_mean_files_raw:
    for thresh in _spi_mean_files_raw[agg]:
        _spi_decade_years.update(_spi_mean_files_raw[agg][thresh].keys())

SPI_DECADE_YEARS = sorted(_spi_decade_years)

# Current defaults (will be controlled by UI)
DEFAULT_SPI_AGG = "92D" if "92D" in SPI_AGGREGATION_PERIODS else (
    SPI_AGGREGATION_PERIODS[0] if SPI_AGGREGATION_PERIODS else None
)
DEFAULT_SPI_THRESH = -1.0 if -1.0 in SPI_THRESHOLDS else (
    SPI_THRESHOLDS[0] if SPI_THRESHOLDS else None
)


# 2-D lat/lon (curvilinear) – identical across all decades, loaded once if the
# dataset is present. None when SPI data has not been added.
SPI_lat = None
SPI_lon = None
SPI_DEFAULT_MEAN_FILES = _spi_mean_files_raw.get(DEFAULT_SPI_AGG, {}).get(DEFAULT_SPI_THRESH, {})
def _load_latlon_from_ds(_ds):
    # Try common latitude / longitude variable names
    _lat = None
    _lon = None
    for _lat_name in ("lat", "latitude", "y"):
        if _lat_name in _ds.variables:
            _lat = _ds.variables[_lat_name][:].astype(np.float32)
            break
    for _lon_name in ("lon", "longitude", "x"):
        if _lon_name in _ds.variables:
            _lon = _ds.variables[_lon_name][:].astype(np.float32)
            break
    return _lat, _lon

if SPI_DEFAULT_MEAN_FILES:
    with nc.Dataset(SPI_DEFAULT_MEAN_FILES[min(SPI_DEFAULT_MEAN_FILES)]) as _ds:
        _lat_arr, _lon_arr = _load_latlon_from_ds(_ds)
        # Handle case where coordinate variables don't exist (returns 0-d arrays containing None)
        if _lat_arr is None or (isinstance(_lat_arr, np.ndarray) and _lat_arr.ndim == 0):
            SPI_lat = None
        else:
            SPI_lat = np.ma.filled(_lat_arr, np.nan)
        if _lon_arr is None or (isinstance(_lon_arr, np.ndarray) and _lon_arr.ndim == 0):
            SPI_lon = None
        else:
            SPI_lon = np.ma.filled(_lon_arr, np.nan)
    
    # Load curvilinear coordinates (xc/yc) from the CLM5 domain file for SPI grid
    # The SPI data uses a curvilinear grid where xc/yc are 2D arrays
    _domain_file = data_dir / "clm5_grid" / "domain.lnd.CLM5EU3_v4.nc"
    if _domain_file.exists():
        with nc.Dataset(_domain_file) as _ds:
            if "xc" in _ds.variables and "yc" in _ds.variables:
                # xc and yc are 2D arrays with shape (nj, ni) = (1544, 1592)
                SPI_lon = np.ma.filled(_ds.variables["xc"][:].astype(np.float32), np.nan)
                SPI_lat = np.ma.filled(_ds.variables["yc"][:].astype(np.float32), np.nan)
            else:
                # Fallback to synthetic coordinates if xc/yc not found
                _nlat = _ds.dimensions['nj'].size
                _nlon = _ds.dimensions['ni'].size
                SPI_lon = np.linspace(351.1, 417.0, _nlon)
                SPI_lat = np.linspace(27.0, 65.7, _nlat)
    else:
        # Domain file not found - generate synthetic coordinates as fallback
        _sample_file = next(iter(SPI_DEFAULT_MEAN_FILES.values()))
        with nc.Dataset(_sample_file) as _spi_ds:
            _nlat = _spi_ds.dimensions['lat'].size
            _nlon = _spi_ds.dimensions['lon'].size
        SPI_lon = np.linspace(351.1, 417.0, _nlon)
        SPI_lat = np.linspace(27.0, 65.7, _nlat)

# Discover non-mean stat files once (outside the nested loop) to avoid
# redundant glob scans proportional to N_agg × N_thresh.
_spi_stat_files_raw = {stat: _discover_spi_files(stat) for stat in ["dfreq", "min", "maxspell"]}

# Per-statistic, per-aggregation, per-threshold decadal data
# Structure: SPI_STAT_DATA[agg][threshold][stat] -> _LazyStatFiles
SPI_STAT_DATA: dict = {}
for agg in SPI_AGGREGATION_PERIODS:
    SPI_STAT_DATA[agg] = {}
    for thresh in SPI_THRESHOLDS:
        SPI_STAT_DATA[agg][thresh] = {}
        # Mean files
        mean_files = _spi_mean_files_raw.get(agg, {}).get(thresh, {})
        SPI_STAT_DATA[agg][thresh]["mean"] = _LazyStatFiles(mean_files, "SXI_P")
        # Other statistics (files already discovered once outside the loop)
        for stat in ["dfreq", "min", "maxspell"]:
            files_for_this = _spi_stat_files_raw[stat].get(agg, {}).get(thresh, {})
            SPI_STAT_DATA[agg][thresh][stat] = _LazyStatFiles(files_for_this, "SXI_P")

# Convenience access for current defaults (flat dict for the default aggregation and threshold)
SPI_STAT_DATA_DEFAULT: dict = {}
if DEFAULT_SPI_AGG is not None and DEFAULT_SPI_THRESH is not None:
    _default_branch = SPI_STAT_DATA.get(DEFAULT_SPI_AGG, {}).get(DEFAULT_SPI_THRESH, {})
    for _stat, _lazy in _default_branch.items():
        SPI_STAT_DATA_DEFAULT[_stat] = _lazy


# ── ICOS observations & CLM5 evaluation time series ─────────────────────────
# Per-station comparison data for the "Model evaluation" page:
#   - clm5_cells.csv        : ICOS station → nearest CLM5 grid cell metadata
#   - gpp_sm_timeseries.csv : daily ICOS RI observations (SWC_1, GPP_NT_CUT_REF)
#   - clm5_timeseries.csv   : daily CLM5 (CLM5EU3) output at the same stations
# If the files have not been downloaded yet the app degrades gracefully.

eval_dir = app_dir.parent.parent / "evaluation"

# Per-variable column suffixes and display metadata for the two sources.
EVAL_VARIABLES = {
    "sm": {
        "label": "Soil moisture",
        "abbr": "SWC",
        "unit": "%",
        "icos_suffix": "SWC_1 (%)",
        "clm5_suffix": "SM (%)",
    },
    "gpp": {
        "label": "Gross primary production (GPP)",
        "abbr": "GPP",
        "unit": "gC m⁻² d⁻¹",
        "icos_suffix": "GPP_NT_CUT_REF (gC/m2/d)",
        "clm5_suffix": "GPP (gC/m2/d)",
        # Both ICOS RI and CLM5 report GPP as positive carbon uptake, so no
        # sign adjustment is needed for the comparison.
    },
}

eval_station_meta = None
eval_icos = None
eval_clm5 = None

_eval_cells_path = eval_dir / "clm5_cells.csv"
_eval_icos_path = eval_dir / "gpp_sm_timeseries.csv"
_eval_clm5_path = eval_dir / "clm5_timeseries.csv"

if _eval_cells_path.exists():
    eval_station_meta = pd.read_csv(_eval_cells_path)

if _eval_icos_path.exists() and _eval_clm5_path.exists():
    eval_icos = pd.read_csv(_eval_icos_path, index_col=0, parse_dates=True)
    _clm5_full = pd.read_csv(_eval_clm5_path, index_col=0, parse_dates=True)
    # ICOS records start ~1999 – clip CLM5 to the overlap era so the in-memory
    # frame stays small (CLM5 itself runs from 1960).
    _clip_from = eval_icos.index.min() - pd.Timedelta(days=1)
    eval_clm5 = _clm5_full.loc[_clm5_full.index >= _clip_from]


_eval_series_cache: dict = {}


def get_eval_series(station_id: str, variable: str):
    """Return the daily ICOS and CLM5 series for a station and variable.

    The two series are aligned on the dates on which both have data (the
    overlapping period for that station). Returns ``(icos, clm5)`` as
    ``pandas.Series``; an entry is ``None`` when the station or the variable
    is not available for that source. Results are cached per
    ``(station_id, variable)``.
    """
    key = (station_id, variable)
    if key in _eval_series_cache:
        return _eval_series_cache[key]
    if eval_icos is None or eval_clm5 is None or variable not in EVAL_VARIABLES:
        _eval_series_cache[key] = (None, None)
        return None, None
    spec = EVAL_VARIABLES[variable]
    icos_col = f"{station_id}_{spec['icos_suffix']}"
    clm5_col = f"{station_id}_{spec['clm5_suffix']}"
    icos = (
        eval_icos[icos_col].dropna()
        if icos_col in eval_icos.columns
        else None
    )
    clm5 = (
        eval_clm5[clm5_col].dropna()
        if clm5_col in eval_clm5.columns
        else None
    )
    if icos is not None and clm5 is not None:
        joined = pd.concat({"icos": icos, "clm5": clm5}, axis=1).dropna()
        icos, clm5 = joined["icos"], joined["clm5"]
    _eval_series_cache[key] = (icos, clm5)
    return icos, clm5


def _build_eval_map_html(meta_df: pd.DataFrame) -> str:
    """Generate a self-initialising Leaflet.js map of the ICOS evaluation stations.

    Mirrors :func:`_build_gauge_map_html` (EPSG:3035 LAEA projection, Natural
    Earth land/lakes GeoJSON background, marker pane above the basemap). Two
    differences: only European stations are shown (the view is fixed to
    Europe, non-European stations stay selectable via the dropdown), and
    marker clicks sync the ``#eval_station`` dropdown (two-way binding).
    """
    european = meta_df[
        (meta_df["latitude"] >= 34)
        & (meta_df["latitude"] <= 72)
        & (meta_df["longitude"] >= -15)
        & (meta_df["longitude"] <= 45)
    ]
    
    markers = [
        {
            "id": str(row["station_id"]),
            "lat": float(row["latitude"]),
            "lon": float(row["longitude"]),
            "station": str(row["station_name"]),
        }
        for _, row in european.iterrows()
    ]
    markers_json = json.dumps(markers)

    return f"""
<div id="eval-map"
     style="height:520px; width:100%; max-width: 600px; margin: 0 auto; border-radius:6px; overflow:hidden;">
</div>
<style>
  .eval-tooltip {{
    background: #2a2a2a !important;
    border: 1px solid #555 !important;
    color: #eee !important;
    font-family: Inter, system-ui, sans-serif;
    font-size: 12px;
    padding: 4px 8px;
    border-radius: 4px;
  }}
  .eval-tooltip.leaflet-tooltip-top::before   {{ border-top-color:   #555 !important; }}
  .eval-tooltip.leaflet-tooltip-left::before  {{ border-left-color:  #555 !important; }}
  .leaflet-control-attribution {{ background: rgba(255,255,255,0.7) !important; color: #333 !important; font-size: 10px; }}
</style>
<script>
(function () {{
  var data   = {markers_json};
  var active = null;

  var defaultStyle = {{
    radius: 6, fillColor: '#375a7f', color: '#46b8da',
    weight: 1.5, opacity: 0.9, fillOpacity: 0.75
  }};
  var hoverStyle = {{
    radius: 8, fillColor: '#46b8da', color: '#ffffff',
    weight: 2, opacity: 1, fillOpacity: 0.9
  }};
  var activeStyle = {{
    radius: 9, fillColor: '#f0ad4e', color: '#ffffff',
    weight: 2, opacity: 1, fillOpacity: 1
  }};

  var map;

  function initMap() {{
    var laea = new L.Proj.CRS(
      'EPSG:3035',
      '+proj=laea +lat_0=52 +lon_0=10 +x_0=4321000 +y_0=3210000 +ellps=GRS80 +units=m +no_defs',
      {{ resolutions: [8000, 4000, 2000, 1000, 500, 250, 125, 62.5, 31.25] }}
    );

    map = L.map('eval-map', {{ crs: laea, maxZoom: 8 }});

    // Calculate bounds from all markers and fit the map to show all of them
    if (data.length > 0) {{
      var bounds = L.latLngBounds(data.map(function(d) {{ return [d.lat, d.lon]; }}));
      map.fitBounds(bounds, {{ padding: [50, 50] }});
    }} else {{
      map.setView([54.0, 15.0], 1);
    }}

    // Dropdown change -> highlight, pan, and bring to front
    $(document).on('change', '#eval_station', function() {{
      var stationId = $(this).val();
      if (stationId) {{
        map.eachLayer(function (layer) {{
          if (layer.stationId === stationId) {{
            if (active && active !== layer) active.setStyle(defaultStyle);
            layer.setStyle(activeStyle);
            layer.bringToFront();
            active = layer;
            map.panTo([layer.getLatLng()]);
          }}
        }});
      }}
    }});

    // Bring the initially selected marker to front after map initialization
    $(document).ready(function() {{
      setTimeout(function() {{
        var stationId = $('#eval_station').val();
        if (stationId) {{
          map.eachLayer(function (layer) {{
            if (layer.stationId === stationId) {{
              layer.setStyle(activeStyle);
              layer.bringToFront();
              active = layer;
            }}
          }});
        }}
      }}, 200); // Allow map to fully render first
    }});

    // Ocean colour via CSS (no tile layer needed)
    document.getElementById('eval-map').style.background = '#a6cee3';

    // Dedicated pane for the station markers so they always render above
    // the GeoJSON land layer (same z-index scheme as the gauge map).
    map.createPane('evalPane');
    map.getPane('evalPane').style.zIndex = 620;
    map.getPane('evalPane').style.pointerEvents = 'auto';

    // Land masses: Natural Earth 50 m (Leaflet reprojects to the map CRS)
    fetch('https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson')
      .then(function (r) {{ return r.json(); }})
      .then(function (geo) {{
        L.geoJSON(geo, {{
          style: {{
            fillColor: '#636363',
            fillOpacity: 0.9,
            color:      '#999',
            weight:     0.5
          }}
        }}).addTo(map);
      }})
      .catch(function (err) {{
        console.warn('Basemap land layer not available:', err.message);
        var europeOutline = [[71, -25], [71, 40], [35, 40], [35, -25], [71, -25]];
        L.polygon(europeOutline, {{
          fillColor: '#636363',
          fillOpacity: 0.2,
          color: '#999',
          weight: 1
        }}).addTo(map).bindTooltip('Land layer unavailable', {{permanent: true, direction: 'center'}});
      }});

    // Major lakes (50 m) – painted in ocean colour so they read as water.
    fetch('https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_lakes.geojson')
      .then(function (r) {{ return r.json(); }})
      .then(function (geo) {{
        L.geoJSON(geo, {{
          style: {{
            fillColor: '#a6cee3',
            fillOpacity: 1.0,
            color:      '#888',
            weight:     0.4
          }}
        }}).addTo(map);
      }})
      .catch(function (err) {{
        console.warn('Basemap lakes layer not available:', err.message);
      }});

    data.forEach(function (g) {{
      var m = L.circleMarker([g.lat, g.lon],
                             Object.assign({{pane: 'evalPane'}}, defaultStyle)).addTo(map);

      // Store the station ID on the marker for easy lookup
      m.stationId = g.id;

      m.bindTooltip(
        '<b>' + g.station + '</b><br><i>' + g.id + '</i>',
        {{ sticky: true, className: 'eval-tooltip' }}
      );

      m.on('mouseover', function () {{
        if (m !== active) m.setStyle(hoverStyle);
      }});
      m.on('mouseout', function () {{
        if (m !== active) m.setStyle(defaultStyle);
      }});
      m.on('click', function () {{
        if (active && active !== m) active.setStyle(defaultStyle);
        m.setStyle(activeStyle);
        m.bringToFront();
        active = m;
        if (typeof Shiny !== 'undefined') {{
          Shiny.setInputValue('eval_station', g.id, {{ priority: 'event' }});
        }}
        // Keep the dropdown in sync with the clicked marker.
        $('#eval_station').val(g.id).trigger('change');
      }});
    }});
  }}

  // Initialise only once the container is visible (Shiny hides inactive tabs).
  var el = document.getElementById('eval-map');
  if (el.offsetWidth > 0 && el.offsetHeight > 0) {{
    initMap();
    // Bring the initially selected marker to front after map initialization
    setTimeout(function() {{
      var selectedId = $('#eval_station').val();
      if (selectedId) {{
        data.forEach(function(g) {{
          if (g.id === selectedId) {{
            // Find the marker with this ID and bring to front
            map.eachLayer(function(layer) {{
              if (layer.stationId === selectedId && layer.bringToFront) {{
                layer.setStyle(activeStyle); // Ensure active style
                layer.bringToFront();
              }}
            }});
          }}
        }});
      }}
    }}, 100); // Small delay to ensure map is fully rendered
  }} else {{
    var ro = new ResizeObserver(function (entries) {{
      if (entries[0].contentRect.width > 0 && entries[0].contentRect.height > 0) {{
        ro.disconnect();
        initMap();
      }}
    }});
    ro.observe(el);
  }}
}})();
</script>
"""


# Built once at import time – reused for the lifetime of the Shiny process
eval_map_html = (
    _build_eval_map_html(eval_station_meta)
    if eval_station_meta is not None and len(eval_station_meta) > 0
    else ""
)

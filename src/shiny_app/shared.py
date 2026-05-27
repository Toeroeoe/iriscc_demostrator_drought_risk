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

df = pd.read_csv(data_dir / "penguins.csv")

# Load decadal data files
decadal_means_clm5_files = sorted(
    glob.glob(str(data_dir / "decadal_SMI/CLM5/decadal_stats_*timmean.nc_classic.nc"))
)
decadal_means_mhm_files = sorted(
    glob.glob(str(data_dir / "decadal_SMI/mHM/decadal_stats_*timmean.nc.nc_classic.nc"))
)

if len(decadal_means_clm5_files) == 0 or len(decadal_means_mhm_files) == 0:
    raise FileNotFoundError("No decadal means files found in the data directory.")
elif len(decadal_means_clm5_files) != len(decadal_means_mhm_files):
    raise ValueError("The number of CLM5 and mHM decadal means files do not match.")

# Extract decade years from filenames
decade_years = []
for file in decadal_means_clm5_files:
    match = re.search(r"(\d{4})_(\d{4})", file)
    if match:
        decade_years.append(int(match.group(1)))

# Load complete datasets with MFDataset
clm5_ds = nc.MFDataset(decadal_means_clm5_files)
mhm_ds = nc.MFDataset(decadal_means_mhm_files)

# Load full arrays (time, lat, lon)
CLM5_smi_full = clm5_ds.variables["SMI"][:]
mHM_smi_full = mhm_ds.variables["SMI"][:]

# Extract coordinates (try different variable names)
if "lon" in clm5_ds.variables:
    lon = clm5_ds.variables["lon"][:]
    lat = clm5_ds.variables["lat"][:]
elif "rlon" in clm5_ds.variables:
    lon = clm5_ds.variables["rlon"][:]
    lat = clm5_ds.variables["rlat"][:]
else:
    coord_vars = list(clm5_ds.variables.keys())
    raise ValueError(
        f"Could not find lat/lon or rlon/rlat in dataset. Available: {coord_vars}"
    )

# Create mapping from decade year to array index
decade_to_index = {year: idx for idx, year in enumerate(decade_years)}

# ── Streamflow / discharge data ───────────────────────────────────────────────

_streamflow_dir = data_dir / "streamflow"

# Gauge metadata (all stations in the CSV)
_gauge_meta_raw = pd.read_csv(_streamflow_dir / "grdc_iriscc_subset_lite.csv")

# Open discharge NetCDF – kept open for the app lifetime; variables load lazily
_discharge_ds = nc.Dataset(_streamflow_dir / "discharge.nc")

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
_base_dt = datetime(1950, 1, 1)
_time_hours = _discharge_ds.variables["time"][:]
discharge_time = pd.DatetimeIndex(
    [_base_dt + timedelta(hours=int(h)) for h in _time_hours]
)


def get_gauge_discharge(gauge_id: str):
    """Return (qobs, qsim) float64 numpy arrays for a gauge_id.

    gauge_id must be a zero-padded 10-digit string (e.g. '0006112080').
    Masked / fill values are replaced with NaN.
    Returns (None, None) when the gauge is absent from the dataset.
    """
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
     style="height:900px; width:100%; border-radius:6px; overflow:hidden;">
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

  function initMap() {{
    // EPSG:3035 LAEA Europe — true equal-area projection (EU standard).
    // Resolutions are in metres/pixel; the array index is the Leaflet zoom level.
    var laea = new L.Proj.CRS(
      'EPSG:3035',
      '+proj=laea +lat_0=52 +lon_0=10 +x_0=4321000 +y_0=3210000 +ellps=GRS80 +units=m +no_defs',
      {{ resolutions: [8000, 4000, 2000, 1000, 500, 250, 125, 62.5, 31.25] }}
    );

    var map = L.map('gauge-map', {{ crs: laea, maxZoom: 8 }}).setView([54.0, 15.0], 1);

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
      }});

    data.forEach(function (g) {{
      var m = L.circleMarker([g.lat, g.lon],
                             Object.assign({{pane: 'gaugePane'}}, defaultStyle)).addTo(map);

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
        active = m;
        if (typeof Shiny !== 'undefined') {{
          Shiny.setInputValue('selected_gauge', g.id, {{ priority: 'event' }});
        }}
      }});
    }});
  }}

  // Initialise only once the container is visible (Shiny hides inactive tabs).
  var el = document.getElementById('gauge-map');
  if (el.offsetWidth > 0 && el.offsetHeight > 0) {{
    initMap();
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

_spi_files = sorted(glob.glob(str(data_dir / "decadal_SXI_P/SXI_P_*_timmean.nc")))

if len(_spi_files) == 0:
    raise FileNotFoundError("No SXI_P timmean files found in data/decadal_SXI_P/.")

# Decade start years extracted from filenames (e.g. SXI_P_92D_1960_1969_timmean.nc)
_spi_decade_years = []
for _f in _spi_files:
    _m = re.search(r"(\d{4})_(\d{4})", _f)
    if _m:
        _spi_decade_years.append(int(_m.group(1)))

# 2-D lat/lon (curvilinear) – identical across all files, load once
with nc.Dataset(_spi_files[0]) as _ds:
    SPI_lat = np.ma.filled(_ds.variables["lat"][:].astype(float), np.nan)
    SPI_lon = np.ma.filled(_ds.variables["lon"][:].astype(float), np.nan)

# Stack all decades: shape (n_decades, lat, lon)
_spi_arrays = []
for _f in _spi_files:
    with nc.Dataset(_f) as _ds:
        _spi_arrays.append(
            np.ma.filled(_ds.variables["SXI_P"][0].astype(float), np.nan)
        )
SPI_full = np.array(_spi_arrays)  # (n_decades, 1544, 1592)

spi_decade_to_index = {year: idx for idx, year in enumerate(_spi_decade_years)}

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


class _LazyDecadeStack:
    """Indexable, lazily-loaded view over a NetCDF variable's decade axis.

    ``stack[i]`` reads and returns only decade ``i`` (as float32) rather than
    pulling every decade into memory at import time. Slices are cached, so
    repeated views of the same decade are free. Only the ndarray operations the
    app relies on are implemented: integer indexing and ``len()``.
    """

    def __init__(self, variable, n_decades: int):
        self._var = variable
        self._n = n_decades
        self._cache: dict = {}

    def __len__(self) -> int:
        return self._n

    def __getitem__(self, index: int):
        if index not in self._cache:
            # float32 keeps memory (and masked-array promotion) in check;
            # netCDF4 reads only the requested decade slice from disk.
            self._cache[index] = self._var[index].astype(np.float32)
        return self._cache[index]


class _LazySpiStat:
    """Lazy, dict-like access to one decadal SPI statistic.

    Maps ``decade_start_year -> 2-D float32 array`` but only reads a decade's
    file the first time that year is requested. Implements just the mapping
    operations the app uses: truthiness, ``in``, ``keys()`` and indexing.
    """

    def __init__(self, files: dict):
        self._files = dict(files)
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
                    ds.variables["SXI_P"][0].astype(np.float32), np.nan
                )
        return self._cache[year]

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

# Lazily-loaded per-decade views (float32). The app only ever displays one
# decade at a time, so reading every decade up front just wastes memory and
# start-up time.
CLM5_smi_full = _LazyDecadeStack(
    clm5_ds.variables["SMI"], len(decadal_means_clm5_files)
)
mHM_smi_full = _LazyDecadeStack(
    mhm_ds.variables["SMI"], len(decadal_means_mhm_files)
)

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
# Loaded only when present. When the discharge dataset has not been synced yet
# the app degrades gracefully: an empty gauge map and no time series, instead
# of failing to import.

_streamflow_dir = data_dir / "streamflow"
_discharge_path = _streamflow_dir / "discharge.nc"
_gauge_csv_path = _streamflow_dir / "grdc_iriscc_subset_lite.csv"

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
# All SPI data is loaded lazily (see _LazySpiStat): only the file paths are
# discovered at import time, and each decade's grid is read on first access.
# If the SPI dataset has not been added yet, the app degrades gracefully — the
# meteorological maps show an "not available" message instead of crashing.

_spi_dir = data_dir / "decadal_SPI"

# Decade-mean files, e.g. SXI_P_92D_1960_1969_timmean.nc → {1960: path, ...}
_spi_mean_files: dict = {}
for _f in sorted(glob.glob(str(_spi_dir / "SXI_P_*_timmean.nc"))):
    _m = re.search(r"(\d{4})_(\d{4})", _f)
    if _m:
        _spi_mean_files[int(_m.group(1))] = _f


def _discover_spi_stat_files(suffix: str) -> dict:
    """Map decade start year → file path for a decadal SPI statistic.

    Files are produced by data/processing/decadal_statistics.sh, one per decade:
      SXI_P_92D_<year>_dfreq.nc     fraction of time in drought (0..1)
      SXI_P_92D_<year>_min.nc       most negative SPI reached (peak severity)
      SXI_P_92D_<year>_maxspell.nc  longest consecutive dry spell (days)
    """
    out: dict = {}
    for _f in sorted(glob.glob(str(_spi_dir / f"SXI_P_92D_*_{suffix}.nc"))):
        _m = re.search(rf"SXI_P_92D_(\d{{4}})_{suffix}\.nc$", _f)
        if _m:
            out[int(_m.group(1))] = _f
    return out


# 2-D lat/lon (curvilinear) – identical across all decades, loaded once if the
# dataset is present. None when SPI data has not been added.
SPI_lat = None
SPI_lon = None
if _spi_mean_files:
    with nc.Dataset(_spi_mean_files[min(_spi_mean_files)]) as _ds:
        SPI_lat = np.ma.filled(_ds.variables["lat"][:].astype(np.float32), np.nan)
        SPI_lon = np.ma.filled(_ds.variables["lon"][:].astype(np.float32), np.nan)

# Per-statistic decadal data keyed by statistic name; each value is a lazy,
# dict-like mapping of decade start year → 2-D field, read on first access.
SPI_STAT_DATA: dict = {
    "mean": _LazySpiStat(_spi_mean_files),
    "dfreq": _LazySpiStat(_discover_spi_stat_files("dfreq")),
    "min": _LazySpiStat(_discover_spi_stat_files("min")),
    "maxspell": _LazySpiStat(_discover_spi_stat_files("maxspell")),
}

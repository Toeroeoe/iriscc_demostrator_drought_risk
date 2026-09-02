"""
Offline tests for clm5_download.py.

No access to ICOS or to the full CLM5 model files is needed: small
synthetic curvilinear domain files and model files are written to a
temporary directory with netCDF4, and the pipeline functions (station
matching, per-file extraction, assembly, unit conversion, resampling,
CSV writing) are tested directly. Two tests additionally run main()
end-to-end with a monkeypatched command line.
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import netCDF4  # noqa: E402

import clm5_download as clm5  # noqa: E402

FILL = 1e36


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_grid_arrays():
    """A small 4x4 curvilinear test grid (1 degree spacing, Europe-like)."""
    lats = np.array([[48.0] * 4, [47.0] * 4, [46.0] * 4, [45.0] * 4])
    lons = np.array([[7.0, 8.0, 9.0, 10.0]] * 4)
    return lats, lons


def write_domain_file(path, lats, lons, mask=None):
    ds = netCDF4.Dataset(str(path), 'w')
    ds.createDimension('y', lats.shape[0])
    ds.createDimension('x', lats.shape[1])
    yc = ds.createVariable('yc', 'f8', ('y', 'x'))
    yc[:] = lats
    xc = ds.createVariable('xc', 'f8', ('y', 'x'))
    xc[:] = lons
    if mask is not None:
        m = ds.createVariable('mask', 'i4', ('y', 'x'))
        m[:] = mask
    ds.close()


def write_model_file(path, year, n_days=5, n_soil=3, n_lat=4, n_lon=4,
                     fill_cells=()):
    """
    Write a synthetic annual model file.

    H2OSOI values encode the soil layer index plus 0.1 per day (so the
    selected soil layer can be verified); GPP values are
    2.0 + 0.001*day in gC/m^2/s. `fill_cells` is an iterable of
    (time, row, col) tuples where GPP is set to the fill value.
    """
    ds = netCDF4.Dataset(str(path), 'w')
    for name, size in (('time', n_days), ('levsoi', n_soil),
                       ('lat', n_lat), ('lon', n_lon)):
        ds.createDimension(name, size)
    t = ds.createVariable('time', 'f8', ('time',))
    t.units = f'days since {year}-01-01 00:00:00'
    t.calendar = 'noleap'
    t[:] = np.arange(n_days)
    h2o = ds.createVariable('H2OSOI', 'f4',
                            ('time', 'levsoi', 'lat', 'lon'), fill_value=FILL)
    h2o.units = 'mm3/mm3'
    gpp = ds.createVariable('GPP', 'f4', ('time', 'lat', 'lon'),
                            fill_value=FILL)
    gpp.units = 'gC/m^2/s'
    for ti in range(n_days):
        for layer in range(n_soil):
            h2o[ti, layer, :, :] = layer + 0.1 * ti
        gpp[ti, :, :] = 2.0 + 0.001 * ti
    for (ti, r, c) in fill_cells:
        gpp[ti, r, c] = FILL
    ds.close()


def write_stations_csv(path, rows):
    df = pd.DataFrame(rows, columns=['station_id', 'station_name',
                                     'latitude', 'longitude'])
    df.to_csv(path, index=False)


def write_config(path, domain_path, model_dir):
    text = (
        "clm5:\n"
        f"  path: \"{model_dir}\"\n"
        "  files: \"model_*.nc\"\n"
        "  variables:\n"
        "    SM: H2OSOI\n"
        "    GPP: GPP\n"
        "  soil_layer_i: 1\n"
        "grid:\n"
        f"  path: \"{os.path.dirname(domain_path)}\"\n"
        f"  file: \"{os.path.basename(domain_path)}\"\n"
        "  variables:\n"
        "    lat: yc\n"
        "    lon: xc\n"
    )
    Path(path).write_text(text)


def setup_scenario(tmp_path):
    """Domain + two model years + stations CSV + config; returns paths."""
    lats, lons = make_grid_arrays()
    domain_dir = tmp_path / 'domain'
    domain_dir.mkdir()
    domain = domain_dir / 'domain.nc'
    write_domain_file(domain, lats, lons, mask=np.ones((4, 4), dtype=int))

    model_dir = tmp_path / 'model'
    model_dir.mkdir()
    write_model_file(model_dir / 'model_1960-01-01-00000.nc', 1960)
    write_model_file(model_dir / 'model_1961-01-01-00000.nc', 1961)

    cfg = tmp_path / 'config.yaml'
    write_config(cfg, domain, model_dir)

    stations = tmp_path / 'stations.csv'
    write_stations_csv(stations, [
        ['ST1', 'Test one', 48.1, 7.2],   # -> cell (0, 0) at (48.0, 7.0)
        ['ST2', 'Test two', 45.6, 9.4],   # -> cell (2, 2) at (46.0, 9.0)
    ])
    return cfg, stations


# ---------------------------------------------------------------------------
# resolve_variables / parse_unit_overrides
# ---------------------------------------------------------------------------

def test_resolve_variables_aliases_and_dedup():
    cfg_vars = {'SM': 'H2OSOI', 'GPP': 'GPP'}
    assert clm5.resolve_variables(['SM'], cfg_vars) == [('SM', 'H2OSOI')]
    assert clm5.resolve_variables(['gpp'], cfg_vars) == [('GPP', 'GPP')]
    # Raw NetCDF names are accepted and map back to the yaml label
    assert clm5.resolve_variables(['H2OSOI'], cfg_vars) == [('SM', 'H2OSOI')]
    # Duplicates dropped, request order kept
    assert clm5.resolve_variables(
        ['GPP', 'sm', 'gpp'], cfg_vars
    ) == [('GPP', 'GPP'), ('SM', 'H2OSOI')]


def test_resolve_variables_unknown_raises():
    with pytest.raises(ValueError, match='Unknown variable'):
        clm5.resolve_variables(['NBP'], {'SM': 'H2OSOI'})


def test_parse_unit_overrides():
    assert clm5.parse_unit_overrides(['SM:m3/m3', 'GPP:gC/m2/s']) == {
        'SM': 'm3/m3', 'GPP': 'gC/m2/s'
    }
    assert clm5.parse_unit_overrides(None) == {}
    for bad in ('no-colon', 'GPP:', ':gC/m2/d'):
        with pytest.raises(ValueError):
            clm5.parse_unit_overrides([bad])


# ---------------------------------------------------------------------------
# haversine_km / find_nearest_cell
# ---------------------------------------------------------------------------

def test_haversine_km():
    assert clm5.haversine_km(48.0, 7.0, 48.0, 7.0) == 0.0
    # One degree of latitude is about 111.2 km
    assert clm5.haversine_km(48.0, 7.0, 49.0, 7.0) == pytest.approx(
        111.2, rel=1e-3)


def test_find_nearest_cell():
    lats, lons = make_grid_arrays()
    # (47.6, 7.4) is closest to cell (0, 0) at (48.0, 7.0)
    match = clm5.find_nearest_cell(47.6, 7.4, lats, lons)
    assert (match['row'], match['col']) == (0, 0)
    assert match['cell_lat'] == 48.0
    assert match['cell_lon'] == 7.0
    assert 40.0 < match['distance_km'] < 70.0


def test_find_nearest_cell_land_mask_fallback():
    lats, lons = make_grid_arrays()
    mask = np.ones((4, 4), dtype=int)
    mask[:, 0] = 0  # westernmost column is ocean
    # The closest cell (0, 0) is ocean -> falls back to (0, 1) at (48.0, 8.0)
    match = clm5.find_nearest_cell(47.6, 7.4, lats, lons, land_mask=mask)
    assert (match['row'], match['col']) == (0, 1)


def test_find_nearest_cell_no_land_returns_none():
    lats, lons = make_grid_arrays()
    mask = np.zeros((4, 4), dtype=int)
    assert clm5.find_nearest_cell(
        47.0, 8.0, lats, lons, land_mask=mask) is None


# ---------------------------------------------------------------------------
# decode_time
# ---------------------------------------------------------------------------

class FakeTimeVar:
    def __init__(self, units='days since 1960-01-01 00:00:00',
                 calendar='noleap'):
        self.units = units
        self.calendar = calendar


def test_decode_time_noleap():
    idx = clm5.decode_time(np.array([0.0, 1.0, 364.0]), FakeTimeVar())
    assert list(idx) == [pd.Timestamp('1960-01-01'),
                         pd.Timestamp('1960-01-02'),
                         pd.Timestamp('1960-12-31')]


def test_decode_time_restart_epoch_units():
    # Restart epochs reset the raw values to 0.0 with different units;
    # each file must be decoded with its own units.
    idx = clm5.decode_time(
        np.array([0.0, 2.0]), FakeTimeVar('days since 2023-06-01 00:00:00'))
    assert list(idx) == [pd.Timestamp('2023-06-01'),
                         pd.Timestamp('2023-06-03')]


# ---------------------------------------------------------------------------
# process_clm5_file / assemble_timeseries
# ---------------------------------------------------------------------------

def test_process_clm5_file_selects_soil_layer(tmp_path):
    path = tmp_path / 'model_1960-01-01-00000.nc'
    write_model_file(path, 1960, n_days=5)
    cells = {'ST1': (0, 0), 'ST2': (3, 2)}
    specs = [('SM', 'H2OSOI'), ('GPP', 'GPP')]
    time_index, units, per_label = clm5.process_clm5_file(
        str(path), cells, specs, soil_layer=1)

    assert list(time_index) == [pd.Timestamp(f'1960-01-0{i}') for i in range(1, 6)]
    assert units == {'SM': 'mm3/mm3', 'GPP': 'gC/m^2/s'}

    # SM: soil layer 1 -> value = 1 + 0.1*day
    np.testing.assert_allclose(
        per_label['SM']['ST1'], 1.0 + 0.1 * np.arange(5), rtol=1e-6)
    # GPP: 2.0 + 0.001*day (no fill cells hit by the stations here)
    np.testing.assert_allclose(
        per_label['GPP']['ST2'], 2.0 + 0.001 * np.arange(5), rtol=1e-6)


def test_process_clm5_file_fill_value_becomes_nan(tmp_path):
    path = tmp_path / 'model_1960-01-01-00000.nc'
    write_model_file(path, 1960, n_days=5, fill_cells=[(0, 3, 2)])
    _, _, per_label = clm5.process_clm5_file(
        str(path), {'ST2': (3, 2)}, [('GPP', 'GPP')], soil_layer=1)
    gpp = per_label['GPP']['ST2']
    assert np.isnan(gpp[0])
    assert not np.any(np.isnan(gpp[1:]))


def test_process_clm5_file_soil_layer_out_of_range(tmp_path):
    path = tmp_path / 'model_1960-01-01-00000.nc'
    write_model_file(path, 1960, n_days=2, n_soil=3)
    with pytest.raises(ValueError, match='soil_layer_i'):
        clm5.process_clm5_file(
            str(path), {'ST1': (0, 0)}, [('SM', 'H2OSOI')], soil_layer=3)


def test_assemble_timeseries_dedupes_overlapping_dates(tmp_path):
    path = tmp_path / 'model_1960-01-01-00000.nc'
    write_model_file(path, 1960, n_days=5)
    result = clm5.process_clm5_file(
        str(path), {'ST1': (0, 0)}, [('GPP', 'GPP')], soil_layer=1)
    # Simulate a restart file covering the same dates
    df, units = clm5.assemble_timeseries([result, result])
    assert len(df) == 5
    assert list(df.columns) == [('ST1', 'GPP')]
    assert units == {'GPP': 'gC/m^2/s'}


# ---------------------------------------------------------------------------
# resample_timeseries / build_output_columns
# ---------------------------------------------------------------------------

def make_df():
    idx = pd.DatetimeIndex(
        [pd.Timestamp('1960-01-01'), pd.Timestamp('1960-01-02'),
         pd.Timestamp('1960-02-01')])
    df = pd.DataFrame({
        ('ST1', 'GPP'): [1.0, 3.0, 5.0],
        ('ST1', 'SM'): [10.0, 20.0, 30.0],
    }, index=idx)
    df.index.name = 'TIMESTAMP'
    return df


def test_resample_single_agg_keeps_two_level_columns():
    out = clm5.resample_timeseries(make_df(), '1MS', ['mean'])
    assert out.columns.nlevels == 2
    assert out.loc['1960-01-01', ('ST1', 'GPP')] == pytest.approx(2.0)
    assert out.loc['1960-02-01', ('ST1', 'GPP')] == pytest.approx(5.0)


def test_resample_multi_agg_adds_agg_level():
    out = clm5.resample_timeseries(make_df(), '1MS', ['mean', 'std'])
    assert out.columns.nlevels == 3
    assert out.loc['1960-01-01', ('ST1', 'GPP', 'mean')] == pytest.approx(2.0)


def test_build_output_columns_names_and_units():
    df = make_df()
    names = clm5.build_output_columns(df, {'GPP': 'gC/m2/d', 'SM': '%'})
    assert names == ['ST1_GPP (gC/m2/d)', 'ST1_SM (%)']


# ---------------------------------------------------------------------------
# end-to-end via main()
# ---------------------------------------------------------------------------

def test_main_end_to_end(tmp_path, monkeypatch):
    cfg, stations = setup_scenario(tmp_path)
    output = tmp_path / 'out.csv'
    cells_report = tmp_path / 'cells.csv'
    monkeypatch.setattr(sys, 'argv', [
        'clm5_download.py',
        '--config', str(cfg),
        '--input-csv', str(stations),
        '--output', str(output),
        '--cell-report', str(cells_report),
        '--workers', '1',
    ])
    clm5.main()

    df = pd.read_csv(output)
    assert df.columns[0] == 'TIMESTAMP'
    assert list(df.columns[1:]) == [
        'ST1_GPP (gC/m2/d)', 'ST1_SM (%)',
        'ST2_GPP (gC/m2/d)', 'ST2_SM (%)'
    ]
    assert len(df) == 10  # two model years x 5 days
    assert df['TIMESTAMP'].iloc[0] == '1960-01-01'
    assert df['TIMESTAMP'].iloc[-1] == '1961-01-05'

    # GPP: (2.0 + 0.001*t) gC/m^2/s * 86400 s/d
    gpp_st1 = df['ST1_GPP (gC/m2/d)'].iloc[:5].to_numpy()
    np.testing.assert_allclose(
        gpp_st1, (2.0 + 0.001 * np.arange(5)) * 86400.0, rtol=1e-5)
    # SM: soil layer 1 (1.0 + 0.1*t) mm3/mm3 * 100 -> %
    sm_st2 = df['ST2_SM (%)'].iloc[5:].to_numpy()
    np.testing.assert_allclose(
        sm_st2, (1.0 + 0.1 * np.arange(5)) * 100.0, rtol=1e-5)

    cells_df = pd.read_csv(cells_report)
    assert sorted(cells_df['station_id']) == ['ST1', 'ST2']
    st1 = cells_df.loc[cells_df['station_id'] == 'ST1'].iloc[0]
    assert (st1['cell_row'], st1['cell_col']) == (0, 0)
    assert st1['distance_km'] < 20.0
    st2 = cells_df.loc[cells_df['station_id'] == 'ST2'].iloc[0]
    # (45.6, 9.4) is closest to cell (2, 2) at (46.0, 9.0)
    assert (st2['cell_row'], st2['cell_col']) == (2, 2)


def test_main_no_unit_conversion_limit_and_variables(tmp_path, monkeypatch):
    cfg, stations = setup_scenario(tmp_path)
    output = tmp_path / 'out.csv'
    monkeypatch.setattr(sys, 'argv', [
        'clm5_download.py',
        '--config', str(cfg),
        '--input-csv', str(stations),
        '--output', str(output),
        '--cell-report', '',
        '--variables', 'GPP',
        '--no-unit-conversion',
        '--limit', '1',
    ])
    clm5.main()

    df = pd.read_csv(output)
    assert list(df.columns) == [
        'TIMESTAMP', 'ST1_GPP (gC/m^2/s)', 'ST2_GPP (gC/m^2/s)'
    ]
    assert len(df) == 5  # only the first model year
    gpp_st1 = df['ST1_GPP (gC/m^2/s)'].to_numpy()
    np.testing.assert_allclose(gpp_st1, 2.0 + 0.001 * np.arange(5), rtol=1e-6)

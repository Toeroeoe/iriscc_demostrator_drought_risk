"""
Offline tests for download.py.

The ICOS Dobj class is replaced with a FakeDobj backed by an in-memory
registry, so no network access or ICOS credentials are needed.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import download as dsm  # noqa: E402
except ImportError:
    # download.py needs the icoscp >= 0.2 API ('icoscp.dobj'), which is
    # only available on Python >= 3.10. Skip the module on older Pythons.
    dsm = None
    pytestmark = pytest.mark.skip(
        reason='requires icoscp >= 0.2 (Python >= 3.10)')


TS = pd.date_range('2020-01-01', periods=8, freq='h')


def make_df(**columns):
    """Build a data-object frame with a TIMESTAMP column plus variables."""
    df = pd.DataFrame({'TIMESTAMP': TS.copy()})
    for name, values in columns.items():
        df[name] = values
    return df


class FakeDobj:
    """Stands in for icoscp.dobj.Dobj; entries keyed by URI."""

    registry = {}

    def __init__(self, uri):
        self.uri = uri
        if uri not in self.registry:
            raise KeyError(f"Unknown data object URI: {uri}")
        entry = self.registry[uri]
        self.colNames = list(entry['columns'])
        self._data = entry['data']
        self._units = entry.get('units', {})

    @property
    def variables(self):
        rows = [
            {
                'name': col,
                'unit': self._units.get(col, ''),
                'type': 'float',
                'format': '',
            }
            for col in self.colNames
            if col != 'TIMESTAMP'
        ]
        return pd.DataFrame(rows, columns=['name', 'unit', 'type', 'format'])

    def get(self, columns=None):
        df = self._data
        if columns is not None:
            df = df[[c for c in columns if c in df.columns]]
        return df.copy()


@pytest.fixture
def fake_dobj(monkeypatch):
    def _install(entries):
        FakeDobj.registry = dict(entries)
        monkeypatch.setattr(dsm, 'Dobj', lambda uri: FakeDobj(uri))

    return _install


def make_station(dobj_uris, station_id='ST1', station_name='Station One'):
    uris = '; '.join(dobj_uris)
    return {
        'station_uri': f'https://example/station/{station_id}',
        'station_id': station_id,
        'station_name': station_name,
        'latitude': '60.0',
        'longitude': '25.0',
        'soil_moisture_variables': 'SWC_1;SWC_2',
        'num_data_objects': str(len(dobj_uris)),
        'data_object_uris': uris,
    }


# ---------------------------------------------------------------------------
# match_variables
# ---------------------------------------------------------------------------

def test_match_variables_exact():
    labels = ['TIMESTAMP', 'SWC_1', 'SWC_10', 'GPP']
    assert dsm.match_variables(['SWC_1'], labels) == ['SWC_1']
    assert dsm.match_variables(['GPP'], labels) == ['GPP']
    assert dsm.match_variables(['NBP'], labels) == []


def test_match_variables_prefix():
    labels = ['TIMESTAMP', 'SWC_1', 'SWC_2', 'SWC_10', 'GPP']
    assert dsm.match_variables(['SWC'], labels) == ['SWC_1', 'SWC_2', 'SWC_10']
    # A prefix must not match a longer bare name without the separator
    assert dsm.match_variables(['SWC_1'], labels) == ['SWC_1']


def test_match_variables_bracketed_label():
    labels = ['TIMESTAMP', 'SWC_1 [m3/m3]', 'GPP [g C/m2/s]']
    assert dsm.match_variables(['SWC_1'], labels) == ['SWC_1 [m3/m3]']
    assert dsm.match_variables(['SWC'], labels) == ['SWC_1 [m3/m3]']


# ---------------------------------------------------------------------------
# process_stations
# ---------------------------------------------------------------------------

def test_process_multiple_variables(fake_dobj):
    fake_dobj({
        'uri1': {
            'columns': ['TIMESTAMP', 'SWC_1', 'GPP'],
            'data': make_df(SWC_1=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
                            GPP=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]),
            'units': {'SWC_1': 'm3/m3', 'GPP': 'g C/m2/s'},
        },
        'uri2': {
            # Overlapping timestamps; keep='first' must preserve uri1 values
            'columns': ['TIMESTAMP', 'SWC_1'],
            'data': make_df(SWC_1=[9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8]),
            'units': {'SWC_1': 'm3/m3'},
        },
    })
    stations = [make_station(['uri1', 'uri2'])]

    df, units = dsm.process_stations(stations, ['SWC_1', 'GPP'])

    assert units == {'SWC_1': 'm3/m3', 'GPP': 'g C/m2/s'}
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.name == 'TIMESTAMP'
    assert df.columns.nlevels == 2
    assert list(df.columns) == [('ST1', 'GPP'), ('ST1', 'SWC_1')]
    # Concatenation of both data objects must deduplicate timestamps
    assert len(df[('ST1', 'SWC_1')]) == 8
    assert df[('ST1', 'SWC_1')].iloc[0] == pytest.approx(0.1)
    assert len(df[('ST1', 'GPP')]) == 8
    assert df[('ST1', 'GPP')].iloc[0] == pytest.approx(1.0)


def test_process_prefix_matching(fake_dobj):
    fake_dobj({
        'uri1': {
            'columns': ['TIMESTAMP', 'SWC_1', 'SWC_2', 'GPP'],
            'data': make_df(SWC_1=[0.1] * 8, SWC_2=[0.2] * 8, GPP=[1.0] * 8),
            'units': {'SWC_1': 'm3/m3', 'SWC_2': 'm3/m3', 'GPP': 'g C/m2/s'},
        },
    })
    stations = [make_station(['uri1'])]

    df, units = dsm.process_stations(stations, ['SWC'])

    assert list(df.columns) == [('ST1', 'SWC_1'), ('ST1', 'SWC_2')]
    assert units == {'SWC_1': 'm3/m3', 'SWC_2': 'm3/m3'}


def test_process_unit_fallback_from_label(fake_dobj):
    fake_dobj({
        'uri1': {
            'columns': ['TIMESTAMP', 'SWC_1 [m3/m3]'],
            'data': make_df(**{'SWC_1 [m3/m3]': [0.1] * 8}),
            # No units in metadata -> fallback to bracketed label
            'units': {},
        },
    })
    stations = [make_station(['uri1'])]

    df, units = dsm.process_stations(stations, ['SWC_1'])

    assert units == {'SWC_1 [m3/m3]': 'm3/m3'}
    assert list(df.columns) == [('ST1', 'SWC_1 [m3/m3]')]


def test_process_no_match_yields_empty(fake_dobj):
    fake_dobj({
        'uri1': {
            'columns': ['TIMESTAMP', 'SWC_1'],
            'data': make_df(SWC_1=[0.1] * 8),
            'units': {'SWC_1': 'm3/m3'},
        },
    })
    stations = [make_station(['uri1'])]

    df, units = dsm.process_stations(stations, ['GPP'])

    assert df.empty
    assert units == {}


def test_process_limit(fake_dobj):
    fake_dobj({
        f'uri{i}': {
            'columns': ['TIMESTAMP', 'SWC_1'],
            'data': make_df(SWC_1=[float(i)] * 8),
            'units': {'SWC_1': 'm3/m3'},
        }
        for i in range(3)
    })
    stations = [make_station(['uri0', 'uri1', 'uri2'])]

    df, units = dsm.process_stations(stations, ['SWC_1'], limit=1)

    assert list(df.columns) == [('ST1', 'SWC_1')]
    assert (df[('ST1', 'SWC_1')].dropna() == 0.0).all()


# ---------------------------------------------------------------------------
# resample_timeseries
# ---------------------------------------------------------------------------

def make_multicol_df():
    idx = pd.date_range('2020-01-01', periods=48, freq='h')
    s1 = pd.Series(range(48), dtype=float, index=idx)
    s2 = pd.Series(range(48, 96), dtype=float, index=idx)
    df = pd.DataFrame({('ST1', 'SWC_1'): s1, ('ST1', 'GPP'): s2})
    df.index.name = 'TIMESTAMP'
    return df


def test_resample_single_agg():
    df = make_multicol_df()
    out = dsm.resample_timeseries(df, '1D', ['mean'])

    assert out.shape == (2, 2)
    assert out.columns.nlevels == 2
    # Resampling preserves the input column order
    assert list(out.columns) == [('ST1', 'SWC_1'), ('ST1', 'GPP')]
    assert out.index.name == 'TIMESTAMP'
    # Mean of 0..23 is 11.5
    assert out[('ST1', 'SWC_1')].iloc[0] == pytest.approx(11.5)


def test_resample_multi_agg():
    df = make_multicol_df()
    out = dsm.resample_timeseries(df, '1D', ['mean', 'std'])

    # pandas appends the aggregation function as the last column level
    assert out.columns.nlevels == 3
    assert set(out.columns.get_level_values(0)) == {'ST1'}
    assert set(out.columns.get_level_values(1)) == {'GPP', 'SWC_1'}
    assert set(out.columns.get_level_values(2)) == {'mean', 'std'}
    assert out.shape == (2, 4)
    # First day: values 0..23 -> mean 11.5
    assert out[('ST1', 'SWC_1', 'mean')].iloc[0] == pytest.approx(11.5)
    assert out[('ST1', 'SWC_1', 'std')].iloc[0] == pytest.approx(
        pd.Series(range(24), dtype=float).std()
    )


def test_resample_invalid_rule_raises():
    df = make_multicol_df()
    with pytest.raises(ValueError, match='Resampling failed'):
        dsm.resample_timeseries(df, 'NOT_A_RULE', ['mean'])


def test_resample_invalid_agg_raises():
    df = make_multicol_df()
    with pytest.raises(ValueError, match='Resampling failed'):
        dsm.resample_timeseries(df, '1D', ['no_such_agg'])


def test_resample_empty_df():
    df = make_multicol_df().iloc[0:0]
    out = dsm.resample_timeseries(df, '1D', ['mean'])
    assert out.empty


# ---------------------------------------------------------------------------
# build_output_columns
# ---------------------------------------------------------------------------

def test_build_output_columns_single_var():
    cols = pd.MultiIndex.from_tuples([('ST1', 'SWC_1'), ('ST2', 'SWC_1')])
    df = pd.DataFrame(index=pd.DatetimeIndex([], name='TIMESTAMP'), columns=cols)
    names = dsm.build_output_columns(df, {'SWC_1': 'm3/m3'})
    assert names == ['ST1_SWC_1 (m3/m3)', 'ST2_SWC_1 (m3/m3)']


def test_build_output_columns_multi_var():
    cols = pd.MultiIndex.from_tuples([('ST1', 'SWC_1'), ('ST1', 'GPP')])
    df = pd.DataFrame(index=pd.DatetimeIndex([], name='TIMESTAMP'), columns=cols)
    names = dsm.build_output_columns(df, {'SWC_1': 'm3/m3', 'GPP': 'g C/m2/s'})
    assert names == ['ST1_SWC_1 (m3/m3)', 'ST1_GPP (g C/m2/s)']


def test_build_output_columns_multi_agg():
    cols = pd.MultiIndex.from_tuples(
        [('ST1', 'SWC_1', 'mean'), ('ST1', 'SWC_1', 'std')]
    )
    df = pd.DataFrame(index=pd.DatetimeIndex([], name='TIMESTAMP'), columns=cols)
    names = dsm.build_output_columns(df, {'SWC_1': 'm3/m3'})
    assert names == ['ST1_SWC_1_MEAN (m3/m3)', 'ST1_SWC_1_STD (m3/m3)']


def test_build_output_columns_unknown_unit():
    cols = pd.MultiIndex.from_tuples([('ST1', 'GPP')])
    df = pd.DataFrame(index=pd.DatetimeIndex([], name='TIMESTAMP'), columns=cols)
    assert dsm.build_output_columns(df, {}) == ['ST1_GPP']


# ---------------------------------------------------------------------------
# end-to-end: process + resample + CSV round trip
# ---------------------------------------------------------------------------

def test_end_to_end_csv(fake_dobj, tmp_path):
    fake_dobj({
        'uri1': {
            'columns': ['TIMESTAMP', 'SWC_1', 'GPP'],
            'data': make_df(SWC_1=[0.1] * 8, GPP=[1.0] * 8),
            'units': {'SWC_1': 'm3/m3', 'GPP': 'g C/m2/s'},
        },
    })
    stations = [make_station(['uri1'])]

    df, units = dsm.process_stations(stations, ['SWC_1', 'GPP'])
    df = dsm.resample_timeseries(df, '1D', ['mean'])

    out_path = tmp_path / 'icos_timeseries.csv'
    dsm.write_timeseries_csv(df, str(out_path), units)

    back = pd.read_csv(out_path, index_col=0, parse_dates=True)
    assert isinstance(back.index, pd.DatetimeIndex)
    assert back.index.name == 'TIMESTAMP'
    assert list(back.columns) == ['ST1_GPP (g C/m2/s)', 'ST1_SWC_1 (m3/m3)']
    assert back['ST1_SWC_1 (m3/m3)'].iloc[0] == pytest.approx(0.1)
    assert back['ST1_GPP (g C/m2/s)'].iloc[0] == pytest.approx(1.0)


def test_read_stations_from_csv(tmp_path):
    csv_path = tmp_path / 'stations.csv'
    csv_path.write_text(
        'station_uri,station_id,station_name,latitude,longitude,'
        'soil_moisture_variables,num_data_objects,data_object_uris\n'
        'https://example/s1,ST1,Station One,60.0,25.0,SWC_1,1,uri1\n'
    )
    stations = dsm.read_stations_from_csv(str(csv_path))
    assert len(stations) == 1
    assert stations[0]['station_id'] == 'ST1'
    assert stations[0]['data_object_uris'] == 'uri1'


# ---------------------------------------------------------------------------
# unit conversion integration
# ---------------------------------------------------------------------------

def test_parse_unit_overrides():
    assert dsm.parse_unit_overrides(None) == {}
    assert dsm.parse_unit_overrides([]) == {}
    assert dsm.parse_unit_overrides(['GPP:gC/m2/d']) == {'GPP': 'gC/m2/d'}
    assert dsm.parse_unit_overrides([' GPP : gC/m2/d ', 'NEE:gC/m2/h']) == {
        'GPP': 'gC/m2/d',
        'NEE': 'gC/m2/h',
    }
    with pytest.raises(ValueError):
        dsm.parse_unit_overrides(['GPP'])
    with pytest.raises(ValueError):
        dsm.parse_unit_overrides([':gC/m2/d'])


def test_end_to_end_unit_conversion(fake_dobj, tmp_path):
    fake_dobj({
        'uri1': {
            'columns': ['TIMESTAMP', 'GPP'],
            'data': make_df(GPP=[1.0] * 8),
            'units': {'GPP': 'g C/m2/s'},
        },
    })
    stations = [make_station(['uri1'])]

    df, units = dsm.process_stations(stations, ['GPP'])
    df, units = dsm.apply_unit_conversions(df, units)

    assert units == {'GPP': 'gC/m2/d'}
    assert df[('ST1', 'GPP')].iloc[0] == pytest.approx(86400.0)

    out_path = tmp_path / 'out.csv'
    dsm.write_timeseries_csv(df, str(out_path), units)
    back = pd.read_csv(out_path, index_col=0, parse_dates=True)
    assert list(back.columns) == ['ST1_GPP (gC/m2/d)']
    assert back['ST1_GPP (gC/m2/d)'].iloc[0] == pytest.approx(86400.0)

"""
Offline tests for units.py (pint-based unit normalization and conversion).
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import units  # noqa: E402


# ---------------------------------------------------------------------------
# normalize_unit
# ---------------------------------------------------------------------------

def test_normalize_carbon_units():
    assert units.normalize_unit('g C/m2/s') == 'gC/m**2/s'
    assert units.normalize_unit('gC/m2/s') == 'gC/m**2/s'
    assert units.normalize_unit('mg C/m2/s') == 'mgC/m**2/s'
    assert units.normalize_unit('mol C/m2/s') == 'molC/m**2/s'


def test_normalize_implicit_powers():
    assert units.normalize_unit('m3/m3') == 'm**3/m**3'
    assert units.normalize_unit('W/m2') == 'W/m**2'


def test_normalize_plain_units_unchanged():
    assert units.normalize_unit('mm') == 'mm'
    assert units.normalize_unit('mm/d') == 'mm/d'
    # Normalization is idempotent
    assert units.normalize_unit('gC/m**2/s') == 'gC/m**2/s'


def test_normalize_fluxnet_units():
    # ETC L2 FluxNet product reports molar carbon fluxes as 'µmol m-2 s-1'
    assert units.normalize_unit('µmol m-2 s-1') == 'umolC m**-2 s**-1'
    assert units.normalize_unit('umol m-2 s-1') == 'umolC m**-2 s**-1'
    assert units.normalize_unit('mol m-2 s-1') == 'molC m**-2 s**-1'
    assert units.normalize_unit('mmol m-2 s-1') == 'mmolC m**-2 s**-1'
    # Normalization is idempotent
    assert units.normalize_unit('umolC m**-2 s**-1') == 'umolC m**-2 s**-1'


# ---------------------------------------------------------------------------
# base_name
# ---------------------------------------------------------------------------

def test_base_name():
    assert units.base_name('GPP') == 'GPP'
    assert units.base_name('SWC_1 [m3/m3]') == 'SWC_1'
    assert units.base_name('GPP [g C/m2/s]') == 'GPP'


# ---------------------------------------------------------------------------
# conversion_factor / convert_series
# ---------------------------------------------------------------------------

def test_conversion_factor_seconds_to_days():
    assert units.conversion_factor('gC/m2/s', 'gC/m2/d') == pytest.approx(86400.0)


def test_conversion_factor_icos_source_notation():
    assert units.conversion_factor('g C/m2/s', 'gC/m2/d') == pytest.approx(86400.0)


def test_conversion_factor_molar_to_mass():
    # mol C -> g C uses the standard atomic weight of carbon (12.011 g/mol)
    assert units.conversion_factor('mol C/m2/s', 'gC/m2/d') == pytest.approx(
        units.C_MOLAR_MASS_G_PER_MOL * 86400.0
    )


def test_conversion_factor_fluxnet_molar_to_mass():
    # µmol m-2 s-1 -> gC/m2/d: 1e-6 mol * 12.011 g/mol * 86400 s/d
    assert units.conversion_factor('µmol m-2 s-1', 'gC/m2/d') == pytest.approx(
        1e-6 * units.C_MOLAR_MASS_G_PER_MOL * 86400.0
    )


def test_conversion_factor_inverse():
    assert units.conversion_factor('gC/m2/d', 'gC/m2/s') == pytest.approx(1 / 86400)


def test_conversion_factor_incompatible_dimensions_raises():
    with pytest.raises(Exception):
        units.conversion_factor('m3/m3', 'gC/m2/d')


def test_conversion_factor_unknown_unit_raises():
    with pytest.raises(Exception):
        units.conversion_factor('not a unit', 'gC/m2/d')


def test_convert_series_preserves_nan():
    s = pd.Series([1.0, 2.0, float('nan')])
    out = units.convert_series(s, 'gC/m2/s', 'gC/m2/d')
    assert out.iloc[0] == pytest.approx(86400.0)
    assert out.iloc[1] == pytest.approx(172800.0)
    assert pd.isna(out.iloc[2])


# ---------------------------------------------------------------------------
# apply_unit_conversions
# ---------------------------------------------------------------------------

def make_df():
    idx = pd.date_range('2020-01-01', periods=4, freq='h')
    df = pd.DataFrame({
        ('ST1', 'GPP'): [1.0, 2.0, 3.0, 4.0],
        ('ST1', 'SWC_1'): [0.1, 0.2, 0.3, 0.4],
        ('ST2', 'GPP'): [0.5, 0.5, 0.5, 0.5],
    })
    df.index.name = 'TIMESTAMP'
    return df


def test_apply_defaults_convert_gpp_only():
    df = make_df()
    out, unit_map = units.apply_unit_conversions(
        df, {'GPP': 'g C/m2/s', 'SWC_1': 'm3/m3'}
    )
    assert unit_map == {'GPP': 'gC/m2/d', 'SWC_1': 'm3/m3'}
    assert out[('ST1', 'GPP')].iloc[0] == pytest.approx(86400.0)
    assert out[('ST2', 'GPP')].iloc[0] == pytest.approx(43200.0)
    # SWC (no target unit) is untouched
    assert out[('ST1', 'SWC_1')].iloc[0] == pytest.approx(0.1)


def test_apply_override_beats_default():
    df = make_df()
    out, unit_map = units.apply_unit_conversions(
        df, {'GPP': 'gC/m2/s'}, overrides={'GPP': 'gC/m2/h'}
    )
    assert unit_map['GPP'] == 'gC/m2/h'
    assert out[('ST1', 'GPP')].iloc[0] == pytest.approx(3600.0)


def test_apply_skips_unknown_source_unit():
    df = make_df()
    # No source unit recorded for GPP -> cannot convert, keep as-is
    out, unit_map = units.apply_unit_conversions(df, {})
    assert unit_map == {}
    assert out[('ST1', 'GPP')].iloc[0] == pytest.approx(1.0)


def test_apply_skips_incompatible_target():
    df = make_df()
    out, unit_map = units.apply_unit_conversions(
        df, {'SWC_1': 'm3/m3'}, overrides={'SWC_1': 'gC/m2/d'}
    )
    assert unit_map == {'SWC_1': 'm3/m3'}
    assert out[('ST1', 'SWC_1')].iloc[0] == pytest.approx(0.1)


def test_apply_empty_df_unchanged():
    df = make_df().iloc[0:0]
    out, unit_map = units.apply_unit_conversions(df, {'GPP': 'gC/m2/s'})
    assert out.empty
    assert unit_map == {'GPP': 'gC/m2/s'}


def test_apply_matches_bracketed_labels():
    idx = pd.date_range('2020-01-01', periods=4, freq='h')
    df = pd.DataFrame({
        ('ST1', 'GPP [g C/m2/s]'): [1.0, 2.0, 3.0, 4.0],
        ('ST1', 'SWC_1'): [0.1, 0.2, 0.3, 0.4],
    })
    df.index.name = 'TIMESTAMP'
    out, unit_map = units.apply_unit_conversions(
        df, {'GPP [g C/m2/s]': 'g C/m2/s'}
    )
    assert unit_map == {'GPP [g C/m2/s]': 'gC/m2/d'}
    assert out[('ST1', 'GPP [g C/m2/s]')].iloc[0] == pytest.approx(86400.0)


# ---------------------------------------------------------------------------
# FluxNet defaults (GPP_NT_CUT_REF etc.)
# ---------------------------------------------------------------------------

def test_default_target_units_include_fluxnet_columns():
    for name in ('GPP_NT_CUT_REF', 'GPP_NT_VUT_REF', 'GPP_DT_CUT_REF',
                 'GPP_DT_VUT_REF', 'NEE_CUT_REF', 'NEE_VUT_REF',
                 'RECO_NT_CUT_REF', 'RECO_NT_VUT_REF'):
        assert units.DEFAULT_TARGET_UNITS[name] == 'gC/m2/d'


def test_apply_defaults_convert_fluxnet_gpp():
    idx = pd.date_range('2020-01-01', periods=4, freq='h')
    df = pd.DataFrame({
        ('ST1', 'GPP_NT_CUT_REF'): [1.0, 2.0, 3.0, 4.0],
        ('ST1', 'SWC_1'): [0.1, 0.2, 0.3, 0.4],
    })
    df.index.name = 'TIMESTAMP'
    out, unit_map = units.apply_unit_conversions(
        df, {'GPP_NT_CUT_REF': 'µmol m-2 s-1', 'SWC_1': 'm3/m3'}
    )
    assert unit_map == {'GPP_NT_CUT_REF': 'gC/m2/d', 'SWC_1': 'm3/m3'}
    assert out[('ST1', 'GPP_NT_CUT_REF')].iloc[0] == pytest.approx(
        1e-6 * units.C_MOLAR_MASS_G_PER_MOL * 86400.0
    )
    # SWC (no target unit) is untouched
    assert out[('ST1', 'SWC_1')].iloc[0] == pytest.approx(0.1)

"""
Pint-based unit handling for ICOS time series data.

ICOS L2 data objects report unit strings such as 'g C/m2/s' (L2 fluxes),
'\u00b5mol m-2 s-1' (FluxNet product: GPP, NEE, RECO) or 'm3/m3' (soil water
content). This module provides:

- a pint UnitRegistry that understands ICOS-style notation, including
  carbon-bearing units ('g C', 'mol C', 'umol', ...), implicit powers
  ('m2', 'm3') and negative exponents ('m-2', 's-1');
- conversion helpers (conversion_factor, convert_series) to convert values
  between units;
- apply_unit_conversions(), which converts the columns of a
  station/variable DataFrame to per-variable target units.

By default, carbon flux variables (GPP, NEE, RE, NBP and the FluxNet
product columns such as GPP_NT_CUT_REF) are converted to gC/m2/d;
variables without a target unit (e.g. SWC in m3/m3) are left untouched.
"""

import re

import pandas as pd
from pint import UnitRegistry

# Standard atomic weight of carbon (g/mol). Molar carbon fluxes (mol C)
# are converted to mass fluxes (g C) with this factor.
C_MOLAR_MASS_G_PER_MOL = 12.011

# Target units applied automatically, keyed by variable name (the column
# label without its trailing '[unit]' part).
DEFAULT_TARGET_UNITS = {
    'GPP': 'gC/m2/d',
    'NEE': 'gC/m2/d',
    'RE': 'gC/m2/d',
    'NBP': 'gC/m2/d',
    # Column names of the FluxNet-format L2 product (etcL2Fluxnet), e.g.
    # the reference-model GPP (Lasslop et al. 2010).
    'GPP_NT_CUT_REF': 'gC/m2/d',
    'GPP_NT_VUT_REF': 'gC/m2/d',
    'GPP_DT_CUT_REF': 'gC/m2/d',
    'GPP_DT_VUT_REF': 'gC/m2/d',
    'NEE_CUT_REF': 'gC/m2/d',
    'NEE_VUT_REF': 'gC/m2/d',
    'RECO_NT_CUT_REF': 'gC/m2/d',
    'RECO_NT_VUT_REF': 'gC/m2/d',
}

# Column labels may embed their unit in square brackets, e.g. 'SWC_1 [m3/m3]'.
UNIT_LABEL_RE = re.compile(r'^(?P<name>.+?)\s*\[(?P<unit>[^\]]+)\]$')

# 'g C', 'mg C', 'kg C', 'mol C' -> gC, mgC, kgC, molC.
# (A bare 'C' is parsed by pint as the Coulomb, so the carbon marker
# must be glued to the mass/mole unit.)
_CARBON_UNIT_RE = re.compile(r'\b(mg|kg|g|mol)\s+C\b')
# Implicit powers, as used by ICOS: 'm2' -> 'm**2', 'm3' -> 'm**3'.
_IMPLICIT_POWER_RE = re.compile(r'([A-Za-z°_])([A-Za-z_]*)(\d+)')
# Negative exponents, as used by the ICOS FluxNet product:
# 'm-2' -> 'm**-2', 's-1' -> 's**-1'.
_NEG_EXP_RE = re.compile(r'([A-Za-z°_][A-Za-z_]*)(-\d+)')
# Molar units without an explicit carbon marker ('mol', 'umol', 'mmol', ...).
# In ICOS ecosystem data these always refer to moles of carbon.
_MOL_RE = re.compile(r'\b(u|mm?|n|k)?mol\b')

_registry = None


def get_registry():
    """Return the shared pint UnitRegistry (created on first use)."""
    global _registry
    if _registry is None:
        ureg = UnitRegistry()
        # Carbon-bearing units as single, unambiguous tokens:
        ureg.define('gC = g')
        ureg.define('mgC = 0.001 * gC')
        ureg.define('kgC = 1000 * gC')
        ureg.define(f'molC = {C_MOLAR_MASS_G_PER_MOL} * g')
        # Prefixed carbon-mole units (used by the FluxNet product,
        # e.g. GPP in 'umol m-2 s-1').
        ureg.define('mmolC = 0.001 * molC')
        ureg.define('umolC = 0.001 * mmolC')
        ureg.define('nmolC = 0.001 * umolC')
        ureg.define('kmolC = 1000 * molC')
        _registry = ureg
    return _registry


def normalize_unit(unit):
    """
    Rewrite an ICOS-style unit string into a pint-parseable form.

    - 'g C', 'mg C', 'kg C', 'mol C' -> gC, mgC, kgC, molC
    - implicit powers: 'm2' -> 'm**2', 'm3' -> 'm**3'
    - negative exponents: 'm-2' -> 'm**-2', 's-1' -> 's**-1'
    - molar units (ICOS carbon notation): 'umol' -> 'umolC', 'mol' -> 'molC'

    Args:
        unit: Unit string (e.g. 'g C/m2/s', 'm3/m3', '\u00b5mol m-2 s-1')

    Returns:
        Normalized unit string (e.g. 'gC/m**2/s', 'm**3/m**3',
        'umolC m**-2 s**-1')
    """
    s = str(unit).strip()
    s = s.replace('\u00b5', 'u')  # unicode micro sign -> ASCII
    s = _CARBON_UNIT_RE.sub(lambda m: m.group(1) + 'C', s)
    s = _IMPLICIT_POWER_RE.sub(r'\1\2**\3', s)
    s = _NEG_EXP_RE.sub(r'\1**\2', s)
    s = _MOL_RE.sub(lambda m: (m.group(1) or '') + 'molC', s)
    return s


def base_name(label):
    """
    Return the variable name of a column label, without a trailing
    '[unit]' part (e.g. 'SWC_1 [m3/m3]' -> 'SWC_1').
    """
    m = UNIT_LABEL_RE.match(label)
    return m.group('name').strip() if m else label


def conversion_factor(from_unit, to_unit):
    """
    Constant multiplicative factor that converts values from `from_unit`
    to `to_unit`.

    Args:
        from_unit: Source unit string (e.g. 'g C/m2/s')
        to_unit: Target unit string (e.g. 'gC/m2/d')

    Returns:
        Float factor such that value * factor is expressed in to_unit

    Raises:
        pint.errors.UndefinedUnitError / UnitParseException:
            if either unit cannot be parsed
        pint.errors.DimensionalityError:
            if the units have incompatible dimensions
            (e.g. m3/m3 -> gC/m2/d)
    """
    ureg = get_registry()
    quantity = ureg.Quantity(1.0, normalize_unit(from_unit))
    return quantity.to(normalize_unit(to_unit)).magnitude


def convert_series(series, from_unit, to_unit):
    """
    Convert a pandas Series (or array-like) of values from `from_unit`
    to `to_unit`. NaN values are preserved.

    Args:
        series: Values to convert
        from_unit: Unit the values are currently in
        to_unit: Unit to convert to

    Returns:
        Converted values (unitless magnitudes)
    """
    factor = conversion_factor(from_unit, to_unit)
    return series * factor


def apply_unit_conversions(df, variable_units, overrides=None):
    """
    Convert the columns of a station/variable DataFrame to target units.

    A variable is converted when a target unit is known for it: first from
    `overrides` (variable name -> unit), then from DEFAULT_TARGET_UNITS.
    Conversion is only applied when the source unit is recorded in
    `variable_units` and dimensionally compatible with the target;
    otherwise the variable is left untouched and a warning is printed.

    Args:
        df: DataFrame with MultiIndex columns (station, variable) or
            (station, variable, agg)
        variable_units: Dict mapping variable label -> source unit
        overrides: Optional dict mapping variable name -> target unit

    Returns:
        Tuple (converted_df, variable_units) where variable_units has the
        target units substituted for the converted variables. An empty
        DataFrame is returned unchanged.
    """
    units = dict(variable_units)
    if df is None or df.empty or not isinstance(df.columns, pd.MultiIndex):
        return df, units

    targets = {}
    for label, from_unit in variable_units.items():
        name = base_name(label)
        target = (overrides or {}).get(name) or DEFAULT_TARGET_UNITS.get(name)
        if target:
            targets[label] = (from_unit, target)

    out = df.copy()
    variable_level = out.columns.get_level_values(1)
    for label, (from_unit, target) in targets.items():
        mask = variable_level == label
        if not mask.any():
            continue
        try:
            factor = conversion_factor(from_unit, target)
        except Exception as e:
            print(f"  ! Could not convert {label}: {from_unit} -> {target} ({e}). "
                  f"Keeping original unit.")
            continue
        out.loc[:, mask] = out.loc[:, mask] * factor
        units[label] = target
        print(f"  ~ Converted {label}: {from_unit} -> {target} (factor {factor})")

    return out, units

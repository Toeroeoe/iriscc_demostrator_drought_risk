"""
Drought hydrograph plot for IRISCC Shiny app.

Translates the R implementation from drought_hydrograph_shiny.R to Python.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import pandas as pd
from scipy import interpolate

from shared import get_gauge_discharge, discharge_time


# =============================================================================
# Styling constants (matching R implementation)
# =============================================================================
COL_Q = "#1f4fd8"      # blue - monthly hydrograph
COL_10YR = "#f08c00"   # orange - 10-yr return period
COL_50YR = "#b23a00"   # dark orange - 50-yr return period
COL_AXIS = "#eeeeee"   # light gray - axes/text

FILL_ALPHA = 0.6
LWD_MAIN = 1.4
LWD_RP = 0.6

FONT_FAMILY = "Inter"
FONT_TITLE = "Crimson Text"

FS_AXTEXT = 14
FS_AXTITLE = 16
FS_LEGEND = 14
FS_TITLE = 20
FS_TITLE_MAIN = 22
FS_TITLE_PAREN = 16


def _apply_persistence(below: np.ndarray, k: int) -> np.ndarray:
    """Keep TRUE only where it belongs to a run of >= k consecutive TRUEs."""
    if k <= 1 or len(below) == 0:
        return below
    
    values = below[:-1] != below[1:]
    run_lengths = np.diff(np.concatenate(([0], np.where(values)[0], [len(below)])))
    run_values = below[np.concatenate(([0], np.where(values)[0]))]
    
    keep = run_values & (run_lengths >= k)
    
    result = np.zeros(len(below), dtype=bool)
    idx = 0
    for length, value in zip(run_lengths, keep):
        if value:
            result[idx:idx + length] = True
        idx += length
    
    return result


def _compute_monthly_thresholds(qobs: np.ndarray, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Compute per-calendar-month quantiles (0.10 and 0.02) from full record."""
    months = np.arange(1, 13)
    thresholds = []
    
    for m in months:
        mask = dates.month == m
        qm = qobs[mask]
        qm_valid = qm[~np.isnan(qm)]
        
        if len(qm_valid) > 0:
            thr_10yr = np.quantile(qm_valid, 0.10)
            thr_50yr = np.quantile(qm_valid, 0.02)
        else:
            thr_10yr = np.nan
            thr_50yr = np.nan
        
        thresholds.append({
            'month': m,
            'thr_10yr': thr_10yr,
            'thr_50yr': thr_50yr
        })
    
    return pd.DataFrame(thresholds)


def _smooth_series(x: np.ndarray, y: np.ndarray, nout: int = 1000) -> tuple:
    """Smooth a series using spline interpolation (non-negative)."""
    valid = ~np.isnan(y)
    x_valid = x[valid]
    y_valid = y[valid]
    
    if len(x_valid) < 3:
        return x_valid, np.maximum(y_valid, 0)
    
    try:
        tck = interpolate.splrep(x_valid, y_valid, s=0)
        x_out = np.linspace(x_valid.min(), x_valid.max(), nout)
        y_out = np.maximum(interpolate.splev(x_out, tck), 0)
        return x_out, y_out
    except:
        return x_valid, np.maximum(y_valid, 0)

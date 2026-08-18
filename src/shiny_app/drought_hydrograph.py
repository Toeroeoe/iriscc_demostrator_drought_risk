"""
Drought hydrograph plot for IRISCC Shiny app - Python implementation.
"""
from matplotlib.layout_engine import LayoutEngine
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import pandas as pd
from scipy import interpolate
from shared import get_gauge_discharge, discharge_time
from theme_config import get_theme_config


class _NoOpLayoutEngine(LayoutEngine):
    """A no-op layout engine to prevent Shiny from applying tight_layout."""
    _adjust_compatible = True
    _colorbar_gridspec = True

    def execute(self, fig) -> None:  # type: ignore[override]
        pass  # deliberately do nothing


# Styling constants - colors will be fetched from theme at runtime
COL_10YR = '#f08c00'   # orange - 10-yr return period
COL_50YR = '#b23a00'   # dark orange - 50-yr return period
FILL_ALPHA = 0.4
LWD_MAIN = 0.8

def _apply_persistence(below, k):
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

def _compute_monthly_thresholds(qobs, dates):
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
            thr_10yr, thr_50yr = np.nan, np.nan
        thresholds.append({'month': m, 'thr_10yr': thr_10yr, 'thr_50yr': thr_50yr})
    return pd.DataFrame(thresholds)

def _smooth_series(x, y, nout=1000):
    """Smooth a series using cubic spline interpolation.

    This matches the R implementation which uses spline(x, y, n=nout).
    For data with duplicate x values, we first aggregate by taking the mean.

    Args:
        x: X coordinates
        y: Y coordinates (may contain NaN)
        nout: Number of output points

    Returns:
        (x_out, y_out) tuple with nout points, non-negative values
    """
    # Remove NaN values
    valid = ~np.isnan(y)
    x_valid = x[valid]
    y_valid = y[valid]

    if len(x_valid) < 3:
        # Too few points for spline, return what we have
        return np.linspace(x.min(), x.max(), nout) if len(x) > 0 else np.array([]), np.maximum(y_valid, 0)

    try:
        # Check for duplicate x values and aggregate if needed
        unique_x, indices, counts = np.unique(x_valid, return_inverse=True, return_counts=True)

        if len(unique_x) < len(x_valid):
            # Have duplicates - aggregate y by mean for each unique x
            y_agg = np.array([np.mean(y_valid[indices == i]) for i in range(len(unique_x))])
            # Sort by x for spline fitting
            sort_idx = np.argsort(unique_x)
            x_sorted = unique_x[sort_idx]
            y_sorted = y_agg[sort_idx]
        else:
            # No duplicates - use original data
            sort_idx = np.argsort(x_valid)
            x_sorted = x_valid[sort_idx]
            y_sorted = y_valid[sort_idx]

        # Apply cubic spline interpolation (no smoothing, just interpolation like R's spline())
        tck = interpolate.splrep(x_sorted, y_sorted, s=0)  # s=0 means no smoothing
        x_out = np.linspace(x_sorted.min(), x_sorted.max(), nout)
        y_out = np.maximum(interpolate.splev(x_out, tck), 0)

        return x_out, y_out
    except Exception:
        # Fallback: return linear interpolation
        y_out = np.maximum(y_valid, 0)
        x_out = np.linspace(x.min(), x.max(), nout) if len(x) > 0 else np.array([])
        return x_out, y_out


def _create_main_plot(ax, dec_df, s10_x, s10_y, s50_x, s50_y, hydro_x, hydro_y, decade, palette, theme_config):
    """Create main hydrograph plot with theme-consistent styling."""
    COL_TEXT = palette['text']
    COL_GRID = palette['grid']
    COL_BG = palette['background']
    COL_PRIMARY = palette['primary']

    FONT_BODY = theme_config.get_font_family('body')
    FONT_HEADING = theme_config.get_font_family('heading')
    FONT_MONO = theme_config.get_font_family('mono')

    FS_SMALL = theme_config.font_sizes['small']
    FS_BASE = theme_config.font_sizes['base']
    FS_LARGE = theme_config.font_sizes['large']
    FS_TITLE = theme_config.font_sizes['title']
    FS_HEADING = theme_config.font_sizes['heading']

    # Fill areas first (so they're behind the line)
    ax.fill_between(s10_x, s10_y, color=COL_10YR, alpha=FILL_ALPHA, label='10-yr', zorder=1)
    ax.fill_between(s50_x, s50_y, color=COL_50YR, alpha=FILL_ALPHA, label='50-yr', zorder=1)

    # Plot hydrograph line - use smoothed data (no gaps)
    line = ax.plot(
        hydro_x, hydro_y, color=COL_PRIMARY, linewidth=LWD_MAIN,
        label='Monthly hydrograph', zorder=10, solid_capstyle='round',
        solid_joinstyle='round'
    )[0]

    # Explicitly set zorder to ensure line is on top
    if line is not None:
        line.set_zorder(100)

    # Set y-limits based on BOTH hydrograph AND threshold fills
    hydro_max = hydro_y.max() if len(hydro_y) > 0 else dec_df['Q'].max()
    if np.isnan(hydro_max) or hydro_max <= 0:
        hydro_max = 100

    # Also consider the maximum threshold values from fills
    threshold_max = max(
        np.nanmax(s10_y) if len(s10_y) > 0 and not np.all(np.isnan(s10_y)) else 0,
        np.nanmax(s50_y) if len(s50_y) > 0 and not np.all(np.isnan(s50_y)) else 0
    )

    # Use the larger of hydrograph max or threshold max
    y_max = max(hydro_max, threshold_max) * 1.1  # 10% headroom
    ax.set_ylim(0, y_max)

    # X-axis labels (years) - use mono font for all tick labels
    year_breaks = np.array(decade) - min(decade)
    ax.set_xticks(year_breaks)
    ax.set_xticklabels(
        [str(y) for y in decade], 
        fontsize=FS_SMALL, family=FONT_MONO, color=COL_TEXT
    )
    
    # Tick params - smaller size for tick labels
    ax.tick_params(
        axis='both', direction='in', length=5, 
        color=COL_TEXT, labelsize=FS_SMALL
    )
    
    # Set font family for tick labels (tick_params doesn't support family directly)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontfamily(FONT_MONO)
    
    # Y-axis label - use body font, smaller size
    ax.set_ylabel(
        'streamflow (m³/s)', 
        fontsize=FS_BASE, family=FONT_BODY, color=COL_TEXT
    )
    ax.yaxis.set_label_coords(-0.12, 0.5)

    # Hide all spines for modern look
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.tick_params(colors=COL_TEXT)
    ax.set_facecolor('none')

    # Legend with theme colors - smaller, mono font
    ax.legend(
        loc='upper right', 
        frameon=True, 
        facecolor=COL_BG,
        edgecolor=COL_GRID, 
        fontsize=FS_LEGEND,
        family=FONT_MONO,
        labelcolor=COL_TEXT,
        borderpad=0.6,
        labelspacing=0.4,
        framealpha=0.95
    )

    return ax

def _create_total_inset(ax, dec_df, decade, palette, theme_config):
    """Create total drought event count inset plot."""
    COL_TEXT = palette['text']
    COL_GRID = palette['grid']
    COL_BG = palette['background']

    FONT_BODY = theme_config.get_font_family('body')
    FONT_HEADING = theme_config.get_font_family('heading')
    FONT_MONO = theme_config.get_font_family('mono')

    FS_SMALL = theme_config.font_sizes['small']
    FS_BASE = theme_config.font_sizes['base']
    FS_TITLE = theme_config.font_sizes['title']
    FS_HEADING = theme_config.font_sizes['heading']

    count_q10 = sum((dec_df['drought_10yr']) & (~dec_df['drought_50yr']))
    count_q50 = sum(dec_df['drought_50yr'])
    counts = [count_q10, count_q50]
    y_pos = np.arange(2)
    width = 0.5

    bars = ax.barh(
        y_pos, counts, height=width,
        color=[COL_10YR, COL_50YR],
        alpha=FILL_ALPHA,
        edgecolor=[COL_10YR, COL_50YR],
        linewidth=0.8
    )
    
    # Hide all spines for modern look
    for spine in ax.spines.values():
        spine.set_visible(False)
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(
        ['Q10', 'Q50'],
        fontsize=FS_SMALL, family=FONT_MONO, color=COL_TEXT
    )

    ax.set_xlabel(
        'event count', fontsize=FS_BASE, family=FONT_BODY, color=COL_TEXT
    )
    ax.set_title(
        f'Total drought events',
        fontsize=FS_TITLE, family=FONT_HEADING, color=COL_TEXT, pad=10
    )
    
    # Set font family for tick labels
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontfamily(FONT_MONO)

    ax.tick_params(colors=COL_TEXT)
    ax.set_facecolor('none')
    return ax

def _create_monthly_inset(ax, dec_df, decade, palette, theme_config):
    """Create monthly drought event count inset plot."""
    COL_TEXT = palette['text']
    COL_GRID = palette['grid']
    COL_BG = palette['background']

    FONT_BODY = theme_config.get_font_family('body')
    FONT_HEADING = theme_config.get_font_family('heading')
    FONT_MONO = theme_config.get_font_family('mono')

    FS_SMALL = theme_config.font_sizes['small']
    FS_BASE = theme_config.font_sizes['base']
    FS_TITLE = theme_config.font_sizes['title']
    FS_HEADING = theme_config.font_sizes['heading']

    months_initial = ['J','F','M','A','M','J','J','A','S','O','N','D']
    x = np.arange(12)
    width = 0.25
    counts_q10, counts_q50 = [], []
    for m in range(1, 13):
        sub = dec_df[dec_df['month'] == m]
        c10 = sum((sub['drought_10yr']) & (~sub['drought_50yr']))
        c50 = sum(sub['drought_50yr'])
        counts_q10.append(c10)
        counts_q50.append(c50)

    ax.bar(
        x - width/2, counts_q10, width,
        color=COL_10YR, alpha=FILL_ALPHA,
        edgecolor=COL_10YR, linewidth=0.8
    )
    ax.bar(
        x + width/2, counts_q50, width,
        color=COL_50YR, alpha=FILL_ALPHA,
        edgecolor=COL_50YR, linewidth=0.8
    )

    # Hide all spines for modern look
    for spine in ax.spines.values():
        spine.set_visible(False)
    
    ax.set_xticks(x)
    ax.set_xticklabels(
        months_initial, fontsize=FS_SMALL, family=FONT_MONO, color=COL_TEXT
    )
    ax.set_ylabel(
        'event count', fontsize=FS_BASE, family=FONT_BODY, color=COL_TEXT
    )
    ax.set_title(
        f'Drought events by month',
        fontsize=FS_TITLE, family=FONT_HEADING, color=COL_TEXT, pad=10
    )
    
    # Set font family for tick labels
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontfamily(FONT_MONO)

    ax.tick_params(colors=COL_TEXT)
    ax.set_facecolor('none')
    return ax

def create_drought_hydrograph(gauge_id, decade_year=None, persistence=1):
    """Main function to create the drought hydrograph plot.

    Modern design with:
    - Theme-consistent colors and fonts (Inter, Crimson Text, IBM Plex Mono)
    - No axis splines for clean look
    - More spacious layout
    - Mono font for data values and coordinates

    Args:
        gauge_id: Zero-padded 10-digit gauge ID (e.g., '0006112080')
        decade_year: Integer representing the decade start (e.g., 1960 for 1960-1969)
                   If None, uses the first available decade from the data.
        persistence: Minimum consecutive months below threshold (default=1)

    Returns:
        matplotlib.figure.Figure with theme styling
    """
    # Get theme configuration
    theme_config = get_theme_config('dark')  # App uses dark theme
    palette = theme_config.get_plot_palette()

    # Get discharge data
    qobs, qsim = get_gauge_discharge(gauge_id)
    if qobs is None or len(qobs) == 0:
        raise ValueError(f"No discharge data found for gauge {gauge_id}")

    # Get dates from discharge_time
    dates = discharge_time

    # Compute thresholds from full record
    thresholds = _compute_monthly_thresholds(qobs, dates)

    # Create flow dataframe
    flow = pd.DataFrame({
        'year': dates.year,
        'month': dates.month,
        'Q': qobs
    })
    flow = flow.merge(thresholds, on='month')
    flow = flow.sort_values(['year', 'month']).reset_index(drop=True)

    # Apply persistence filter
    flow.loc[:, 'drought_10yr'] = _apply_persistence(flow['Q'] < flow['thr_10yr'], persistence)
    flow.loc[:, 'drought_50yr'] = _apply_persistence(flow['Q'] < flow['thr_50yr'], persistence)

    # Determine decade
    if decade_year is None:
        decade_year = flow['year'].min() // 10 * 10
    decade = list(range(decade_year, decade_year + 10))

    # Subset to decade
    dec_df = flow[flow['year'].isin(decade)].copy()
    if len(dec_df) == 0:
        raise ValueError(f"No data in decade {decade_year}-{decade_year+9}")

    # Create time index for plotting
    dec_df.loc[:, 't'] = (dec_df['year'] - decade_year) + (dec_df['month'] - 0.5) / 12

    # Smooth threshold curves (these should be continuous)
    thr_pts = []
    for y in decade:
        for _, row in thresholds.iterrows():
            thr_pts.append({
                't': (y - decade_year) + (row['month'] - 0.5) / 12,
                'thr_10yr': row['thr_10yr'],
                'thr_50yr': row['thr_50yr']
            })
    thr_pts = pd.DataFrame(thr_pts).sort_values('t')

    s10_x, s10_y = _smooth_series(thr_pts['t'].values, thr_pts['thr_10yr'].values)
    s50_x, s50_y = _smooth_series(thr_pts['t'].values, thr_pts['thr_50yr'].values)

    # For hydrograph line, use smoothed data (no gaps)
    # Sort by time for proper line drawing
    dec_df_sorted = dec_df.sort_values('t').copy()
    hydro_x = dec_df_sorted['t'].values
    hydro_y = dec_df_sorted['Q'].values

    # Apply smoothing to hydrograph
    hydro_x_smooth, hydro_y_smooth = _smooth_series(hydro_x, hydro_y, nout=len(hydro_x))

    # Define colors from theme
    COL_TEXT = palette['text']
    COL_BG = palette['background']
    COL_GRID = palette['grid']
    COL_PRIMARY = palette['primary']
    COL_10YR = '#f08c00'   # orange - 10-yr return period
    COL_50YR = '#b23a00'   # dark orange - 50-yr return period

    # Define font families
    FONT_BODY = theme_config.get_font_family('body')
    FONT_HEADING = theme_config.get_font_family('heading')
    FONT_MONO = theme_config.get_font_family('mono')

    # Define font sizes (smaller for tick labels and axis labels to match other plots)
    FS_SMALL = theme_config.font_sizes['small']  # 12px - for tick labels
    FS_BASE = theme_config.font_sizes['base']    # 14px - for axis labels
    FS_LARGE = theme_config.font_sizes['large']  # 16px
    FS_TITLE = theme_config.font_sizes['title']  # 20px
    FS_HEADING = theme_config.font_sizes['heading']  # 24px
    FS_LEGEND = theme_config.font_sizes['small']  # 12px - for legend

    # Create figure with more spacious layout
    fig = plt.figure(figsize=(14, 14), facecolor=COL_BG)

    # Install no-op layout engine to prevent Shiny from applying tight_layout
    fig.set_layout_engine(_NoOpLayoutEngine())
    fig.tight_layout = lambda *a, **kw: None

    # Create GridSpec with more spacing (more room for labels, better proportions)
    # Create simplified GridSpec with just 2 rows and 2 columns
    gs = gridspec.GridSpec(
        figure=fig,
        nrows=2,
        ncols=2,
        height_ratios=[0.6, 1.2],  # Main plot larger than insets
        width_ratios=[1.0, 1.0],   # Equal width for both inset columns
        hspace=0.30,
        wspace=0.20,
        left=0.08,
        right=0.96,
        top=0.95,
        bottom=0.06
    )
    
    # Insets in row 0 (side by side)
    # Insets in row 0 (side by side)
    ax_total = fig.add_subplot(gs[0, 0])
    ax_month = fig.add_subplot(gs[0, 1])
    
    _create_total_inset(ax_total, dec_df, decade, palette, theme_config)
    _create_monthly_inset(ax_month, dec_df, decade, palette, theme_config)
    
    # Main plot in row 1 (spans both columns)
    ax_main = fig.add_subplot(gs[1, :])
    _create_main_plot(
        ax_main, dec_df, s10_x, s10_y, s50_x, s50_y,
        hydro_x_smooth, hydro_y_smooth, decade,
        palette, theme_config
    )

    return fig

"""
Drought hydrograph plot for IRISCC Shiny app - Python implementation.
"""
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import pandas as pd
from scipy import interpolate
from shared import get_gauge_discharge, discharge_time

# Styling constants
COL_Q = "#4d94ff"      # brighter blue - monthly hydrograph
COL_10YR = "#f08c00"   # orange - 10-yr return period
COL_50YR = "#b23a00"   # dark orange - 50-yr return period
COL_AXIS = "#eeeeee"   # light gray - axes/text
FILL_ALPHA = 0.4       # reduced alpha for fills to make line more visible
LWD_MAIN = 0.8         # reduced linewidth for cleaner look
LWD_RP = 0.8
FONT_FAMILY = "Inter"
FONT_TITLE = "Crimson Text"
FS_AXTEXT = 14
FS_AXTITLE = 16
FS_LEGEND = 14
FS_TITLE = 20
FS_TITLE_MAIN = 22

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


def _create_main_plot(ax, dec_df, s10_x, s10_y, s50_x, s50_y, hydro_x, hydro_y, decade):
    # Fill areas first (so they're behind the line)
    ax.fill_between(s10_x, s10_y, color=COL_10YR, alpha=FILL_ALPHA, label='10-yr', zorder=1)
    ax.fill_between(s50_x, s50_y, color=COL_50YR, alpha=FILL_ALPHA, label='50-yr', zorder=1)
    
    # Plot hydrograph line - use smoothed data (no gaps)
    line = ax.plot(hydro_x, hydro_y, color=COL_Q, linewidth=LWD_MAIN, 
                   label='Monthly hydrograph', zorder=10, solid_capstyle='round', 
                   solid_joinstyle='round')[0]
    
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
    print(f"DEBUG: Setting ylim to (0, {y_max:.2f}) - hydro_max={hydro_max:.2f}, threshold_max={threshold_max:.2f}")
    ax.set_ylim(0, y_max)
    year_breaks = np.array(decade) - min(decade)
    ax.set_xticks(year_breaks)
    ax.set_xticklabels([str(y) for y in decade], fontsize=FS_AXTEXT, color=COL_AXIS)
    ax.tick_params(axis='both', direction='in', length=6, color=COL_AXIS)
    ax.set_ylabel('streamflow (m³/s)', fontsize=FS_AXTITLE, color=COL_AXIS)
    ax.yaxis.set_label_coords(-0.08, 0.5)
    for spine in ax.spines.values():
        spine.set_color(COL_AXIS)
    ax.tick_params(colors=COL_AXIS)
    ax.set_facecolor('none')
    n_drought = dec_df['drought_10yr'].sum()
    pct = 100 * n_drought / len(dec_df)
    ax.text(0.05, 0.90, f"{pct:.1f}%", transform=ax.transAxes, fontsize=28, fontweight='bold',
            family=FONT_FAMILY, color=COL_AXIS, ha='left', va='top')
    ax.text(0.05, 0.80, 'of the decade', transform=ax.transAxes, fontsize=18,
            family=FONT_FAMILY, color=COL_AXIS, ha='left', va='top')
    ax.text(0.05, 0.72, 'the river segment was', transform=ax.transAxes, fontsize=18,
            family=FONT_FAMILY, color=COL_AXIS, ha='left', va='top')
    ax.text(0.05, 0.64, 'modelled under drought', transform=ax.transAxes, fontsize=18,
            family=FONT_FAMILY, color=COL_AXIS, ha='left', va='top')
    ax.legend(loc='upper right', frameon=True, framealpha=0.9, facecolor='#cccccc',
              edgecolor='none', fontsize=FS_LEGEND, labelcolor='black')
    return ax

def _create_total_inset(ax, dec_df, decade):
    count_q10 = sum((dec_df['drought_10yr']) & (~dec_df['drought_50yr']))
    count_q50 = sum(dec_df['drought_50yr'])
    counts = [count_q10, count_q50]
    y_pos = np.arange(2)
    width = 0.5
    bars = ax.barh(y_pos, counts, height=width, color=[COL_10YR, COL_50YR],
                   alpha=FILL_ALPHA, edgecolor=[COL_10YR, COL_50YR], linewidth=0.8)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(['Q10 only', 'Q50'], fontsize=FS_AXTEXT, family=FONT_FAMILY, color=COL_AXIS)
    max_c = max(counts) if max(counts) > 0 else 1
    for bar, count in zip(bars, counts):
        ax.text(count + max_c * 0.05, bar.get_y() + bar.get_height()/2, str(int(count)),
                va='center', fontsize=FS_TITLE_MAIN, family=FONT_FAMILY, color=COL_AXIS, fontweight='bold')
    ax.set_xlabel('event count', fontsize=FS_AXTITLE, color=COL_AXIS)
    ax.set_title(f'Total drought events\n({min(decade)}-{max(decade)})', fontsize=FS_TITLE,
                 family=FONT_TITLE, color=COL_AXIS, pad=10)
    ax.tick_params(colors=COL_AXIS)
    ax.set_facecolor('none')
    for spine in ax.spines.values():
        spine.set_color(COL_AXIS)
    return ax

def _create_monthly_inset(ax, dec_df, decade):
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
    ax.bar(x - width/2, counts_q10, width, color=COL_10YR, alpha=FILL_ALPHA,
           edgecolor=COL_10YR, linewidth=0.8)
    ax.bar(x + width/2, counts_q50, width, color=COL_50YR, alpha=FILL_ALPHA,
           edgecolor=COL_50YR, linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(months_initial, fontsize=FS_AXTEXT, family=FONT_FAMILY, color=COL_AXIS)
    ax.set_ylabel('event count', fontsize=FS_AXTITLE, color=COL_AXIS)
    ax.set_title(f'Drought events across the months\n({min(decade)}-{max(decade)})',
                 fontsize=FS_TITLE, family=FONT_TITLE, color=COL_AXIS, pad=10)
    ax.tick_params(colors=COL_AXIS)
    ax.set_facecolor('none')
    for spine in ax.spines.values():
        spine.set_color(COL_AXIS)
    return ax

def create_drought_hydrograph(gauge_id, decade_year=None, persistence=1):
    """Main function to create the drought hydrograph plot.
    
    Args:
        gauge_id: Zero-padded 10-digit gauge ID (e.g., '0006112080')
        decade_year: Integer representing the decade start (e.g., 1960 for 1960-1969)
                   If None, uses the first available decade from the data.
        persistence: Minimum consecutive months below threshold (default=1)
    
    Returns:
        matplotlib.figure.Figure with transparent background
    """
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
    
    # Create figure with gridspec (slightly taller for better spacing)
    fig = plt.figure(figsize=(12, 12), facecolor='none')
    # Set layout engine to 'none' to prevent Shiny from changing it to 'tight'
    fig.set_layout_engine(layout='none')
    
    # Adjusted height_ratios and width_ratios for better alignment
    # Removed spacer rows - insets are now directly below title
    # Reduced wspace to minimize gap between inset plots
    gs = gridspec.GridSpec(4, 3, figure=fig, height_ratios=[0.4, 0.7, 1.0, 0.05],
                           width_ratios=[0.9, 0.4, 1.2], hspace=0.3, wspace=0.15)
    
    # Title
    ax_title = fig.add_subplot(gs[0, :])
    ax_title.axis('off')
    station_name = gauge_id
    ax_title.text(0.02, 0.95, f"Monthly hydrological drought ({decade_year}s, persistence = {persistence} months)",
                  fontsize=FS_TITLE, fontweight='bold', family=FONT_FAMILY, color=COL_AXIS,
                  ha='left', va='top')
    ax_title.text(0.02, 0.65, f"River at station {station_name} ({gauge_id})",
                  fontsize=FS_TITLE, family=FONT_TITLE, color=COL_AXIS,
                  ha='left', va='top')
    
    # Insets - row 1 now directly below title
    ax_total = fig.add_subplot(gs[1, 0])
    ax_month = fig.add_subplot(gs[1, 2])
    _create_total_inset(ax_total, dec_df, decade)
    _create_monthly_inset(ax_month, dec_df, decade)
    
    # Main plot - row 2
    ax_main = fig.add_subplot(gs[2, :])
    _create_main_plot(ax_main, dec_df, s10_x, s10_y, s50_x, s50_y, hydro_x_smooth, hydro_y_smooth, decade)

    return fig

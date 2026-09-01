"""Scratch: emulate shiny's matplotlib sizing on the eval plots to find the
empty-image failure mode. Duplicates the plot code from app.py (eval section)."""
import sys
import io
import warnings

sys.path.insert(0, "/home/chris/projects/IRISCC/iriscc_demostrator_drought_risk/src/shiny_app")

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.font_manager import FontProperties
import numpy as np
import pandas as pd

from shared import eval_station_meta, EVAL_VARIABLES, get_eval_series
from theme_config import get_theme_config

tc = get_theme_config("dark")
c = tc.colors

print("stations:", 0 if eval_station_meta is None else len(eval_station_meta))
print("default station (iloc[0]):", eval_station_meta["station_id"].iloc[0])

# ---- data summary -----------------------------------------------------------
print("\n--- per-station overlap summary ---")
for var in ["sm", "gpp"]:
    lines = []
    for sid in eval_station_meta["station_id"]:
        i, s = get_eval_series(sid, var)
        ni = 0 if i is None else len(i)
        ns = 0 if s is None else len(s)
        lines.append((min(ni, ns), sid, ni, ns))
    lines.sort()
    for n, sid, ni, ns in lines[:12]:
        i, s = get_eval_series(sid, var)
        rng = f"{i.index.min():%Y-%m}..{i.index.max():%Y-%m}" if i is not None and len(i) else "-"
        print(f"  {var:3s} {sid:8s} icos={ni:5d} clm5={ns:5d} overlap={min(ni,ns):5d} {rng}")
    print(f"  {var}: stations with overlap 0: {sum(1 for n, *_ in lines if n == 0)}, "
          f"<31 days: {sum(1 for n, *_ in lines if 0 < n < 31)}, >=31: {sum(1 for n, *_ in lines if n >= 31)}")


# ---- figure builders (copied from app.py eval section) ----------------------
def _message_fig(message):
    fig, ax = plt.subplots(figsize=(4, 1.5))
    fig.patch.set_facecolor(c["background"])
    ax.set_facecolor(c["background"])
    ax.text(0.5, 0.5, message, ha="center", va="center", color=c["text"],
            fontsize=11, wrap=True, transform=ax.transAxes)
    ax.axis("off")
    return fig


def _eval_monthly_stats(icos, clm5):
    if icos is None or clm5 is None:
        return None
    joined = pd.concat({"obs": icos.resample("ME").mean(), "sim": clm5.resample("ME").mean()}, axis=1).dropna()
    if len(joined) < 3:
        return None
    o = joined["obs"].to_numpy(dtype=float)
    s = joined["sim"].to_numpy(dtype=float)
    return {"r": float(np.corrcoef(o, s)[0, 1]), "rmse": float(np.sqrt(np.mean((s - o) ** 2))),
            "n": int(len(joined)), "obs": joined["obs"], "sim": joined["sim"]}


def build_ts(sid, var):
    spec = EVAL_VARIABLES[var]
    icos, clm5 = get_eval_series(sid, var)
    if icos is None or clm5 is None or len(icos) < 2:
        return _message_fig(f"No {spec['label']} data available for {sid}.")
    icos_mo = icos.resample("ME").mean().dropna()
    clm5_mo = clm5.resample("ME").mean().dropna()
    stats = _eval_monthly_stats(icos, clm5)
    fig, ax = plt.subplots(figsize=(10, 3.8))
    fig.patch.set_facecolor(c["background"])
    ax.set_facecolor(c["background"])
    ax.plot(icos.index, icos.values, color=c["primary"], linewidth=0.5, alpha=0.4, label="ICOS (daily)")
    ax.plot(clm5.index, clm5.values, color="#bb86fc", linewidth=0.5, alpha=0.4, label="CLM5 (daily)")
    ax.plot(icos_mo.index, icos_mo.values, color=c["primary"], linewidth=1.8, label="ICOS (monthly mean)")
    ax.plot(clm5_mo.index, clm5_mo.values, color="#bb86fc", linewidth=1.8, label="CLM5 (monthly mean)")
    ax.set_title(f"{sid} - {spec['label']}", color=c["text"], fontsize=12, pad=8,
                 family=tc.get_font_family("heading"))
    ax.set_ylabel(spec["unit"], color=c["text"])
    ax.set_xlabel("Date", color=c["text"])
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(colors=c["text"])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(True, color=c["border"], alpha=0.3, linewidth=0.5)
    ax.legend(facecolor=c["background"], edgecolor=c["border"], labelcolor=c["text"],
              prop=FontProperties(family=tc.get_font_family("body"), size=9), framealpha=0.9)
    if stats is not None:
        ax.text(0.99, 0.03, f"r = {stats['r']:.2f}  RMSE = {stats['rmse']:.3f}", transform=ax.transAxes,
                ha="right", va="bottom", color=c["text"], fontsize=9)
    fig.tight_layout = lambda *a, **kw: None
    return fig


def build_xy(sid, var):
    spec = EVAL_VARIABLES[var]
    icos, clm5 = get_eval_series(sid, var)
    stats = _eval_monthly_stats(icos, clm5)
    if icos is None or clm5 is None or len(icos) < 2:
        return _message_fig(f"No {spec['label']} data available for {sid}.")
    if stats is None:
        return _message_fig(f"Overlap shorter than 3 months for {sid} - too few monthly means.")
    o, s = stats["obs"], stats["sim"]
    fig, ax = plt.subplots(figsize=(5.5, 3.8))
    fig.patch.set_facecolor(c["background"])
    ax.set_facecolor(c["background"])
    ax.scatter(o, s, s=14, color=c["info"], alpha=0.6, edgecolors="none", label="monthly means")
    lo, hi = min(o.min(), s.min()), max(o.max(), s.max())
    ax.plot([lo, hi], [lo, hi], color=c["text"], linestyle="--", linewidth=1, alpha=0.7, label="1:1")
    ax.set_title(f"{spec['label']}: CLM5 vs ICOS", color=c["text"], fontsize=12)
    ax.set_xlabel(f"ICOS ({spec['unit']})", color=c["text"])
    ax.set_ylabel(f"CLM5 ({spec['unit']})", color=c["text"])
    ax.tick_params(colors=c["text"])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(True, color=c["border"], alpha=0.3, linewidth=0.5)
    ax.legend(facecolor=c["background"], edgecolor=c["border"], labelcolor=c["text"],
              prop=FontProperties(family=tc.get_font_family("body"), size=9), framealpha=0.9)
    ax.text(0.99, 0.03, f"r = {stats['r']:.2f}  RMSE = {stats['rmse']:.3f}", transform=ax.transAxes,
            ha="right", va="bottom", color=c["text"], fontsize=9)
    fig.tight_layout = lambda *a, **kw: None
    return fig


def clamp_size(fig, min_inch=1.0):
    orig = fig.set_size_inches

    def _clamped(w, h, **kw):
        orig(max(w, min_inch), max(h, min_inch), **kw)

    fig.set_size_inches = _clamped
    return fig


def shiny_save(fig, w_px, h_px, pixelratio=1.0):
    """Replicates shiny's try_render_matplotlib sizing + save."""
    ppi_out = fig.get_dpi()
    fig.set_size_inches(w_px / ppi_out, h_px / ppi_out)
    fig.set_dpi(ppi_out * pixelratio)
    if not fig.get_layout_engine():
        fig.set_layout_engine(layout="tight")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=ppi_out * pixelratio)
    buf.seek(0)
    im = mpimg.imread(buf)
    shape = im.shape
    plt.close(fig)
    return shape


def try_case(label, fig, w, h, do_clamp=False):
    if do_clamp:
        clamp_size(fig)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        try:
            shape = shiny_save(fig, w, h)
            print(f"  OK   {label:38s} ({w}x{h}px) -> PNG {shape[1]}x{shape[0]}")
        except Exception as e:
            plt.close(fig)
            print(f"  FAIL {label:38s} ({w}x{h}px) -> {type(e).__name__}: {e}")


# ---- normal sizes: all stations/vars ----------------------------------------
print("\n--- normal container sizes (all stations) ---")
bad = 0
for var in ["sm", "gpp"]:
    for sid in eval_station_meta["station_id"]:
        f = build_ts(sid, var)
        r = try_case(f"ts {sid} {var}", f, 700, 430)
        f = build_xy(sid, var)
        try_case(f"xy {sid} {var}", f, 450, 430)
print("done")

# ---- zero width: the hidden-tab case ----------------------------------------
print("\n--- zero-width container (hidden tab) ---")
for sid, var in [("FI-Lom", "sm"), ("BE-Bra", "sm"), ("FI-Lom", "gpp"), ("DE-Fri", "gpp")]:
    f = build_ts(sid, var)
    try_case(f"ts {sid} {var}", f, 0, 430)
    f = build_ts(sid, var)
    try_case(f"ts {sid} {var} CLAMPED", f, 0, 430, do_clamp=True)

# ---- degenerate data check: constant series ---------------------------------
print("\n--- constant/degenerate value check ---")
for var in ["sm", "gpp"]:
    for sid in eval_station_meta["station_id"]:
        i, s = get_eval_series(sid, var)
        for nm, ser in (("icos", i), ("clm5", s)):
            if ser is None or len(ser) < 2:
                continue
            v = ser.to_numpy(dtype=float)
            if v.max() - v.min() == 0:
                print(f"  CONSTANT: {sid} {var} {nm} (n={len(ser)})")
print("done")

#!/usr/bin/env python3
"""Compute decadal drought statistics from a drought-index NetCDF file.

Python port of ``decadal_statistics.sh``, generalised to give *consistent*
results across datasets with different temporal sampling (daily, n-daily,
monthly). For each decade it writes four fields, one file each. The threshold
(and, optionally, the temporal-aggregation label) are encoded in the file name
so several runs can coexist (and be selected from in the app):

    <prefix>[_<agg>]_<thresh>_<decade>_mean.nc      decadal mean of the index
    <prefix>[_<agg>]_<thresh>_<decade>_dfreq.nc     fraction of time in drought
    <prefix>[_<agg>]_<thresh>_<decade>_min.nc       most negative index reached
    <prefix>[_<agg>]_<thresh>_<decade>_maxspell.nc  longest dry spell (DAYS)

The aggregation label (``--agg``, e.g. ``92D``) is optional: pass it for
indices computed over a temporal window (e.g. a 92-day SPI), and omit it for
variables with no aggregation (e.g. SMI). ``mean`` and ``min`` do not depend on
the threshold, so they are identical across threshold runs (they still carry
the tag for a uniform, self-contained set of files per run).

The mean, drought frequency and spell length are weighted by each timestep's
real duration in days, so the numbers are directly comparable no matter how
the data is sampled:

    daily     -> 1 day per step
    8-daily   -> 8 days per step
    monthly   -> 28..31 days per step (derived from the calendar)

For equally-spaced data this weighting is a no-op, so results stay identical to
the original shell script. Use ``--step-days N`` to force a fixed step length
instead of deriving it from the time axis.

Ocean/missing cells are kept masked (NaN) in every output, derived from the
input's valid footprint. This avoids the CDO ``consecsum`` pitfall where the
land-sea mask was lost and the ocean ended up drawn as 0.

Requires: xarray, numpy (cftime comes with netCDF4). Example:

    python decadal_statistics.py \\
        --ifile /path/SXI_92D.nc --odir /path/decadal/ \\
        --var SXI_P --prefix SXI_P --agg 92D \\
        --dec1 1960 --dec2 2010 --thresh -1
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xarray as xr


def _to_days(times) -> np.ndarray:
    """Convert a time coordinate (datetime64 or cftime) to a float day number."""
    arr = np.asarray(times)
    if np.issubdtype(arr.dtype, np.datetime64):
        return arr.astype("datetime64[s]").astype("float64") / 86400.0
    import cftime  # bundled with netCDF4; handles noleap/360_day/etc.

    cal = getattr(arr.flat[0], "calendar", "standard")
    return np.asarray(
        cftime.date2num(arr, "days since 1970-01-01", calendar=cal), dtype="float64"
    )


def timestep_weights(ds: xr.Dataset, tdim: str, step_days) -> xr.DataArray:
    """Days each timestep represents, as a DataArray aligned to the time axis.

    Priority: explicit ``--step-days`` > CF time bounds (exact for any
    sampling) > forward difference of the timestamps (the very last step of the
    file reuses the previous gap).
    """
    times = ds[tdim].values
    n = len(times)
    if step_days is not None:
        w = np.full(n, float(step_days))
    else:
        bounds = ds[tdim].attrs.get("bounds")
        if bounds and bounds in ds.variables:
            b = ds[bounds].values
            w = _to_days(b[..., 1]) - _to_days(b[..., 0])
        elif n < 2:
            w = np.ones(n)
        else:
            diffs = np.diff(_to_days(times))
            w = np.append(diffs, diffs[-1])
    return xr.DataArray(w, dims=[tdim], coords={tdim: ds[tdim]})


def longest_spell_days(mask: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Longest run of consecutive True along axis 0, summed in day-weights.

    Mirrors CDO ``timmax -consecsum``: a running sum that accumulates each
    in-drought step's day-weight and resets to zero whenever drought ends.
    """
    running = np.zeros(mask.shape[1:], dtype="float64")
    best = np.zeros_like(running)
    for t in range(mask.shape[0]):
        running = np.where(mask[t], running + weights[t], 0.0)
        best = np.maximum(best, running)
    return best


def write_field(field: xr.DataArray, var: str, when, units: str, path: Path) -> None:
    """Write a 2-D field as a length-1 time NetCDF, matching the CDO layout."""
    out = field.rename(var).expand_dims({"time": [when]})
    out.attrs["units"] = units
    out.to_netcdf(path, encoding={var: {"zlib": True, "complevel": 4}})


def process(args: argparse.Namespace) -> None:
    ds = xr.open_dataset(args.ifile)
    da = ds[args.var]
    tdim = args.time_dim

    odir = Path(args.odir)
    odir.mkdir(parents=True, exist_ok=True)

    # Weights over the full axis, so a decade's last step still sees the next
    # step (only the file's final step is ever approximated).
    weights_full = timestep_weights(ds, tdim, args.step_days)

    for y0 in range(args.dec1, args.dec2 + 1, args.length):
        y1 = y0 + args.length - 1
        dec = da.sel({tdim: slice(str(y0), str(y1))})
        if dec.sizes.get(tdim, 0) == 0:
            print(f"Skipping {y0}-{y1}: no timesteps")
            continue

        print(f"Processing {y0}-{y1}")
        dec = dec.load()
        weight = weights_full.sel({tdim: slice(str(y0), str(y1))})
        w = weight.values
        mask = dec <= args.thresh  # 1 where in drought (NaN -> False)
        valid = dec.notnull().any(tdim)  # land-sea mask: keep ocean as NaN
        when = dec[tdim].values[0]
        units = dec.attrs.get("units", "")

        # Filename: <prefix>[_<agg>]_<thresh>_<decade>_<stat>.nc
        # The aggregation label (e.g. 92D) is optional - omitted for variables
        # without a temporal aggregation (e.g. SMI). The thresh tag lets several
        # threshold runs coexist. A trailing '_' on the prefix is tolerated.
        parts = [args.prefix.rstrip("_")]
        if args.agg:
            parts.append(args.agg)
        parts += [f"{args.thresh:g}", str(y0)]
        stem = "_".join(parts)

        print("  - decadal mean")
        mean = dec.weighted(weight).mean(tdim, skipna=True)
        write_field(mean.where(valid), args.var, when, units, odir / f"{stem}_mean.nc")

        print("  - relative drought time")
        dfreq = (mask * weight).sum(tdim) / weight.sum()
        write_field(dfreq.where(valid), args.var, when, "1", odir / f"{stem}_dfreq.nc")

        print("  - minimum drought index")
        write_field(dec.min(tdim).where(valid), args.var, when, units, odir / f"{stem}_min.nc")

        print("  - longest drought spell (days)")
        mask_t = mask.transpose(tdim, ...)
        spell = xr.DataArray(
            longest_spell_days(mask_t.values, w),
            dims=mask_t.dims[1:],
            coords={c: dec.coords[c] for c in dec.coords if tdim not in dec[c].dims},
        )
        write_field(spell.where(valid), args.var, when, "days", odir / f"{stem}_maxspell.nc")

    ds.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ifile", required=True, help="input drought-index NetCDF")
    p.add_argument("--odir", required=True, help="output directory")
    p.add_argument("--var", default="SXI_P", help="variable name (default: SXI_P)")
    p.add_argument("--prefix", default="SXI_P", help="output filename prefix")
    p.add_argument(
        "--agg", default=None,
        help="optional temporal-aggregation label placed in the file name "
        "(e.g. 92D); omit for non-aggregated variables such as SMI",
    )
    p.add_argument("--time-dim", default="time", help="name of the time dimension")
    p.add_argument("--dec1", type=int, default=1960, help="first decade start year")
    p.add_argument("--dec2", type=int, default=2010, help="last decade start year")
    p.add_argument("--length", type=int, default=10, help="decade length in years")
    p.add_argument("--thresh", type=float, default=-1.0, help="drought threshold")
    p.add_argument(
        "--step-days", type=float, default=None,
        help="fixed days per timestep; omit to derive from the time axis "
        "(1 for daily, 8 for 8-daily, ~30 for monthly)",
    )
    process(p.parse_args())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Per-decade largest-drought-event maps from event properties + 3-D event masks.

For every decade this selects the largest drought event — maximum
``integrated_area`` (km² days) among the events in the properties file — and
writes one NetCDF file with two 2-D fields (length-1 time axis, set to the
event's start date):

    event_mask      1 where the pixel is part of the event, 0 elsewhere,
                    NaN where the drought index is not defined
    event_duration  number of timesteps the pixel was part of the event,
                    in days (timesteps are counted with the 8-d day weight),
                    NaN outside the event

The mask file's lat/lon coordinates are carried into the output files.

Decade assignment: an event belongs to the decade that contains the majority
of its duration (calendar-day overlap of [start_date, end_date] with the
decade; exact ties go to the earlier decade). The whole event — including the
part lying in the adjacent decade — is written to the selected decade's file.

File resolution is driven by ``events.yaml``:

    masks dir / cluster_<project> / <t_agg>_<detection-params>_<suffix>.nc
        (variable <drought_var>; a 3-D label field: event ID per timestep
         per pixel, -1/NaN where not in an event)
    props dir / <project>_event_properties_<drought_var>_<t_agg>.xlsx

The mask file carries no time coordinate. The time axis is reconstructed as
8-daily timesteps that restart at January 1st of each year, the first year
starting at ``--start`` (e.g. 1960-04-06):

    1960: 04-06, 04-14, ..., 12-28      34 steps
    1961: 01-01, 01-09, ..., 12-27      46 steps (46 in leap years too)
    ...
    2024: 01-01, 01-09, ..., 12-26      46 steps

Its length must equal the mask file's time size (checked at startup).

Example:

    python decadal_events.py --config events.yaml --dec1 1960 --dec2 2020
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import yaml


def build_time_axis(start: pd.Timestamp, end: pd.Timestamp, step_days: int) -> pd.DatetimeIndex:
    """8-daily timesteps per year, each year starting at January 1st.

    The first year starts at ``start`` instead (e.g. the model's start date).
    """
    parts = []
    for year in range(start.year, end.year + 1):
        y0 = max(start, pd.Timestamp(year, 1, 1))
        y1 = pd.Timestamp(year, 12, 31)
        parts.append(pd.date_range(y0, y1, freq=f"{step_days}D"))
    return pd.DatetimeIndex(np.concatenate([p.to_numpy() for p in parts]))


def resolve_mask_file(mdir: Path, project: str, t_agg: str, suffix: str) -> Path:
    """<masks dir>/cluster_<project>/<t_agg>_<params>_<suffix>.nc (exactly one)."""
    cdir = mdir / f"cluster_{project}"
    cands = sorted(cdir.glob(f"{t_agg}_*_{suffix}.nc"))
    if len(cands) != 1:
        raise SystemExit(f"Expected exactly one mask file in {cdir} matching "
                         f"{t_agg}_*_{suffix}.nc, found: {[str(c) for c in cands]}")
    return cands[0]


def resolve_props_file(pdir: Path, project: str, drought_var: str, t_agg: str) -> Path:
    """<props dir>/<project>_event_properties_<drought_var>_<t_agg>.xlsx."""
    return pdir / f"{project}_event_properties_{drought_var}_{t_agg}.xlsx"


def load_events(props_path: Path) -> pd.DataFrame:
    """Read the event-properties table (header row, then a units + blank row)."""
    if not props_path.exists():
        raise SystemExit(f"Props file not found: {props_path}")
    df = pd.read_excel(props_path, skiprows=[1, 2])
    if "Property" in df.columns:
        df = df.drop(columns=["Property"])
    df["ID"] = pd.to_numeric(df["ID"], errors="coerce")
    df = df[df["ID"].notna()].copy()
    df["ID"] = df["ID"].astype(int)
    df["start"] = pd.to_datetime(df["start_date"])
    df["end"] = pd.to_datetime(df["end_date"])
    df["duration"] = pd.to_numeric(df["duration"])
    df["integrated_area"] = pd.to_numeric(df["integrated_area"])
    if df.empty:
        raise SystemExit(f"No events with a valid ID in {props_path}")
    return df.reset_index(drop=True)


def decade_overlap_days(start: pd.Timestamp, end: pd.Timestamp, d0: int) -> int:
    """Calendar days of [start, end] (inclusive) falling inside decade d0..d0+9."""
    ds, de = pd.Timestamp(d0, 1, 1), pd.Timestamp(d0 + 9, 12, 31)
    return max((min(end, de) - max(start, ds)).days + 1, 0)


def assign_decade(start: pd.Timestamp, end: pd.Timestamp, decades: list[int]) -> int | None:
    """Decade holding the majority of the event's duration; None if no overlap.

    Decades are scanned ascending with a strict comparison, so an exact
    overlap tie goes to the earlier decade.
    """
    best_d, best_ov = None, 0
    for d0 in decades:
        ov = decade_overlap_days(start, end, d0)
        if ov > best_ov:
            best_d, best_ov = d0, ov
    return best_d


def write_decade_file(out_path: Path, member: np.ndarray, n_hit: np.ndarray,
                      valid: np.ndarray, step_days: int, when: pd.Timestamp,
                      ev: pd.Series, mask_file: Path, props_file: Path,
                      drought_var: str, t_agg: str, project: str,
                      grid_coords: dict) -> None:
    """Write <drought_var>_<t_agg>_<decade>_event.nc for one selected event."""
    mask2d = np.where(valid, member, np.nan).astype("float32")
    dur2d = np.where(valid & member, n_hit * step_days, np.nan).astype("float32")
    out = xr.Dataset(
        {
            "event_mask": (("time", "lat", "lon"),
                           mask2d[np.newaxis, ...],
                           {"units": "",
                            "description": "1 where the pixel is part of the decade's "
                                            "largest drought event, 0 elsewhere, NaN "
                                            "where the drought index is not defined"}),
            # NB: no units="days" here - CF time units make xarray decode the
            # field as timedelta64 on open. Unit is documented instead.
            "event_duration": (("time", "lat", "lon"),
                               dur2d[np.newaxis, ...],
                               {"description": f"timesteps ({step_days} d each) the pixel "
                                                "was part of the event, in days; NaN "
                                                "outside the event"}),
        },
        coords={"time": xr.DataArray([when], dims="time"), **grid_coords},
        attrs={
            "title": f"Decade {when.year // 10 * 10} largest drought event "
                     f"({drought_var}, {t_agg}, {project})",
            "event_id": int(ev["ID"]),
            "start_date": str(ev["start"].date()),
            "end_date": str(ev["end"].date()),
            "duration_days": int(ev["duration"]),
            "integrated_area_km2_days": float(ev["integrated_area"]),
            "maximum_area_km2": float(ev["maximum_area"]),
            "decade": when.year // 10 * 10,
            "drought_var": drought_var,
            "t_agg": t_agg,
            "project": project,
            "selection": "largest integrated_area among events whose majority of "
                         "duration lies in this decade; the full event (incl. the "
                         "part in the adjacent decade) is written here",
            "source_props": str(props_file),
            "source_mask": str(mask_file),
        },
    )
    out.to_netcdf(out_path, encoding={v: {"zlib": True, "complevel": 4} for v in out.data_vars})


def process(args: argparse.Namespace) -> None:
    cfg = yaml.safe_load(Path(args.config).read_text())
    drought_var = cfg["drought_var"]
    t_agg = cfg["t_agg"]
    project = cfg["project"]

    mask_file = resolve_mask_file(Path(cfg["masks"]["dir"]), project, t_agg, cfg["masks"]["suffix"])
    props_file = resolve_props_file(Path(cfg["props"]["dir"]), project, drought_var, t_agg)
    print(f"mask : {mask_file}  (variable {drought_var})")
    print(f"props: {props_file}")

    axis = build_time_axis(pd.Timestamp(args.start), pd.Timestamp(args.end), args.step_days)
    ds = xr.open_dataset(mask_file)
    if drought_var not in ds:
        raise SystemExit(f"Variable {drought_var} not in {mask_file}; "
                         f"available: {list(ds.data_vars)}")
    lab = ds[drought_var]

    # Keep the mask file's grid coordinates in the output files, relabelled
    # to the "lat"/"lon" dim names the fields are written with, so each
    # per-decade file is self-describing.
    grid_coords: dict = {}
    for _name, _coord in lab.coords.items():
        if _name == "time":
            continue
        _lname = _name.lower()
        if "lat" in _lname or _lname.startswith("y"):
            grid_coords["lat"] = _coord
        elif "lon" in _lname or _lname.startswith("x"):
            grid_coords["lon"] = _coord
    if len(axis) != lab.sizes["time"]:
        raise SystemExit(f"Reconstructed time axis has {len(axis)} timesteps "
                         f"({args.start}..{args.end}, {args.step_days}D) but the mask file "
                         f"has {lab.sizes['time']}; check --start/--end/--step-days")
    print(f"time axis: {len(axis)} timesteps, {axis[0].date()} .. {axis[-1].date()}")

    events = load_events(props_file)
    print(f"events: {len(events)} (ID {events['ID'].min()}..{events['ID'].max()})")

    # Validate that event dates sit on the reconstructed axis.
    pos = axis.get_indexer(pd.DatetimeIndex(list(events["start"]) + list(events["end"])))
    bad = events[(pos[: len(events)] == -1) | (pos[len(events):] == -1)]
    if not bad.empty:
        raise SystemExit(f"Event dates not on the reconstructed time axis "
                         f"(first IDs: {bad['ID'].head().tolist()}); check "
                         f"--start/--end/--step-days")

    decades = list(range(args.dec1, args.dec2 + 1, args.length))
    # Largest event (by integrated area) per decade, by duration-majority.
    selected: dict[int, pd.Series] = {}
    n_unassigned = 0
    for _, ev in events.iterrows():
        d0 = assign_decade(ev["start"], ev["end"], decades)
        if d0 is None:
            n_unassigned += 1
            continue
        cur = selected.get(d0)
        if cur is None or ev["integrated_area"] > cur["integrated_area"]:
            selected[d0] = ev
    if n_unassigned:
        print(f"note: {n_unassigned} events fall outside decades {decades[0]}..{decades[-1] + 9}")

    odir = Path(args.odir) if args.odir else Path(cfg["masks"]["dir"]) / f"cluster_{project}" / "decadal"
    odir.mkdir(parents=True, exist_ok=True)

    for d0 in decades:
        ev = selected.get(d0)
        if ev is None:
            print(f"decade {d0}: no assigned event, skipping")
            continue
        i0, i1 = axis.get_indexer(pd.DatetimeIndex([ev["start"], ev["end"]]))
        seg = lab.isel(time=slice(i0, i1 + 1)).load()
        hit = seg == ev["ID"]
        member = hit.any(dim="time").values
        n_hit = hit.sum(dim="time").values
        valid = seg.notnull().any(dim="time").values

        out_path = odir / f"{drought_var}_{t_agg}_{d0}_event.nc"
        print(f"decade {d0}: event {ev['ID']}  {ev['start'].date()}..{ev['end'].date()} "
              f"({ev['duration']:.0f} d, integrated area {ev['integrated_area']:.0f} km² d) "
              f"-> {out_path.name}")
        if not args.dry_run:
            write_decade_file(out_path, member, n_hit, valid, args.step_days,
                              ev["start"], ev, mask_file, props_file,
                              drought_var, t_agg, project, grid_coords)
    ds.close()
    if not args.dry_run:
        print(f"wrote {len([d for d in decades if d in selected])} file(s) to {odir}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=str(Path(__file__).parent / "events.yaml"),
                   help="events.yaml with drought_var/impact_var/t_agg/project/masks/props")
    p.add_argument("--dec1", type=int, default=1960, help="first decade start year")
    p.add_argument("--dec2", type=int, default=2020, help="last decade start year")
    p.add_argument("--length", type=int, default=10, help="decade length in years")
    p.add_argument("--start", default="1960-04-06",
                   help="first timestep of the data (first year of the time axis)")
    p.add_argument("--end", default="2024-12-26",
                   help="last timestep of the data (last year of the time axis)")
    p.add_argument("--step-days", type=int, default=8, help="timestep length in days")
    p.add_argument("--odir", default=None,
                   help="output directory (default: <masks dir>/cluster_<project>/decadal)")
    p.add_argument("--dry-run", action="store_true", help="resolve and select only, write nothing")
    process(p.parse_args())


if __name__ == "__main__":
    main()

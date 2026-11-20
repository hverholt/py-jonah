"""Load ADCP telemetry and calculate values shared by dashboard plots."""
import datetime as dt
import glob
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
import time

import numpy as np
import xarray as xr

from adcp_toolbox import telemetry2netcdf

from . import config as cfg


# ADCP data loading
def get_recent_files(hours):
    cutoff = time.time() - hours * 3600

    files = glob.glob(
        os.path.join(cfg.INPUT_DIR, "Terminal_*.txt")
    )

    files = [
        f for f in files
        if os.path.isfile(f) and os.path.getmtime(f) >= cutoff
    ]

    if not files:
        raise FileNotFoundError(
            f"No telemetry files modified in the last {hours} hours."
        )

    # Filenames should contain timestamps, so this sorts them chronologically
    # Correct sorting is not absolutely critical though as data is eventually sorted by time
    return sorted(files)


def load_data():
    # Get all recent telemetry files (within specified interval + 1 hour buffer)
    source_files = get_recent_files(hours=cfg.HISTORY_HOURS + 1)

    txt = Path(cfg.TXT_FILE)
    nc = Path(cfg.NC_FILE)
    for path in (txt, nc):
        path.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(dir=txt.parent, delete=False) as temp:
        snapshot = Path(temp.name)
    with NamedTemporaryFile(dir=nc.parent, suffix=".nc", delete=False) as temp:
        candidate = Path(temp.name)
    try:
        with snapshot.open("wb") as dest:
            for source_file in source_files:
                with open(source_file, "rb") as src:
                    for line in src:
                        if line.endswith((b"\r", b"\n")):
                            dest.write(line)
                        elif source_file != source_files[-1]:
                            dest.write(line + b"\n")
                        # Re-read the active file's unfinished tail next refresh.
        telemetry2netcdf.telemetry_to_netcdf(snapshot, candidate, 102, filter_errors=True)
        ds = read_dashboard_dataset(candidate)
        os.replace(snapshot, txt)
        os.replace(candidate, nc)
    finally:
        snapshot.unlink(missing_ok=True)
        candidate.unlink(missing_ok=True)

    filename = (
        f"{len(source_files)} files "
        f"(latest: {os.path.basename(source_files[-1])})"
    )

    return ds, filename



def read_dashboard_dataset(path):
    """Load and close the file before Windows replaces it."""
    with xr.open_dataset(path) as source:
        if not source.sizes.get("TIME") or not source.sizes.get("CN"):
            raise ValueError("No dashboard observations in telemetry.")
        for name in ("VN", "VE", "CP", "P"):
            if name not in source:
                raise ValueError(f"Missing dashboard variable {name}")
        return source.load()


# Velocity extraction
def extract_velocity(ds, target_depths=cfg.TARGET_DEPTHS,
                     averaging_width=cfg.AVERAGING_WIDTH, min_depth=cfg.MIN_DEPTH):
    """Depth-average horizontal velocities around selected depths below the surface."""

    vn_da = ds["VN"].transpose("TIME", "CN")
    ve_da = ds["VE"].transpose("TIME", "CN")

    vn = np.asarray(vn_da.values, dtype=float)
    ve = np.asarray(ve_da.values, dtype=float)

    pressure = np.asarray(ds["P"].values, dtype=float).reshape(-1)

    cp_da = xr.broadcast(vn_da, ds["CP"])[1]
    cp = np.asarray(
        cp_da.transpose("TIME", "CN").values,
        dtype=float,
    )

    water_depth = pressure / cfg.DBAR_PER_METER
    depth = water_depth[:, None] - cp

    targets = np.asarray(target_depths, dtype=float)
    n_times = vn.shape[0]

    north = np.full((len(targets), n_times), np.nan)
    east = np.full((len(targets), n_times), np.nan)

    # Process each velocity profile
    for i in range(n_times):
        valid = (
            np.isfinite(depth[i])
            & (depth[i] >= min_depth)
            & np.isfinite(vn[i])
            & np.isfinite(ve[i])
        )

        if valid.sum() < 2:
            continue

        z = depth[i, valid]
        n = vn[i, valid]
        e = ve[i, valid]

        order = np.argsort(z)
        z = z[order]
        n = n[order]
        e = e[order]

        for j, target in enumerate(targets):
            if not (z[0] <= target <= z[-1]):
                continue

            half_width = max(0.0, min(
                averaging_width / 2,
                target - min_depth,
                target - z[0],
                z[-1] - target,
            ))

            if half_width == 0:
                north[j, i] = np.interp(target, z, n)
                east[j, i] = np.interp(target, z, e)
                continue

            lower, upper = target - half_width, target + half_width
            
            within = (z > lower) & (z < upper)
            sample_depths = np.concatenate(([lower], z[within], [upper]))
            
            dz = np.diff(sample_depths)
            
            n_values = np.interp(sample_depths, z, n)
            e_values = np.interp(sample_depths, z, e)
            north[j, i] = np.sum((n_values[:-1] + n_values[1:]) * dz) / (2 * (upper - lower))
            east[j, i] = np.sum((e_values[:-1] + e_values[1:]) * dz) / (2 * (upper - lower))

    result = {}

    for j, target in enumerate(target_depths):
        result[target] = {
            "VN": north[j],
            "VE": east[j],
            "speed": np.hypot(north[j], east[j]),
        }

    return result, water_depth



# Time and status helpers
UTC = dt.timezone.utc

def utc_now():
    return dt.datetime.now(UTC)

def format_time(value):
    return value.strftime("%H:%M:%S UTC")

def format_value(value, digits=3, unit=""):
    if not np.isfinite(value):
        return "N/A"
    return f"{value:.{digits}f}{unit}"


def get_data_status(last_data_time, now):
    """ Determine telemetry freshness from actual observation time """

    age = (now - last_data_time).total_seconds()

    if age < -60:
        return "CLOCK ERROR", cfg.RED, age

    if age < cfg.STALE_AFTER_SECONDS:
        return "LIVE", cfg.GREEN, age

    if age < cfg.OFFLINE_AFTER_SECONDS:
        return "STALE", cfg.ORANGE, age

    return "OFFLINE", cfg.RED, age



# Time-series processing
def get_time_gaps(times):
    """Mark observations separated by unusually long or nonpositive time gaps."""
    breaks = np.zeros(len(times), dtype=bool)
    if len(times) < 2:
        return breaks

    intervals = np.array([
        (b - a).total_seconds()
        for a, b in zip(times[:-1], times[1:])
    ])
    positive = intervals[intervals > 0]
    max_gap = np.median(positive) * cfg.MAX_CURRENT_GAP_FACTOR if positive.size else 0
    breaks[1:] = (intervals <= 0) | (intervals > max_gap)
    return breaks


def running_mean(values, breaks):
    """Centered running mean without averaging across missing data or time gaps."""
    values = np.asarray(values, dtype=float)
    result = np.full(values.shape, np.nan)
    window = max(1, int(cfg.RUNNING_MEAN_SAMPLES))

    before = window // 2
    after = window - before - 1

    for i in range(before, len(values) - after):
        start, stop = i - before, i + after + 1
        samples = values[start:stop]

        if np.all(np.isfinite(samples)) and not np.any(breaks[start + 1:stop]):
            result[i] = np.mean(samples)

    return result


def split_time_gaps(times, values, breaks):
    """Insert missing points so lines cannot cross gaps in observations."""
    plot_times, plot_values = [], []
    for i, (t, value) in enumerate(zip(times, values)):
        if breaks[i]:
            plot_times.append(t)
            plot_values.append(np.nan)
        plot_times.append(t)
        plot_values.append(value)
    return plot_times, plot_values


def split_direction_crossings(times, directions, breaks):
    plot_times, plot_values = [], []
    for i, (t, angle) in enumerate(zip(times, directions)):
        if i and breaks[i]:
            plot_times.append(t)
            plot_values.append(np.nan)
        elif i and np.isfinite(directions[i - 1]) and np.isfinite(angle):
            previous = directions[i - 1]
            jump = angle - previous
            if abs(jump) > cfg.DIRECTION_WRAP_THRESHOLD:
                boundary = 360.0 if jump < 0 else 0.0
                next_angle = angle + (360.0 if jump < 0 else -360.0)
                fraction = (boundary - previous) / (next_angle - previous)
                crossing_time = times[i - 1] + (t - times[i - 1]) * fraction
                plot_times.extend((crossing_time, crossing_time, crossing_time))
                plot_values.extend((boundary, np.nan, 360.0 - boundary))
        plot_times.append(t)
        plot_values.append(angle)
    return plot_times, plot_values

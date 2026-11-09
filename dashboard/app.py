"""Application startup, refresh scheduling, and coordination."""
import argparse
import datetime as dt
import time
import traceback

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from . import config as cfg
from . import data
from . import wind
from . import export
from .plots import overview


def update_dashboard(view, ds, wind_state, now):
    """Prepare observations and redraw the Overview page."""
    times = pd.to_datetime(ds["TIME"].values, utc=True)
    if len(times) == 0:
        raise ValueError("Dataset contains no timestamps.")

    # Order velocities, times and pressure chronologically
    order = np.argsort(times)
    ds = ds.isel(TIME=order)
    times = times[order]

    start_time = now - dt.timedelta(hours=cfg.HISTORY_HOURS)
    visible = np.asarray(
        (times >= pd.Timestamp(start_time))
        & (times <= pd.Timestamp(now))
    )
    last_data_time = times[-1].to_pydatetime()

    currents, water_depth = data.extract_velocity(ds)
    status = data.get_data_status(last_data_time, now)

    view["profile_dataset"] = ds
    
    overview.update_view(
        view,
        times=times.to_pydatetime(),
        currents=currents,
        water_depth=water_depth,
        now=now,
        visible=visible,
        wind_state=wind_state,
        last_data_time=last_data_time,
        status=status,
    )


def refresh(view, export_dir, cached=None):
    """Refresh wind and ADCP data; reuse the last dataset if loading fails.

    ``cached`` is either None or a (dataset, filename) tuple.
    Returns the most recently successful (dataset, filename) tuple.
    """
    now = data.utc_now()

    # Wind retrieval should not stop ADCP updates if both stations fail.
    try:
        wind_state = wind.refresh_wind(now)
    except Exception as exc:
        print(f"Wind refresh failed: {exc}")
        traceback.print_exc()
        wind_state = {"data": None, "error": str(exc), "history": pd.DataFrame()}

    try:
        ds, filename = data.load_data()
        update_dashboard(view, ds, wind_state, now)
        cached = (ds, filename)
        print(f"[{data.format_time(now)}] Dashboard refreshed: {filename}")

    except Exception as exc:
        print(f"Refresh failed: {exc}")
        traceback.print_exc()

        if cached is not None:
            try:
                update_dashboard(view, cached[0], wind_state, now)
            except Exception:
                traceback.print_exc()

        overview.show_error(view, str(exc))

    # Export failures should not interrupt acquisition or later refreshes.
    try:
        export.export_dashboard(view, export_dir)
    except Exception as exc:
        print(f"Dashboard export failed: {exc}")
        traceback.print_exc()

    return cached


def main():
    """Refresh the web dashboard indefinitely, without opening a desktop window."""
    parser = argparse.ArgumentParser(description="ADCP live current monitor")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    export_dir = cfg.EXPORT_DIR / ("live" if args.live else "preview")
    print(f"Dashboard output: {export_dir}")

    view = overview.create_view()
    view["live_mode"] = args.live
    cached = None
    try:
        while True:
            cached = refresh(view, export_dir, cached)
            if not args.live:
                print("Preview run complete.")
                break
            time.sleep(cfg.REFRESH_SECONDS)
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        for fig in view["figures"].values():
            plt.close(fig)

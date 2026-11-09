"""Dashboard data presentation with one time-series and one polar SVG.

Matplotlib owns each scientific figure. HTML/CSS independently position the
figures, measurements, status, header and footer.
"""
import datetime as dt

import matplotlib.pyplot as plt
import numpy as np

from .. import config as cfg, data
from . import polar, timeseries


def create_view():
    """Create two figures without opening a desktop window."""
    plt.rcParams.update({**cfg.PLOT_STYLE, "font.size": 12})

    # Original shared-x, vertically stacked current/current/depth layout.
    # Figure coordinates apply only *within* this one SVG.
    series_fig = plt.figure(figsize=(10.5, 8.0), facecolor=cfg.BG)
    gs = series_fig.add_gridspec(
        3, 1, left=0.092, right=0.895, top=0.945, bottom=0.092,
        height_ratios=(1, 1, 0.60), hspace=0.15,
    )
    axes = []
    for i in range(3):
        axes.append(series_fig.add_subplot(
            gs[i, 0], sharex=axes[0] if axes else None,
        ))
    ax_wind_speed = axes[1].twinx()
    ax_wind_speed.set_in_layout(False)

    # No legend inside the SVG: its HTML counterpart sits to the right.
    polar_fig = plt.figure(figsize=(5.8, 5.8), facecolor=cfg.BG)
    ax_polar = polar_fig.add_axes([0.035, 0.035, 0.93, 0.86], projection="polar")

    view = {
        "figures": {"timeseries": series_fig, "polar": polar_fig},
        "axes": axes,
        "ax_wind_speed": ax_wind_speed,
        "ax_polar": ax_polar,
        "map_image": None,
        "live_mode": False,
        "status": {
            "state": "INITIALIZING", "color": cfg.ORANGE, "age": None,
            "last_data": "—", "last_refresh": "—", "next_refresh": "—",
            "filename": "Waiting for telemetry…",
        },
        "measurements": [],
        "wind_measurement": ("Wind", "—"),
    }

    try:
        view["map_image"] = polar.get_map_image(
            cfg.WMS_URL, cfg.WMS_LAYERS, cfg.MAP_LAT, cfg.MAP_LON,
            width=cfg.MAP_WIDTH,
        )
    except Exception as exc:
        print(f"Could not load basemap: {exc}")
    return view


def update_view(view, *, times, currents, water_depth, now, visible,
                wind_state, filename, last_data_time, status):
    """Update science plots and plain HTML numerical/status data."""
    timeseries.update_timeseries(
        view, times, currents, water_depth, now, visible, wind_state,
    )
    polar.update_polar(view, currents, visible, wind_state.get("data"))

    # Components are intentionally omitted: speed magnitude at each depth only.
    view["measurements"] = [
        (f"{depth:g} m", data.format_value(currents[depth]["speed"][-1], unit=" m/s"), color)
        for depth, color in zip(cfg.TARGET_DEPTHS, cfg.DEPTH_COLORS)
    ]
    view["water_depth"] = data.format_value(water_depth[-1], 2, " m")

    state, color, age = status
    view["status"] = {
        "state": state,
        "color": color,
        "age": max(0, age),
        "last_data": data.format_time(last_data_time),
        "last_refresh": data.format_time(now),
        "next_refresh": (
            data.format_time(now + dt.timedelta(seconds=cfg.REFRESH_SECONDS))
            if view.get("live_mode") else "Not scheduled"
        ),
        "filename": filename,
    }

    # Wind belongs to the numerical panel alongside current speed and depth.
    wind_data = wind_state.get("data")
    if wind_data is not None:
        station = str(wind_data.get("station", "Weather station"))
        timestamp = wind_data["time"].strftime("%H:%M UTC")
        view["wind_measurement"] = (
            f"Wind ({station}, {timestamp})",
            data.format_value(float(wind_data["speed"]), digits=1, unit=" m/s"),
        )
    else:
        view["wind_measurement"] = ("Wind", "No recent data")


def show_error(view, message):
    """Keep the last successful plots while flagging an acquisition error."""
    view["status"].update({
        "state": "UPDATE ERROR",
        "color": cfg.RED,
        "filename": f"Update error: {str(message)[:100]}",
    })

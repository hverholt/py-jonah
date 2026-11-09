"""Time–range velocity and amplitude profiles."""

import datetime as dt
import math
import warnings
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.collections import QuadMesh
import numpy as np
import pandas as pd
import xarray as xr

from .. import config as cfg


def create_figure(ds, plot_type="velocity", now=None):
    """Plot the selected profile type over the latest history window.

    Parameters
    ----------
    ds : xarray.Dataset
        Processed ADCP measurements.
    plot_type : str
        "velocity" or "amplitude".
    now : datetime, optional
        End of the history window in UTC. Defaults to the current UTC time.

    Returns
    -------
    matplotlib.figure.Figure
        Profile figure.
    """
    if plot_type not in cfg.PROFILE_PLOT_SETTINGS:
        raise ValueError(f"Unsupported profile type: {plot_type!r}")
    if ds is None or "TIME" not in ds:
        raise ValueError("No ADCP dataset is available")

    settings = cfg.PROFILE_PLOT_SETTINGS[plot_type]
    times = pd.to_datetime(ds["TIME"].values, utc=True)
    stop = pd.Timestamp(now if now is not None else dt.datetime.now(dt.timezone.utc))
    if stop.tzinfo is None:
        stop = stop.tz_localize("UTC")
    start = stop - pd.Timedelta(hours=cfg.HISTORY_HOURS)
    indices = np.flatnonzero((times >= start) & (times <= stop))
    if not indices.size:
        raise ValueError(f"No {plot_type} observations in the last {cfg.HISTORY_HOURS} hours")

    indices = indices[np.argsort(times[indices])]
    step = max(1, math.ceil(indices.size / cfg.PROFILE_MAX_TIME_SAMPLES))
    if step > 1:
        indices = np.unique(np.r_[indices[::step], indices[-1]])
    selected = ds.isel(TIME=indices)

    if cfg.PROFILE_Y_MODE == "range" and "CP" in selected and "TIME" not in selected["CP"].dims:
        cp = xr.broadcast(selected["TIME"], selected["CP"])[1]
        selected = selected.assign(CP=cp.transpose("TIME", "CN"))

    with plt.rc_context(cfg.PLOT_STYLE):
        from adcp_toolbox import plot as adcp_plot

        coordinates = (
            str(np.asarray(selected["CY"]).reshape(-1)[0])
            if "CY" in selected else "ENU"
        )
        variables, _, _ = adcp_plot.get_plot_args(plot_type, coordinates)
        components = [i for i, name in enumerate(variables) if name in selected]
        if not components:
            raise ValueError(f"No supported {plot_type} components in the dataset")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fig = adcp_plot.plot_data(
                selected,
                plot_type=plot_type,
                x_mode="time",
                y_mode=cfg.PROFILE_Y_MODE,
                subplot_indices=components,
                cmap=settings["cmap"],
                clim=settings["clim"],
                corr_threshold=(
                    cfg.PROFILE_CORR_THRESHOLD
                    if plot_type == "velocity" and all(f"C{i}" in selected for i in range(1, 5))
                    else None
                ),
                datefmt="%H:%M",
            )

        fig.set_size_inches(14, max(4.0, 1.44 * len(components) + 0.8), forward=False)
        fig.set_facecolor(cfg.BG)

        for ax in fig.axes:
            ax.set_facecolor("white")
            ax.patch.set_alpha(1.0)
            for spine in ax.spines.values():
                spine.set_visible(True)
                spine.set_color(cfg.GRID)
                spine.set_linewidth(0.8)

        profile_times = times[indices].to_pydatetime()
        if cfg.PROFILE_Y_MODE == "range":
            water_depth = (
                np.asarray(selected["P"].values, dtype=float).ravel()
                / cfg.DBAR_PER_METER
            )

        for ax in fig.axes[:len(components)]:
            ax.set_xlim(profile_times[0], profile_times[-1])
            if cfg.PROFILE_Y_MODE == "range":
                ax.fill_between(
                    profile_times,
                    water_depth,
                    ax.get_ylim()[1],
                    color=cfg.PANEL,
                    linewidth=0,
                    zorder=2,
                )

            ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8, tz=dt.timezone.utc))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=dt.timezone.utc))
            ax.tick_params(colors=cfg.MUTED, length=3)
            ax.yaxis.label.set_color(cfg.TEXT)
            ax.title.set_color(cfg.TEXT)
            for collection in ax.collections:
                if isinstance(collection, QuadMesh):
                    collection.set_rasterized(True)

        fig.subplots_adjust(left=0.09, right=0.88, bottom=0.09, top=0.97, hspace=0.26)
        return fig

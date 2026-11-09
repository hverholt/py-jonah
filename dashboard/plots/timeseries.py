"""Shared-x time-series plot: direction, current speed, and water depth."""
import datetime as dt
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from .. import config as cfg
from .. import data, wind

def update_wind_timeseries(view, now, wind_state):
    """Show ODR history only; the Þyrill fallback is reserved for polar arrows."""
    axes = view["axes"]
    ax_wind_speed = view["ax_wind_speed"]
    ax_wind_speed.clear()
    history = wind_state.get("history")
    if history is None or history.empty:
        ax_wind_speed.set_visible(False)
        return

    series = wind.wind_plot_series(now, history=history)
    if series.empty or not series["speed"].notna().any():
        ax_wind_speed.set_visible(False)
        return

    ax_wind_speed.set_visible(True)
    times = series.index.to_pydatetime()
    speed = series["speed"].to_numpy(dtype=float)
    direction = (series["direction"].to_numpy(dtype=float) + 180) % 360
    direction[speed <= 0] = np.nan
    plot_times, plot_angles = data.split_direction_crossings(
        times, direction, np.zeros(len(times), dtype=bool),
    )

    axes[0].plot(
        plot_times, plot_angles, color="w", linestyle=":",
        lw=1.5, alpha=cfg.WIND_PLOT_ALPHA,
    )
    ax_wind_speed.plot(
        times, speed, color="w", linestyle=":",
        lw=1.5, alpha=cfg.WIND_PLOT_ALPHA,
    )
    ax_wind_speed.set_ylabel("Wind speed (m/s)", fontsize=12)
    ax_wind_speed.yaxis.set_label_position("right")
    ax_wind_speed.yaxis.set_ticks_position("right")
    ax_wind_speed.tick_params(
        axis="y",
        right=True,
        labelright=True,
        left=False,
        labelleft=False,
        length=4,
        width=0.8,
        color=cfg.GRID,
        labelcolor=cfg.MUTED,
        labelsize=12,
        pad=7,
    )
    ax_wind_speed.spines["right"].set_visible(True)
    ax_wind_speed.spines["right"].set_color(cfg.GRID)
    ax_wind_speed.set_xlim(now - dt.timedelta(hours=cfg.HISTORY_HOURS), now)
    ax_wind_speed.set_ylim(0, max(1.0, 1.15 * np.nanmax(speed)))
    ax_wind_speed.grid(False)

    legend = axes[1].legend(
        [Line2D([], [], color="w", lw=1.3, linestyle=":", alpha=cfg.WIND_PLOT_ALPHA)],
        ["Wind"], loc="lower center",
        bbox_to_anchor=(0.5, 1.025),
        bbox_transform=axes[0].transAxes,
        frameon=False, labelcolor=cfg.TEXT, fontsize=12,
        handlelength=2.0, borderaxespad=0,
    )
    legend.set_in_layout(True)


def update_timeseries(view, times, currents, water_depth, now, visible, wind_state):
    axes = view["axes"]
    all_times = np.asarray(times)
    times_visible = all_times[visible]
    time_gaps = data.get_time_gaps(all_times)
    visible_gaps = time_gaps[visible]
    start_time = now - dt.timedelta(hours=cfg.HISTORY_HOURS)

    variables = [
        ("direction", "Current direction", "°"),
        ("speed", "Current speed", "m/s"),
        ("water_depth", "Water depth", "m"),
    ]
    for ax, (var, name, unit) in zip(axes, variables):
        ax.clear()
        ax.set_facecolor(cfg.PANEL)
        ax.set_axisbelow(True)

        if var == "water_depth":
            values = np.asarray(water_depth, dtype=float)[visible]
            plot_times, plot_values = data.split_time_gaps(
                times_visible, values, visible_gaps,
            )
            ax.plot(plot_times, plot_values, color=cfg.GREEN, lw=1.35)
            recent = values[np.isfinite(values)]
            if recent.size:
                lo, hi = recent.min(), recent.max()
                pad = max((hi - lo) * 0.15, 0.05)
                ax.set_ylim(lo - pad, hi + pad)
            ax.yaxis.set_major_locator(plt.MaxNLocator(3))
        else:
            for i, (depth, color) in enumerate(zip(cfg.TARGET_DEPTHS, cfg.DEPTH_COLORS)):
                layer = 2 * (len(cfg.TARGET_DEPTHS) - i)
                if var == "direction":
                    north = np.asarray(currents[depth]["VN"], dtype=float)
                    east = np.asarray(currents[depth]["VE"], dtype=float)
                    speed = np.hypot(north, east)
                    reliable = speed > cfg.MIN_DIRECTION_SPEED
                    north = np.where(reliable, north, np.nan)
                    east = np.where(reliable, east, np.nan)

                    raw = np.degrees(np.arctan2(east, north)) % 360
                    mean_north = data.running_mean(north, time_gaps)
                    mean_east = data.running_mean(east, time_gaps)
                    mean = np.degrees(np.arctan2(mean_east, mean_north)) % 360
                    mean[
                        np.hypot(mean_north, mean_east) <= cfg.MIN_DIRECTION_SPEED
                    ] = np.nan
                    raw_times, raw_values = data.split_direction_crossings(
                        times_visible, raw[visible], visible_gaps,
                    )
                    mean_times, mean_values = data.split_direction_crossings(
                        times_visible, mean[visible], visible_gaps,
                    )
                else:
                    raw = np.asarray(currents[depth]["speed"], dtype=float)
                    mean = data.running_mean(raw, time_gaps)
                    raw_times, raw_values = data.split_time_gaps(
                        times_visible, raw[visible], visible_gaps,
                    )
                    mean_times, mean_values = data.split_time_gaps(
                        times_visible, mean[visible], visible_gaps,
                    )

                ax.plot(
                    raw_times, raw_values, color=color, lw=1.3,
                    alpha=cfg.RAW_LINE_ALPHA, solid_joinstyle="bevel",
                    zorder=layer
                )
                ax.plot(
                    mean_times, mean_values, color=color, lw=1.5,
                    alpha=1.0, solid_joinstyle="bevel", label=f"{depth:g} m",
                    zorder=layer + 1
                )

        ax.set_ylabel(f"{name} ({unit})", labelpad=10, fontsize=12)
        ax.set_xlim(start_time, now)
        ax.grid(alpha=0.5, linewidth=0.6)
        ax.tick_params(length=0, pad=7, labelsize=12)
        if var == "direction":
            ax.set_ylim(0, 360)
            ax.set_yticks(
                [0, 90, 180, 270, 360],
                ["0° N", "90° E", "180° S", "270° W", "360° N"],
            )
        elif var == "speed":
            ax.set_ylim(bottom=0)

        ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8, tz=data.UTC))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=data.UTC))

    update_wind_timeseries(view, now, wind_state)

    # Restore HH:MM after twinx / wind updates on the shared time axis.
    axes[-1].xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8, tz=data.UTC))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=data.UTC))

    velocity_legend = axes[0].legend(
        title="Current depth", alignment="right", loc="lower right",
        bbox_to_anchor=(1.0, 1.025), ncol=len(cfg.TARGET_DEPTHS),
        frameon=False, labelcolor=cfg.TEXT, fontsize=12,
        handlelength=2.0, columnspacing=1.2, borderaxespad=0,
    )
    axes[0].add_artist(velocity_legend)
    velocity_legend.set_in_layout(True)

    style_legend = axes[0].legend(
        [
            Line2D([], [], color=cfg.DEPTH_COLORS[0], lw=1.3, alpha=cfg.RAW_LINE_ALPHA),
            Line2D([], [], color=cfg.DEPTH_COLORS[0], lw=1.5),
        ],
        ["Raw", f"{cfg.RUNNING_MEAN_SAMPLES}-sample mean"],
        loc="lower left", bbox_to_anchor=(0.0, 1.025), ncol=1,
        frameon=False, labelcolor=cfg.TEXT, fontsize=12,
        handlelength=2.0, borderaxespad=0,
    )
    style_legend.set_in_layout(True)

    for ax in axes[:-1]:
        ax.tick_params(labelbottom=False)
    axes[-1].set_xlabel("Time (UTC)", color=cfg.TEXT, fontsize=12)
    axes[-1].xaxis.set_label_coords(0.47, -0.19)


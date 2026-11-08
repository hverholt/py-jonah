"""Live current overview: figure layout, time series, vectors, and status.

Figures and map requests are created by ``create_view()`` rather than on
import. ``app.py`` supplies processed currents and wind observations; no
telemetry processing or web publishing takes place in this module.
"""

import datetime as dt
import os
from io import BytesIO

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.image import BboxImage
from matplotlib.legend_handler import HandlerBase
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Polygon
from matplotlib.transforms import Bbox, TransformedBbox
from PIL import Image
from pyproj import Transformer

from .. import config as cfg
from .. import data
from .. import wind


# -----------------------------------------------------------------------------
# Basemap and logo
# -----------------------------------------------------------------------------

def get_map_image(wms_url, layers, lat, lon, width=800, resolution=1000):
    """Download the local WMS basemap in a square image."""
    from owslib.wms import WebMapService

    to_3057 = Transformer.from_crs("EPSG:4326", "EPSG:3057", always_xy=True)
    x, y = to_3057.transform(lon, lat)
    half = width / 2
    bounds = (x - half, y - half, x + half, y + half)

    to_3857 = Transformer.from_crs("EPSG:3057", "EPSG:3857", always_xy=True)
    bbox = to_3857.transform_bounds(*bounds)

    wms = WebMapService(wms_url, version="1.1.1")
    response = wms.getmap(
        layers=layers,
        styles=[""] * len(layers),
        srs="EPSG:3857",
        bbox=bbox,
        size=(resolution, resolution),
        format="image/png",
        transparent=False,
    )
    return np.asarray(Image.open(BytesIO(response.read())).convert("RGB"))


def add_polar_basemap(ax, image, alpha=0.5):
    """Fit a circular raster basemap to the live polar axes."""
    image = np.asarray(image)
    height, width = image.shape[:2]
    rgba = np.ones((height, width, 4), dtype=float)
    rgba[..., :3] = image[..., :3] / 255.0
    yy, xx = np.ogrid[-1:1:height * 1j, -1:1:width * 1j]
    rgba[..., 3] = alpha * (xx**2 + yy**2 <= 1)

    artist = BboxImage(ax.bbox, interpolation="bilinear", origin="upper", zorder=-10)
    artist.set_data(rgba)
    artist.set_in_layout(False)
    ax.add_artist(artist)
    return artist


def add_maintainer_logo(fig):
    """Show PNG-converted SVG logo and return its original SVG for web export."""
    if not os.path.isfile(cfg.LOGO_SVG):
        return None, None

    try:
        from cairosvg import svg2png

        with open(cfg.LOGO_SVG, "rb") as file:
            svg_bytes = file.read()
        png = svg2png(bytestring=svg_bytes, output_width=400)
        rgba = np.asarray(Image.open(BytesIO(png)).convert("RGBA"))
    except Exception as exc:
        print(f"Could not load maintainer SVG logo: {exc}")
        print("To enable SVG logos, install CairoSVG: pip install cairosvg")
        return None, None

    image_height, image_width = rgba.shape[:2]
    figure_width, figure_height = fig.get_size_inches()
    width = cfg.LOGO_SIZE
    height = width * (image_height / image_width) * (figure_width / figure_height)
    left, top = cfg.LOGO_POSITION
    bounds = (left, top - height, width, height)

    bbox = TransformedBbox(Bbox.from_bounds(*bounds), fig.transFigure)
    artist = BboxImage(bbox, origin="upper", interpolation="bilinear", zorder=20)
    artist.set_data(rgba)
    artist.set_in_layout(False)
    fig.add_artist(artist)
    return artist, svg_bytes


def update_logo_position(view, event=None):
    """Keep the embedded logo aligned with the figure dimensions."""
    artist = view.get("logo_artist")
    if artist is None:
        return

    image_height, image_width = artist.get_array().shape[:2]
    figure_width, figure_height = view["fig"].get_size_inches()
    width = cfg.LOGO_SIZE
    height = width * (image_height / image_width) * (figure_width / figure_height)
    left, top = cfg.LOGO_POSITION
    artist.bbox = TransformedBbox(
        Bbox.from_bounds(left, top - height, width, height),
        view["fig"].transFigure,
    )


def position_wind_text(view):
    """Keep the wind readout beneath the polar plot."""
    pos = view["ax_polar"].get_position()
    view["wind_text"].set_position(((pos.x0 + pos.x1) / 2, pos.y0 - 0.058))


# -----------------------------------------------------------------------------
# Figure layout
# -----------------------------------------------------------------------------

def create_view():
    """Create the existing Overview layout, returning its figure and artists."""
    plt.rcParams.update(cfg.PLOT_STYLE)

    fig = plt.figure(figsize=(16, 9.8))

    gs_left = fig.add_gridspec(
        3, 1, left=0.070, right=0.605, top=0.870, bottom=0.185,
        height_ratios=[1, 1, 0.6], hspace=0.15,
    )
    axes = []
    for i in range(3):
        axes.append(fig.add_subplot(gs_left[i, 0], sharex=axes[0] if axes else None))
    ax_wind_speed = axes[1].twinx()
    ax_wind_speed.set_in_layout(False)

    gs_right = fig.add_gridspec(
        2, 1, left=0.680, right=0.985, top=0.850, bottom=0.100,
        height_ratios=[0.8, 1], hspace=0.25,
    )
    ax_info = fig.add_subplot(gs_right[0, 0])
    ax_polar = fig.add_subplot(gs_right[1, 0], projection="polar")

    fig.text(
        0.070, 0.95, "HVALFJÖRÐUR ADCP  -  LIVE CURRENT MONITOR",
        fontsize=19, fontweight="bold", color=cfg.TEXT,
    )
    subtitle = fig.text(
        0.070, 0.909, "Waiting for telemetry...", fontsize=10, color=cfg.MUTED,
    )
    fig.text(
        0.965, 0.968,
        f"Maintained by: {cfg.MAINTAINER_NAME}\n{cfg.MAINTAINER_EMAIL}",
        ha="right", va="top", linespacing=1.5, fontsize=9, color=cfg.MUTED,
    )

    status_text = fig.text(
        0.075, 0.12, "INITIALIZING", fontsize=11, weight="bold", color=cfg.ORANGE,
    )
    last_data_text = fig.text(
        0.075, 0.087, "Last data point: —", fontsize=9, color=cfg.MUTED,
    )
    last_refresh_text = fig.text(
        0.075, 0.064, "Last refresh: —", fontsize=9, color=cfg.MUTED,
    )
    next_refresh_text = fig.text(
        0.075, 0.041, "Next refresh: —", fontsize=9, color=cfg.MUTED,
    )
    wind_text = fig.text(
        0.78, 0.115, "Wind: —", fontsize=8.5,
        ha="center", va="top", color=cfg.MUTED,
    )
    wind_text.set_in_layout(False)

    logo_artist, logo_svg_bytes = add_maintainer_logo(fig)

    view = {
        "fig": fig,
        "axes": axes,
        "ax_wind_speed": ax_wind_speed,
        "ax_info": ax_info,
        "ax_polar": ax_polar,
        "subtitle": subtitle,
        "status_text": status_text,
        "last_data_text": last_data_text,
        "last_refresh_text": last_refresh_text,
        "next_refresh_text": next_refresh_text,
        "wind_text": wind_text,
        "logo_artist": logo_artist,
        "logo_svg_bytes": logo_svg_bytes,
        "map_image": None,
    }
    view["update_logo_position"] = lambda: update_logo_position(view)

    # Fetch the basemap at startup only, not at every update or during import.
    try:
        view["map_image"] = get_map_image(
            cfg.WMS_URL, cfg.WMS_LAYERS, cfg.MAP_LAT, cfg.MAP_LON,
            width=cfg.MAP_WIDTH,
        )
    except Exception as exc:
        print(f"Could not load basemap: {exc}")

    position_wind_text(view)
    return view



# -----------------------------------------------------------------------------
# Latest measurements and live wind readout
# -----------------------------------------------------------------------------

def update_info_panel(view, currents, water_depth):
    ax = view["ax_info"]
    ax.clear()
    ax.set_facecolor(cfg.PANEL)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    rows = []
    for depth, color in zip(cfg.TARGET_DEPTHS, cfg.DEPTH_COLORS):
        north = float(currents[depth]["VN"][-1])
        east = float(currents[depth]["VE"][-1])
        speed = float(currents[depth]["speed"][-1])
        rows.extend([
            (f"{depth:g} m North", data.format_value(north, unit=" m/s"), color),
            (f"{depth:g} m East", data.format_value(east, unit=" m/s"), color),
            (f"{depth:g} m Speed", data.format_value(speed, unit=" m/s"), color),
        ])
    rows.append(("Water depth", data.format_value(water_depth[-1], 2, " m"), cfg.MUTED))

    ax.text(
        0.06, 0.90, "LATEST MEASUREMENTS", color=cfg.CYAN,
        fontsize=11, fontweight="bold", va="center",
    )
    fontsize = max(7, min(10, 11 - 0.25 * max(0, len(rows) - 7)))
    positions = np.linspace(0.77, 0.09, len(rows))
    for (name, value, color), y in zip(rows, positions):
        ax.text(0.06, y, name, color=color, fontsize=fontsize, va="center")
        ax.text(
            0.95, y, value, color=cfg.TEXT, fontsize=fontsize,
            fontweight="bold" if name.endswith(" Speed") else "normal",
            ha="right", va="center",
        )


def update_wind_label(view, wind_state):
    wind_text = view["wind_text"]
    wind_data = wind_state.get("data")
    wind_error = wind_state.get("error")

    if wind_error is not None:
        wind_text.set_text(f"Wind: {wind_error}")
        wind_text.set_color(cfg.ORANGE)
    elif wind_data is not None:
        wind_time = wind_data["time"].strftime("%H:%M")
        wind_text.set_text(
            f"Wind speed: {wind_data['speed']:.1f} m/s   "
            f"Weather station: {wind_data['station']}   "
            f"Last wind data: {wind_time} UTC"
        )
        wind_text.set_color(cfg.MUTED)
    else:
        wind_text.set_text("Wind: No data")
        wind_text.set_color(cfg.MUTED)


# -----------------------------------------------------------------------------
# Polar velocity vectors
# -----------------------------------------------------------------------------

class ArrowLegendHandler(HandlerBase):
    def create_artists(self, legend, orig_handle, xdescent, ydescent,
                       width, height, fontsize, trans):
        color = orig_handle.get_edgecolor()
        x0 = -xdescent
        x1 = width - xdescent
        y = height / 2 - ydescent
        head_length = height * 1.2
        head_width = height * 0.95

        shaft = Line2D(
            [x0, x1 - head_length], [y, y],
            color=color, lw=orig_handle.get_linewidth(),
            linestyle=orig_handle.get_linestyle(), transform=trans,
        )
        head = Polygon(
            [(x1, y), (x1 - head_length, y - head_width / 2),
             (x1 - head_length, y + head_width / 2)],
            closed=True, facecolor=color, edgecolor=color,
            linewidth=0, transform=trans,
        )
        return [shaft, head]


def update_polar(view, currents, visible, wind_data):
    ax = view["ax_polar"]
    ax.clear()
    ax.set_facecolor("black")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)

    recent_indices = np.flatnonzero(visible)
    latest_idx = recent_indices[-1] if recent_indices.size else None
    max_speed = 0.05
    if latest_idx is not None:
        for depth in cfg.TARGET_DEPTHS:
            vn = currents[depth]["VN"][latest_idx]
            ve = currents[depth]["VE"][latest_idx]
            if np.isfinite(vn) and np.isfinite(ve):
                max_speed = max(max_speed, 1.15 * np.hypot(vn, ve))
    ax.set_ylim(0, max_speed)

    if view["map_image"] is not None:
        add_polar_basemap(ax, view["map_image"], alpha=cfg.MAP_OPACITY)

    ax.set_thetagrids(
        np.arange(0, 360, 45),
        labels=["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
    )
    ax.tick_params(colors=cfg.TEXT, labelsize=9, pad=5)
    ax.grid(color="white", alpha=0.25, linewidth=0.7)
    ax.spines["polar"].set_color(cfg.GRID)

    for depth, color in zip(cfg.TARGET_DEPTHS, cfg.DEPTH_COLORS):
        if latest_idx is None:
            continue
        vn = currents[depth]["VN"][latest_idx]
        ve = currents[depth]["VE"][latest_idx]
        if not (np.isfinite(vn) and np.isfinite(ve)):
            continue
        speed = np.hypot(vn, ve)
        if speed == 0:
            continue
        direction = np.arctan2(ve, vn) % (2 * np.pi)
        ax.annotate(
            "", xy=(direction, speed), xytext=(direction, 0),
            arrowprops=dict(
                arrowstyle="-|>", color=color, lw=2.5,
                mutation_scale=18, joinstyle="miter", capstyle="projecting",
            ),
            zorder=10,
        )

    if wind_data is not None:
        # Meteorological direction is FROM; the polar arrow points TO.
        theta_wind = np.deg2rad((wind_data["direction"] + 180) % 360)
        r_end = cfg.WIND_ARROW_LENGTH * ax.get_ylim()[1]
        ax.plot(
            [theta_wind, theta_wind], [0, 0.82 * r_end],
            color=cfg.WIND_COLOR, lw=1.8, linestyle="--", zorder=12,
        )
        ax.annotate(
            "", xy=(theta_wind, r_end), xytext=(theta_wind, 0.82 * r_end),
            arrowprops=dict(
                arrowstyle="-|>", color=cfg.WIND_COLOR, lw=1.8,
                mutation_scale=11, shrinkA=0, shrinkB=0,
                joinstyle="miter", capstyle="butt",
            ),
            zorder=13,
        )

    ax.set_title("CURRENT DIRECTION", color=cfg.TEXT,
                 fontsize=11, fontweight="bold", pad=27)
    ax.set_rlabel_position(135)
    for label in ax.get_yticklabels():
        label.set_color(cfg.MUTED)
        label.set_fontsize(8)

    handles = [
        FancyArrowPatch((0, 0), (1, 0), color=color, linewidth=2)
        for color in cfg.DEPTH_COLORS
    ]
    labels = [f"{depth:g} m" for depth in cfg.TARGET_DEPTHS]
    handles.append(
        FancyArrowPatch(
            (0, 0), (1, 0), color=cfg.WIND_COLOR,
            linewidth=1.8, linestyle="--",
        )
    )
    labels.append("Wind")
    legend = ax.legend(
        handles, labels, handler_map={FancyArrowPatch: ArrowLegendHandler()},
        loc="lower right", bbox_to_anchor=(1.20, -0.05),
        bbox_transform=ax.transAxes, frameon=False, fontsize=9,
        labelcolor=cfg.TEXT, handlelength=2.4, labelspacing=0.35,
    )
    legend.set_in_layout(False)


# -----------------------------------------------------------------------------
# Time series and historical ODR wind
# -----------------------------------------------------------------------------

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
    ax_wind_speed.set_ylabel("Wind speed (m/s)")
    ax_wind_speed.yaxis.set_label_position("right")
    ax_wind_speed.yaxis.set_ticks_position("right")
    ax_wind_speed.tick_params(
        axis="y", right=False, labelright=True, left=False, labelleft=False,
    )
    ax_wind_speed.spines["right"].set_visible(True)
    ax_wind_speed.set_xlim(now - dt.timedelta(hours=cfg.HISTORY_HOURS), now)
    ax_wind_speed.set_ylim(0, max(1.0, 1.15 * np.nanmax(speed)))
    ax_wind_speed.tick_params(axis='y', length=0, pad=7)
    ax_wind_speed.grid(False)

    legend = axes[1].legend(
        [Line2D([], [], color="w", lw=1.3, linestyle=":", alpha=cfg.WIND_PLOT_ALPHA)],
        ["Wind"], loc="lower center",
        bbox_to_anchor=(0.5, 1.025),
        bbox_transform=axes[0].transAxes,
        frameon=False, labelcolor=cfg.TEXT, fontsize=9,
        handlelength=2.0, borderaxespad=0,
    )
    legend.set_in_layout(False)


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
            for depth, color in zip(cfg.TARGET_DEPTHS, cfg.DEPTH_COLORS):
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
                )
                ax.plot(
                    mean_times, mean_values, color=color, lw=1.5,
                    alpha=1.0, solid_joinstyle="bevel", label=f"{depth:g} m",
                )

        ax.set_ylabel(f"{name} ({unit})", labelpad=12)
        ax.set_xlim(start_time, now)
        ax.grid(alpha=0.5, linewidth=0.6)
        ax.tick_params(length=0, pad=7)
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
        frameon=False, labelcolor=cfg.TEXT, fontsize=9,
        handlelength=2.0, columnspacing=1.2, borderaxespad=0,
    )
    axes[0].add_artist(velocity_legend)
    velocity_legend.set_in_layout(False)

    style_legend = axes[0].legend(
        [
            Line2D([], [], color=cfg.DEPTH_COLORS[0], lw=1.3, alpha=cfg.RAW_LINE_ALPHA),
            Line2D([], [], color=cfg.DEPTH_COLORS[0], lw=1.5),
        ],
        ["Raw", f"{cfg.RUNNING_MEAN_SAMPLES}-sample mean"],
        loc="lower left", bbox_to_anchor=(0.0, 1.025), ncol=2,
        frameon=False, labelcolor=cfg.TEXT, fontsize=9,
        handlelength=2.0, borderaxespad=0, columnspacing=1.2
    )
    style_legend.set_in_layout(False)

    for ax in axes[:-1]:
        ax.tick_params(labelbottom=False)
    axes[-1].set_xlabel("Time (UTC)", color=cfg.TEXT)
    axes[-1].xaxis.set_label_coords(0.45, -0.25)


# -----------------------------------------------------------------------------
# Entry point used by dashboard/app.py
# -----------------------------------------------------------------------------

def update_view(view, *, times, currents, water_depth, now, visible,
                wind_state, filename, last_data_time, status):
    """Update the full Overview from data already prepared by ``app.py``."""
    update_timeseries(view, times, currents, water_depth, now, visible, wind_state)
    update_info_panel(view, currents, water_depth)
    update_polar(view, currents, visible, wind_state.get("data"))
    update_wind_label(view, wind_state)

    state, color, age = status
    view["status_text"].set_text(
        f"● {state}   |   Data age: {max(0, age):.0f} s"
    )
    view["status_text"].set_color(color)
    view["last_data_text"].set_text(
        f"{'Last data point:':<20}{data.format_time(last_data_time)}"
    )
    view["last_refresh_text"].set_text(
        f"{'Last refresh:':<22}{data.format_time(now)}"
    )
    view["next_refresh_text"].set_text(
        f"{'Next refresh:':<21}"
        f"{data.format_time(now + dt.timedelta(seconds=cfg.REFRESH_SECONDS))}"
    )
    view["subtitle"].set_text(
        f"{filename}   •   Viewing last {cfg.HISTORY_HOURS} hours   •   "
        f"Auto-refresh: {cfg.REFRESH_SECONDS // 60} min"
    )
    position_wind_text(view)


def show_error(view, message):
    """Show an acquisition error while retaining any previously drawn data."""
    view["status_text"].set_text("● OFFLINE / UPDATE ERROR")
    view["status_text"].set_color(cfg.RED)
    view["subtitle"].set_text(f"Update error: {str(message)[:100]}")

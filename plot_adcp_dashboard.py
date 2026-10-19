from matplotlib.legend_handler import HandlerBase
from matplotlib.patches import Polygon
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch
from matplotlib.image import BboxImage
from owslib.wms import WebMapService
from pyproj import Transformer
from io import BytesIO, StringIO
from pathlib import Path
from matplotlib.transforms import Bbox, TransformedBbox
from PIL import Image
import base64
import os
import argparse
import sys
import glob
import time
import shutil
import traceback
import requests
import datetime as dt
import numpy as np
import pandas as pd
import xarray as xr
import matplotlib

matplotlib.use("QtAgg")

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from adcp_toolbox import telemetry2netcdf


# ============================================================
# Configuration
# ============================================================

# Project root
ROOT = Path(__file__).resolve().parent

# Input
INPUT_DIR = r"C:\Users\Nortek1000\Documents\Nortek\Deployment\Online"

# Intermediate and processed data
TXT_FILE = str(ROOT / "data" / "interim" / "latest.txt")
NC_FILE = str(ROOT / "data" / "processed" / "latest.nc")

# Output
EXPORT_DIR = str(ROOT / "output" / "preview")
EXPORT_DPI = 150
FONT_FAMILY = "DejaVu Sans"
FONT_FALLBACK = "Arial"

# Attribution
MAINTAINER_NAME = "Sindri Bernholt"
MAINTAINER_EMAIL = "sindri@rostrannsoknir.is"
LOGO_SVG = str(ROOT / "assets" / "logos" / "rost-logo-icelandic-white.svg")
LOGO_POSITION = (0.67, 0.975)
LOGO_SIZE = 0.16


# Data settings
TARGET_DEPTHS = (1, 1.5, 2, 3, 4, 5)  # metres below sea surface
DBAR_PER_METER = 1.0065

# Live plot settings
STALE_AFTER_SECONDS = 180
HISTORY_HOURS = 24
REFRESH_SECONDS = 120
WEB_POLL_SECONDS = 15

# Primary station (MOGT)
MOGT_URL = "https://vedur.mogt.is/harbor/index.php"
MOGT_STATION_ID = 1035
MOGT_STATION_NAME = "ODR Hvalfjörður"

# Backup station (IMO)
VEDUR_URL = "https://api.vedur.is/weather/observations/aws/10min/latest"
WEATHER_STATION_ID = 1685
WEATHER_STATION_NAME = "Þyrill"

WIND_MAX_AGE = 30
WIND_ARROW_LENGTH = 0.32  # fraction of polar radius
WIND_COLOR = "#ffffff"

# ADCP location and map parameters
MAP_LAT = 64.393931
MAP_LON = -21.466464
MAP_WIDTH = 400 # in metres
MAP_OPACITY = 0.8
WMS_URL = "https://gis.natt.is/mapcache/web-mercator/wms"
WMS_LAYERS = ["LMI_Island_einfalt"]

# Colors
BG = "#0b1019"
PANEL = "#151e2b"
GRID = "#344155"
TEXT = "#e5edf7"
MUTED = "#91a0b5"

CYAN = "#4dd9e8"
ORANGE = "#ffb86b"
GREEN = "#72e6ac"
RED = "#ff747c"

DEPTH_COLOR_PALETTE = (CYAN, ORANGE, "#f78cb7", "#b8a0ff", "#f0d76c")
TARGET_DEPTHS = TARGET_DEPTHS[:len(DEPTH_COLOR_PALETTE)]
DEPTH_COLORS = DEPTH_COLOR_PALETTE[:len(TARGET_DEPTHS)]


plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor": PANEL,
    "savefig.facecolor": BG,
    "axes.edgecolor": GRID,
    "axes.labelcolor": TEXT,
    "text.color": TEXT,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "grid.color": GRID,
    "font.family": [FONT_FAMILY, FONT_FALLBACK, "sans-serif"],
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


# ============================================================
# Basemap
# ============================================================

def get_map_image(
    wms_url,
    layers,
    lat,
    lon,
    width=800,
    resolution=1000,
):
    # Geographic coordinates to Icelandic projected coordinates
    to_3057 = Transformer.from_crs(
        "EPSG:4326", "EPSG:3057", always_xy=True
    )

    x, y = to_3057.transform(lon, lat)
    half = width / 2

    bounds_3057 = (
        x - half,
        y - half,
        x + half,
        y + half,
    )

    # Transform bounding box to WMS coordinate system
    to_3857 = Transformer.from_crs(
        "EPSG:3057", "EPSG:3857", always_xy=True
    )

    bbox = to_3857.transform_bounds(*bounds_3057)

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

    return np.asarray(
        Image.open(BytesIO(response.read())).convert("RGB")
    )


# Load basemap once at startup and store as image array
try:
    map_image = get_map_image(
        WMS_URL,
        WMS_LAYERS,
        MAP_LAT,
        MAP_LON,
        width=MAP_WIDTH,
    )
except Exception as e:
    print(f"Could not load basemap: {e}")
    map_image = None


def add_polar_basemap(ax, image, alpha=0.5):
    """Render a circular RGBA basemap fitted exactly to the polar axes.

    BboxImage tracks ax.bbox during drawing and window resizing.
    """
    image = np.asarray(image)
    height, width = image.shape[:2]

    rgba = np.ones((height, width, 4), dtype=float)
    rgba[..., :3] = image[..., :3] / 255.0

    yy, xx = np.ogrid[-1:1:height*1j, -1:1:width*1j]
    rgba[..., 3] = alpha * (xx**2 + yy**2 <= 1)

    artist = BboxImage(
        ax.bbox,
        interpolation="bilinear",
        origin="upper",
        zorder=-10,
    )
    artist.set_data(rgba)
    artist.set_in_layout(False)
    ax.add_artist(artist)
    return artist


# ============================================================
# Wind observations
# ============================================================

wind_data = None
wind_error = None


def get_wind(max_age=WIND_MAX_AGE):
    """Return latest valid wind observation, preferring Olíudreifing."""

    def validate(df, station):
        df = df.copy()

        for col in ("time", "f", "d"):
            if col not in df:
                raise ValueError(f"Missing field: {col}")

        df["time"] = pd.to_datetime(
            df["time"], utc=True, errors="coerce"
        )
        df["f"] = pd.to_numeric(df["f"], errors="coerce")
        df["d"] = pd.to_numeric(df["d"], errors="coerce")

        df = df.dropna(subset=["time", "f", "d"])
        df = df[(df["f"] >= 0) & df["d"].between(0, 360)]

        if df.empty:
            raise ValueError("No valid wind observations")

        latest = df.sort_values("time").iloc[-1]
        age = (
            pd.Timestamp.now(tz="UTC") - latest["time"]
        ).total_seconds() / 60

        if age < -5 or age > max_age:
            raise ValueError(f"Observation age: {age:.1f} minutes")

        return {
            "speed": float(latest["f"]),
            "direction": float(latest["d"]),  # FROM direction (meteorological)
            "time": latest["time"],
            "station": station,
        }

    # Primary weather station (MOGT)
    try:
        response = requests.get(
            MOGT_URL,
            params={
                "action": "ReadingsDrillDown",
                "stationid": MOGT_STATION_ID,
            },
            timeout=15,
        )
        response.raise_for_status()

        tables = pd.read_html(StringIO(response.text))

        df = next(
            table for table in tables
            if any("Vindur" in str(c) for c in table.columns)
        ).copy()

        df.columns = ["time", "f", "fg", "d", "t"]

        df["time"] = pd.to_datetime(
            df["time"],
            format="%H:%M %d.%m.%Y",
            errors="coerce",
            utc=True,
        )

        return validate(df, MOGT_STATION_NAME)

    except Exception as e:
        print(f"{MOGT_STATION_NAME} unavailable: {e}")
        print(f"Trying {WEATHER_STATION_NAME}...")

    # Backup weather station (IMO)
    try:
        response = requests.get(
            VEDUR_URL,
            params={
                "station_id": WEATHER_STATION_ID,
                "parameters": "basic",
            },
            timeout=20,
        )
        response.raise_for_status()

        df = pd.DataFrame(response.json())

        return validate(df, WEATHER_STATION_NAME)

    # If neither primary nor backup weather station works raise error
    except Exception as e:
        raise RuntimeError(
            f"Weather data unavailable. "
            f"{WEATHER_STATION_NAME}: {e}"
        ) from e


def refresh_wind():
    """Update wind independently of ADCP processing."""
    global wind_data, wind_error

    try:
        wind_data = get_wind()
        wind_error = None

    except Exception as e:
        wind_data = None
        wind_error = str(e).splitlines()[0][:100]
        print(f"Wind retrieval failed: {wind_error}")


def update_wind_label():
    if wind_error is not None:
        wind_text.set_text(f"Wind: {wind_error}")
        wind_text.set_color(ORANGE)

    elif wind_data is not None:
        wind_time = wind_data["time"].strftime("%H:%M")

        wind_text.set_text(
            f"Wind speed: {wind_data['speed']:.1f} m/s   "
            f"Weather station: {wind_data['station']}   "
            f"Last wind data: {wind_time} UTC"
        )
        wind_text.set_color(MUTED)

    else:
        wind_text.set_text("Wind: No data")
        wind_text.set_color(MUTED)


# ============================================================
# File loading
# ============================================================

def get_recent_files(hours):
    cutoff = time.time() - hours * 3600

    files = glob.glob(
        os.path.join(INPUT_DIR, "Terminal_*.txt")
    )

    files = [
        f for f in files
        if os.path.isfile(f) and os.path.getmtime(f) >= cutoff
    ]

    if not files:
        raise FileNotFoundError(
            f"No telemetry files modified in the last {hours} hours."
        )

    # Filenames usually contain timestamps, so this sorts them chronologically
    # Correct sorting is not absolutely critical though as data is eventually sorted by time
    return sorted(files)


def load_data():
    # Get all recent telemetry files (within specified interval plus 1 hour buffer)
    source_files = get_recent_files(hours=HISTORY_HOURS + 1)

    os.makedirs(os.path.dirname(TXT_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(NC_FILE), exist_ok=True)

    # Combine all recent telemetry files into one file: latest.txt
    temp_file = TXT_FILE + ".tmp"

    with open(temp_file, "wb") as dest:
        for source_file in source_files:
            with open(source_file, "rb") as src:
                shutil.copyfileobj(src, dest)

            # Ensure consecutive files are separated
            dest.write(b"\n")

    os.replace(temp_file, TXT_FILE)

    # Convert combined telemetry to NetCDF
    telemetry2netcdf.telemetry_to_netcdf(
        TXT_FILE,
        NC_FILE,
        102,
        filter_errors=True,
    )

    with xr.open_dataset(NC_FILE) as ds:
        ds = ds.load()

    filename = (
        f"{len(source_files)} files "
        f"(latest: {os.path.basename(source_files[-1])})"
    )

    return ds, filename


# ============================================================
# Velocity extraction
# ============================================================

def extract_velocity(ds, target_depths=TARGET_DEPTHS):
    """Interpolate horizontal velocities at fixed depths below the surface."""

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

    water_depth = pressure / DBAR_PER_METER
    depth = water_depth[:, None] - cp

    targets = np.asarray(target_depths, dtype=float)
    n_times = vn.shape[0]

    north = np.full((len(targets), n_times), np.nan)
    east = np.full((len(targets), n_times), np.nan)

    # Process each velocity profile
    for i in range(n_times):

        valid = (
            np.isfinite(depth[i])
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

        # Interpolate within only the measured depth range
        inside = (targets >= z[0]) & (targets <= z[-1])
        north[inside, i] = np.interp(targets[inside], z, n)
        east[inside, i] = np.interp(targets[inside], z, e)

    result = {}

    for j, target in enumerate(target_depths):
        result[target] = {
            "VN": north[j],
            "VE": east[j],
            "speed": np.hypot(north[j], east[j]),
        }

    return result, water_depth


# ============================================================
# Time and status helpers
# ============================================================

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
    """
    Determine telemetry freshness from actual observation time,
    not from local file modification time.
    """

    age = (now - last_data_time).total_seconds()

    if age < -60:
        return "CLOCK ERROR", RED, age

    if age <= STALE_AFTER_SECONDS:
        return "LIVE", GREEN, age

    return "STALE", ORANGE, age


# ============================================================
# Figure layout
# ============================================================

fig = plt.figure(figsize=(16, 9.5))

# Left side 
# Three velocity plots
gs_left = fig.add_gridspec(
    3, 1,
    left=0.085,
    right=0.63,
    top=0.855,
    bottom=0.22,
    hspace=0.15,
)

axes = [
    fig.add_subplot(gs_left[i, 0])
    for i in range(3)
]

# Right side
# Numerical dashboard and polar plot
gs_right = fig.add_gridspec(
    2, 1,
    left=0.66,
    right=0.965,
    top=0.83,
    bottom=0.1,
    height_ratios=[0.8, 1],
    hspace=0.25,
)

ax_info = fig.add_subplot(gs_right[0, 0])
ax_polar = fig.add_subplot(gs_right[1, 0], projection="polar")

# Header
fig.text(
    0.085, 0.95,
    "ADCP  -  LIVE CURRENT MONITOR",
    fontsize=19,
    fontweight="bold",
    color=TEXT,
)

subtitle = fig.text(
    0.085, 0.909,
    "Waiting for telemetry...",
    fontsize=10,
    color=MUTED,
)

fig.text(
    0.965, 0.968,
    f"Maintained by: {MAINTAINER_NAME}\n{MAINTAINER_EMAIL}",
    ha="right",
    va="top",
    linespacing=1.5,
    fontsize=9,
    color=MUTED,
)


def add_maintainer_logo():
    """Show logo.svg in Matplotlib; also keep its SVG source for web exports.

    The optional cairosvg dependency converts SVG to pixels for the live
    window and PNG output. SVG/HTML exports embed the original vector logo.
    """
    if not os.path.isfile(LOGO_SVG):
        return None, None, None

    try:
        from cairosvg import svg2png
        with open(LOGO_SVG, "rb") as file:
            svg_bytes = file.read()
        png = svg2png(bytestring=svg_bytes, output_width=400)
        rgba = np.asarray(Image.open(BytesIO(png)).convert("RGBA"))
    except Exception as exc:
        print(f"Could not load maintainer SVG logo: {exc}")
        print("To enable SVG logos, install CairoSVG: pip install cairosvg")
        return None, None, None

    # Fit logo while retaining original aspect ratio
    height_px, width_px = rgba.shape[:2]
    fig_w, fig_h = fig.get_size_inches()
    w = LOGO_SIZE
    h = w * (height_px / width_px) * (fig_w / fig_h)
    bounds = (LOGO_POSITION[0], LOGO_POSITION[1] - h, w, h)  # left, bottom, width, height

    image_bbox = TransformedBbox(Bbox.from_bounds(*bounds), fig.transFigure)
    artist = BboxImage(image_bbox, origin="upper", interpolation="bilinear", zorder=20)
    artist.set_data(rgba)
    artist.set_in_layout(False)
    fig.add_artist(artist)
    return artist, svg_bytes, bounds


logo_artist, logo_svg_bytes, logo_bounds = add_maintainer_logo()


def update_logo_position(event=None):
    global logo_bounds

    if logo_artist is None:
        return

    height_px, width_px = logo_artist.get_array().shape[:2]
    fig_w, fig_h = fig.get_size_inches()
    w = LOGO_SIZE
    h = w * (height_px / width_px) * (fig_w / fig_h)

    logo_bounds = (
        LOGO_POSITION[0],
        LOGO_POSITION[1] - h,
        w, h
    )

    logo_artist.bbox = TransformedBbox(
        Bbox.from_bounds(*logo_bounds),
        fig.transFigure
    )


fig.canvas.mpl_connect("resize_event", update_logo_position)


# Footer containing data freshness label
status_text = fig.text(
    0.09, 0.12,
    "INITIALIZING",
    fontsize=11,
    weight="bold",
    color=ORANGE,
)

last_data_text = fig.text(
    0.09, 0.087,
    "Last data point: —",
    fontsize=9,
    color=MUTED,
)

last_refresh_text = fig.text(
    0.09, 0.064,
    "Last refresh: —",
    fontsize=9,
    color=MUTED,
)

next_refresh_text = fig.text(
    0.09, 0.041,
    "Next refresh: —",
    fontsize=9,
    color=MUTED,
)

# Small water-depth plot
ax_depth = fig.add_axes([0.38, 0.04, 0.25, 0.09])
ax_depth.set_facecolor(PANEL)
ax_depth.set_in_layout(False)


# Dedicated wind readout below the polar circle
wind_text = fig.text(
    0.78, 0.115,
    "Wind: —",
    fontsize=8.5,
    ha="center",
    va="top",
    color=MUTED,
)
wind_text.set_in_layout(False)


def position_wind_text():
    """Place the wind readout below the polar plot, not in the footer."""
    pos = ax_polar.get_position()
    wind_text.set_position(((pos.x0 + pos.x1) / 2, pos.y0 - 0.058))


# ============================================================
# Window appearance
# ============================================================

def make_dark_window():
    window = fig.canvas.manager.window

    window.setStyleSheet(f"""
        QMainWindow {{
            background-color: {BG};
            color: {TEXT};
        }}
        QWidget {{
            background-color: {BG};
        }}
        QToolBar {{
            background-color: {PANEL};
            border: none;
        }}
        QToolButton {{
            color: {TEXT};
            background-color: {PANEL};
            border: none;
            padding: 4px;
        }}
        QToolButton:hover {{
            background-color: {GRID};
        }}
    """)

    if sys.platform == "win32":
        try:
            import ctypes

            hwnd = int(window.winId())
            value = ctypes.c_int(1)

            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                20,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
        except Exception:
            pass

    window.showMaximized()


# ============================================================
# Numerical dashboard
# ============================================================

def update_info_panel(data, water_depth):
    ax_info.clear()

    ax_info.set_facecolor(PANEL)
    ax_info.set_xlim(0, 1)
    ax_info.set_ylim(0, 1)
    ax_info.set_xticks([])
    ax_info.set_yticks([])

    for spine in ax_info.spines.values():
        spine.set_visible(False)

    # Generate rows for every configured depth.
    rows = []
    for depth, color in zip(TARGET_DEPTHS, DEPTH_COLORS):
        north = float(data[depth]["VN"][-1])
        east = float(data[depth]["VE"][-1])
        speed = float(data[depth]["speed"][-1])

        rows.extend([
            (f"{depth:g} m North", format_value(north, unit=" m/s"), color),
            (f"{depth:g} m East", format_value(east, unit=" m/s"), color),
            (f"{depth:g} m Speed", format_value(speed, unit=" m/s"), color),
        ])

    rows.append((
        "Water depth", format_value(water_depth[-1], 2, " m"), MUTED
    ))

    ax_info.text(
        0.06, 0.90,
        "LATEST MEASUREMENTS",
        color=CYAN,
        fontsize=11,
        fontweight="bold",
        va="center",
    )

    # Reduce text size as more depths are selected
    fontsize = max(7, min(10, 11 - 0.25 * max(0, len(rows) - 7)))
    positions = np.linspace(0.77, 0.09, len(rows))

    for (name, value, color), y in zip(rows, positions):
        ax_info.text(
            0.06, y,
            name,
            color=color,
            fontsize=fontsize,
            va="center",
        )

        ax_info.text(
            0.95, y,
            value,
            color=TEXT,
            fontsize=fontsize,
            fontweight="bold",
            ha="right",
            va="center",
        )


# ============================================================
# Polar velocity vector
# ============================================================

class ArrowLegendHandler(HandlerBase):
    def create_artists(self, legend, orig_handle, xdescent, ydescent,
                       width, height, fontsize, trans):

        color = orig_handle.get_edgecolor()
        x0 = -xdescent
        x1 = width - xdescent
        y = height / 2 - ydescent

        head_length = height * 1.2
        head_width = height * 0.95

        # Arrow shaft
        shaft = Line2D(
            [x0, x1 - head_length],
            [y, y],
            color=color,
            lw=orig_handle.get_linewidth(),
            linestyle=orig_handle.get_linestyle(),
            transform=trans,
        )

        # Arrowhead
        head = Polygon(
            [
                (x1, y),
                (x1 - head_length, y - head_width / 2),
                (x1 - head_length, y + head_width / 2),
            ],
            closed=True,
            facecolor=color,
            edgecolor=color,
            linewidth=0,
            transform=trans,
        )

        return [shaft, head]


def update_polar(data, visible):
    ax_polar.clear()

    ax_polar.set_facecolor("black")
    ax_polar.set_theta_zero_location("N")
    ax_polar.set_theta_direction(-1)

    # Scale based on the latest observations
    recent_indices = np.flatnonzero(visible)
    latest_idx = recent_indices[-1] if recent_indices.size else None

    max_speed = 0.05
    if latest_idx is not None:
        for depth in TARGET_DEPTHS:
            vn = data[depth]["VN"][latest_idx]
            ve = data[depth]["VE"][latest_idx]
            if np.isfinite(vn) and np.isfinite(ve):
                max_speed = max(max_speed, 1.15 * np.hypot(vn, ve))

    ax_polar.set_ylim(0, max_speed)

    # Basemap conforms to the polar axis bounding box
    if map_image is not None:
        add_polar_basemap(ax_polar, map_image, alpha=MAP_OPACITY)

    ax_polar.set_thetagrids(
        np.arange(0, 360, 45),
        labels=["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
    )
    ax_polar.tick_params(colors=TEXT, labelsize=9, pad=5)
    ax_polar.grid(color="white", alpha=0.25, linewidth=0.7)
    ax_polar.spines["polar"].set_color(GRID)

    # Draw current velocity vectors using the most recent observation
    for depth, color in zip(TARGET_DEPTHS, DEPTH_COLORS):
        if latest_idx is None:
            continue
    
        vn = data[depth]["VN"][latest_idx]
        ve = data[depth]["VE"][latest_idx]
    
        if not (np.isfinite(vn) and np.isfinite(ve)):
            continue

        speed = np.hypot(vn, ve)

        if speed == 0:
            continue

        direction = np.arctan2(ve, vn) % (2 * np.pi)
        ax_polar.annotate(
            "",
            xy=(direction, speed),
            xytext=(direction, 0),
            arrowprops=dict(
                arrowstyle="-|>",
                color=color,
                lw=2.5,
                mutation_scale=18,
                joinstyle="miter",
                capstyle="projecting",
            ),
            zorder=10,
        )

    # Fixed-length dashed wind arrow pointing in where the wind GOES TO
    if wind_data is not None:
        # meteorological wind direction is where the wind COMES FROM (shift by 180 deg)
        theta_wind = np.deg2rad((wind_data["direction"] + 180) % 360)
        rmax = ax_polar.get_ylim()[1]
        r_end = WIND_ARROW_LENGTH * rmax

        ax_polar.plot(
            [theta_wind, theta_wind],
            [0, 0.82 * r_end],
            color=WIND_COLOR,
            lw=1.8,
            linestyle="--",
            zorder=12,
        )
        ax_polar.annotate(
            "",
            xy=(theta_wind, r_end),
            xytext=(theta_wind, 0.82 * r_end),
            arrowprops=dict(
                arrowstyle="-|>",
                color=WIND_COLOR,
                lw=1.8,
                mutation_scale=11,
                shrinkA=0,
                shrinkB=0,
                joinstyle="miter",
                capstyle="butt",
            ),
            zorder=13,
        )

    ax_polar.set_title(
        "CURRENT DIRECTION",
        color=TEXT,
        fontsize=11,
        fontweight="bold",
        pad=27,
    )
    ax_polar.set_rlabel_position(135)
    for label in ax_polar.get_yticklabels():
        label.set_color(MUTED)
        label.set_fontsize(8)


    # --------------------------------------------------------
    # Current and wind legend
    # --------------------------------------------------------

    colors = DEPTH_COLORS

    handles = [
        FancyArrowPatch(
            (0, 0), (1, 0),
            color=color,
            linewidth=2,
        )
        for color in colors
    ]

    labels = [f"{depth:g} m" for depth in TARGET_DEPTHS]

    # Wind
    handles.append(
        FancyArrowPatch(
            (0, 0), (1, 0),
            color=WIND_COLOR,
            linewidth=1.8,
            linestyle="--",
        )
    )
    labels.append("Wind")

    legend = ax_polar.legend(
        handles,
        labels,
        handler_map={
            FancyArrowPatch: ArrowLegendHandler()
        },
        loc="lower right",
        bbox_to_anchor=(1.32, -0.05),
        bbox_transform=ax_polar.transAxes,
        frameon=False,
        fontsize=9,
        labelcolor=TEXT,
        handlelength=2.4,
        labelspacing=0.35,
    )

    legend.set_in_layout(False)


    
# ============================================================
# Time-series plots
# ============================================================

def update_timeseries(times, data, now, visible):
    start_time = now - dt.timedelta(hours=HISTORY_HOURS)

    variables = [
        ("VN", "Northward velocity", "m/s"),
        ("VE", "Eastward velocity", "m/s"),
        ("speed", "Current speed", "m/s"),
    ]

    for ax, (var, name, unit) in zip(axes, variables):
        ax.clear()

        ax.set_facecolor(PANEL)
        ax.set_axisbelow(True)
        
        for depth, color in zip(TARGET_DEPTHS, DEPTH_COLORS):
            ax.plot(
                np.asarray(times)[visible],
                np.asarray(data[depth][var])[visible],
                color=color,
                lw=1.8,
                alpha=0.95,
                solid_joinstyle="bevel",
                label=f"{depth:g} m",
            )
        
        ax.set_ylabel(f"{name}\n({unit})", labelpad=12)

        # Update limits to current time, independent of data
        ax.set_xlim(start_time, now)

        ax.grid(alpha=0.5, linewidth=0.6)
        ax.tick_params(length=0, pad=7)

        if var != "speed":
            ax.axhline(
                0,
                color=MUTED,
                lw=0.8,
                alpha=0.7,
            )
        else:
            ax.set_ylim(bottom=0)

        ax.xaxis.set_major_locator(
            mdates.AutoDateLocator(maxticks=8, tz=UTC)
        )

        ax.xaxis.set_major_formatter(
            mdates.DateFormatter("%H:%M", tz=UTC)
        )

    velocity_legend = axes[0].legend(
        loc="lower right",
        bbox_to_anchor=(1.0, 1.025),
        ncol=len(TARGET_DEPTHS),
        frameon=False,
        labelcolor=TEXT,
        fontsize=9,
        handlelength=2.0,
        columnspacing=1.2,
        borderaxespad=0,
    )
    velocity_legend.set_in_layout(False)

    # Only add a time-axis label to the bottom subplot
    for ax in axes[:-1]:
        ax.tick_params(labelbottom=False)

    axes[-1].set_xlabel("Time (UTC)", color=TEXT)
    axes[-1].xaxis.set_label_coords(0.45, -0.25)


# ============================================================
# Water-depth plot
# ============================================================

def update_depth_plot(times, water_depth, now):
    """Small pressure-derived depth trace on the same UTC window as velocities."""
    ax_depth.clear()
    ax_depth.set_facecolor(PANEL)

    depth = np.asarray(water_depth, dtype=float)
    ax_depth.plot(times, depth, color=GREEN, lw=1.35)

    ax_depth.set_xlim(
        now - dt.timedelta(hours=HISTORY_HOURS),
        now,
    )
    ax_depth.set_title("WATER DEPTH (m)", loc="left", color=TEXT,
                       fontsize=8, pad=7)
    ax_depth.grid(True, color=GRID, alpha=0.45, lw=0.5)
    ax_depth.tick_params(colors=MUTED, labelsize=7, length=2, pad=2)
    ax_depth.xaxis.set_major_locator(
        mdates.AutoDateLocator(minticks=2, maxticks=3, tz=UTC)
    )
    ax_depth.xaxis.set_major_formatter(
        mdates.DateFormatter("%H:%M", tz=UTC)
    )
    ax_depth.yaxis.set_major_locator(plt.MaxNLocator(3))

    # Keep small tidal changes visible without using an exaggerated range
    finite = depth[np.isfinite(depth)]
    if len(finite):
        shown = np.asarray(times) >= (
            now - dt.timedelta(hours=HISTORY_HOURS)
        )
        recent = depth[shown & np.isfinite(depth)]
        if len(recent):
            lo, hi = recent.min(), recent.max()
            pad = max((hi - lo) * 0.15, 0.05)
            ax_depth.set_ylim(lo - pad, hi + pad)


# ============================================================
# Dashboard export
# ============================================================

def _atomic_write(path, content):
    """Replace a served file only once its new contents are complete."""
    temporary = path + ".tmp"
    with open(temporary, "wb") as file:
        file.write(content)
    os.replace(temporary, path)


def export_dashboard():
    """Export the current figure as a standalone, browser-readable dashboard.

    The HTML contains inline SVG with actual SVG text nodes, so the
    text can be selected in a browser. The map remains a raster image.
    """
    os.makedirs(EXPORT_DIR, exist_ok=True)
    update_logo_position()

    # Preserve text as SVG text elements
    svg_buffer = BytesIO()
    if logo_artist is not None:
        logo_artist.set_visible(False)
    try:
        with plt.rc_context({"svg.fonttype": "none", "svg.image_inline": True}):
            fig.savefig(svg_buffer, format="svg", facecolor=BG)
    finally:
        if logo_artist is not None:
            logo_artist.set_visible(True)

    svg = svg_buffer.getvalue().decode("utf-8")
    start = svg.find("<svg ")
    if start == -1:
        raise ValueError("No SVG element found in exported dashboard")
    inline_svg = svg[start:]

    inline_svg = inline_svg.replace(
        "<svg ", '<svg xml:space="preserve" ', 1
    )

    svg_font_css = (
        f"text, tspan {{ font-family: '{FONT_FAMILY}', "
        f"'{FONT_FALLBACK}', sans-serif !important; "
        "white-space: pre !important; }"
    )
    svg_tag_end = inline_svg.find(">")
    inline_svg = (
        inline_svg[:svg_tag_end + 1]
        + f"\n<style type=\"text/css\">{svg_font_css}</style>\n"
        + inline_svg[svg_tag_end + 1:]
    )

    # Embed logo as an SVG image
    if logo_svg_bytes is not None:
        left, bottom, width, height = logo_bounds
        figure_width, figure_height = fig.get_size_inches() * 72  #svg viewbox points
        x = left * figure_width
        y = (1 - bottom - height) * figure_height
        w = width * figure_width
        h = height * figure_height
        logo_uri = base64.b64encode(logo_svg_bytes).decode("ascii")
        logo_element = (
            f'<image x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" '
            f'height="{h:.2f}" '
            f'href="data:image/svg+xml;base64,{logo_uri}" />'
        )
        inline_svg = inline_svg.replace("</svg>", logo_element + "\n</svg>", 1)

    html_page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="dashboard-generated" content="{time.time_ns()}">
  <title>ADCP live current monitor</title>
  <style>
    html, body {{ margin: 0; min-height: 100%; background: {BG}; }}
    body {{ display: flex; justify-content: center; align-items: center; }}
    svg {{ display: block; width: 100%; max-height: 100vh; height: auto; }}
    svg text, svg tspan {{
      font-family: '{FONT_FAMILY}', '{FONT_FALLBACK}', sans-serif !important;
      white-space: pre !important;
      user-select: text;
      -webkit-user-select: text;
    }}
  </style>
</head>
<body>
{inline_svg}
<script>
  // Check the server regularly and bypass cached responses.
  let displayedVersion = document.querySelector('meta[name="dashboard-generated"]').content;
  let lastModified = null;
  let checking = false;

  async function checkDashboard() {{
    if (checking) return;
    checking = true;
    try {{
      const url = new URL(window.location.href);
      url.searchParams.set('_', Date.now().toString());
      // A lightweight HEAD request avoids downloading the embedded map
      // again unless the HTML file has actually changed.
      const head = await fetch(url, {{method: 'HEAD', cache: 'no-store'}});
      if (!head.ok) throw new Error(`HTTP ${{head.status}}`);
      const modified = head.headers.get('last-modified');
      if (modified && modified === lastModified) return;

      const response = await fetch(url, {{cache: 'no-store'}});
      if (!response.ok) throw new Error(`HTTP ${{response.status}}`);
      const html = await response.text();
      const updated = new DOMParser().parseFromString(html, 'text/html');
      const newVersion = updated.querySelector('meta[name="dashboard-generated"]')?.content;
      const newSvg = updated.querySelector('svg');

      if (newVersion && newSvg) {{
        if (newVersion !== displayedVersion) {{
          document.querySelector('svg').replaceWith(document.importNode(newSvg, true));
          displayedVersion = newVersion;
          document.querySelector('meta[name="dashboard-generated"]').content = newVersion;
        }}
        lastModified = modified;
      }}
    }} catch (error) {{
      console.warn('Dashboard update failed:', error);
    }} finally {{
      checking = false;
    }}
  }}

  setInterval(checkDashboard, {WEB_POLL_SECONDS * 1000});
</script>
</body>
</html>
"""

    png_buffer = BytesIO()
    fig.savefig(png_buffer, format="png", dpi=EXPORT_DPI, facecolor=BG)

    _atomic_write(os.path.join(EXPORT_DIR, "latest.svg"), inline_svg.encode("utf-8"))
    _atomic_write(os.path.join(EXPORT_DIR, "latest.png"), png_buffer.getvalue())
    _atomic_write(os.path.join(EXPORT_DIR, "latest.html"), html_page.encode("utf-8"))


# ============================================================
# Dashboard refresh
# ============================================================

last_dataset = None
last_filename = None


def update_dashboard(ds, filename, refresh_time=None):
    now = refresh_time if refresh_time is not None else utc_now()

    # Ensure that the times are in chronological order
    times = pd.to_datetime(
        ds["TIME"].values,
        utc=True,
    )

    if len(times) == 0:
        raise ValueError("Dataset contains no timestamps.")

    order = np.argsort(times)
    ds = ds.isel(TIME=order)
    times = times[order]
    
    start_time = now - dt.timedelta(hours=HISTORY_HOURS)

    visible = np.asarray(
        (times >= pd.Timestamp(start_time))
        & (times <= pd.Timestamp(now))
    )

    last_data_time = times[-1].to_pydatetime()

    data, water_depth = extract_velocity(ds)

    # Update all panels
    update_timeseries(times.to_pydatetime(), data, now, visible)
    update_depth_plot(times.to_pydatetime(), water_depth, now)
    update_info_panel(data, water_depth)
    update_polar(data, visible)

    # Determine data freshness
    state, color, age = get_data_status(last_data_time, now)

    status_text.set_text(
        f"● {state}   |   Data age: {max(0, age):.0f} s"
    )
    status_text.set_color(color)

    last_data_text.set_text(
        f"{'Last data point:':<20}"
        f"{format_time(last_data_time)}"
    )
    
    last_refresh_text.set_text(
        f"{'Last refresh:':<22}"
        f"{format_time(now)}"
    )

    next_refresh_text.set_text(
        f"{'Next refresh:':<21}"
        f"{format_time(now + dt.timedelta(seconds=REFRESH_SECONDS))}"
    )

    subtitle.set_text(
        f"{filename}   •   "
        f"Viewing last {HISTORY_HOURS} hours   •   "
        f"Auto-refresh: {REFRESH_SECONDS // 60} min"
    )

    position_wind_text()
    fig.canvas.draw_idle()


def refresh():
    global last_dataset, last_filename

    now = utc_now()

    refresh_wind()
    update_wind_label()

    try:
        ds, filename = load_data()

        update_dashboard(ds, filename, now)

        # Cache only a successfully displayed dataset.
        last_dataset = ds
        last_filename = filename

        print(
            f"[{format_time(now)}] "
            f"Dashboard refreshed: {filename}"
        )

    except Exception as e:
        print(f"Refresh failed: {e}")
        traceback.print_exc()

        # Continue advancing the time axis using cached data
        if last_dataset is not None:
            try:
                update_dashboard(
                    last_dataset,
                    last_filename,
                    now,
                )
            except Exception:
                traceback.print_exc()

        status_text.set_text("● OFFLINE / UPDATE ERROR")
        status_text.set_color(RED)

        subtitle.set_text(f"Update error: {str(e)[:100]}")

        fig.canvas.draw_idle()

    # Publish the most recently rendered state, including an error indicator
    # when telemetry fails. Export failures must not stop monitoring.
    try:
        export_dashboard()
    except Exception as exc:
        print(f"Dashboard export failed: {exc}")
        traceback.print_exc()


# ============================================================
# Application
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="ADCP live current monitor")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Export to output/live/ instead of output/preview/",
    )
    args = parser.parse_args()

    global EXPORT_DIR
    EXPORT_DIR = str(ROOT / "output" / ("live" if args.publish else "preview"))
    print(f"Dashboard export directory: {EXPORT_DIR}")

    plt.show(block=False)
    make_dark_window()
    update_logo_position()
    position_wind_text()

    # Initial refresh
    refresh()

    next_refresh = time.monotonic() + REFRESH_SECONDS

    while plt.fignum_exists(fig.number):
        plt.pause(0.2)

        if time.monotonic() >= next_refresh:
            refresh()
            next_refresh = time.monotonic() + REFRESH_SECONDS


if __name__ == "__main__":
    main()

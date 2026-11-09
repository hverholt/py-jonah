"""Settings for the Hvalfjörður ADCP dashboard."""
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parents[1]

# ADCP telemetry source
INPUT_DIR = r"C:\Users\Nortek1000\Desktop\ADCP\adcp-data\raw\telemetry\live"

# Intermediate and processed data
TXT_FILE = str(ROOT / "data" / "interim" / "latest.txt")
NC_FILE = str(ROOT / "data" / "processed" / "latest.nc")
WIND_HISTORY_FILE = str(ROOT / "data" / "processed" / "wind_history.csv")

# Dashboard output and typography
EXPORT_DIR = ROOT / "output"
PLOT_ASSET_GENERATIONS_TO_KEEP = 3
FONT_FAMILY = "DejaVu Sans"
FONT_FALLBACK = "Arial"
WEB_FONT_REGULAR_PX = 12
WEB_FONT_HEADING_PX = 17

# Overview figures and responsive time-series exports
TIMESERIES_EXPORT_WIDTHS = (10.5, 11.375, 12.25, 13.125, 14.0, 14.875, 15.75, 16.625, 17.5)
TIMESERIES_FIGURE_HEIGHT = 8.0
POLAR_FIGURE_SIZE = (5.8, 5.8)

# Time–range profiles
PROFILE_Y_MODE = "range"  # "range" (m above instrument) or "cell" (cell number)
PROFILE_MAX_TIME_SAMPLES = 360
PROFILE_CORR_THRESHOLD = None
PROFILE_PLOT_SETTINGS = {
    "velocity": {"clim": (-0.15, 0.15), "cmap": "seismic"},
    "amplitude": {"clim": (40, 85), "cmap": "viridis"},
}

# Attribution and logo
MAINTAINER_NAME = "Sindri Bernholt"
MAINTAINER_EMAIL = "sindri@rostrannsoknir.is"
FAVICON_SVG = str(ROOT / "assets" / "logos" / "rost-logo-no-text-50px-green.svg")
LOGO_SVG = str(ROOT / "assets" / "logos" / "rost-logo-icelandic-white.svg")
UNIVERSITY_LOGO_SVG = str(ROOT / "assets" / "logos" / "university-of-iceland-white.svg")

# ADCP measurements
TARGET_DEPTHS = (2, 5, 10)  # metres below surface
AVERAGING_WIDTH = 4.0       # metres, 0 for point values
MIN_DEPTH = 1               # metres below surface
DBAR_PER_METER = 1.0065

# Live monitoring
STALE_AFTER_SECONDS = 300
HISTORY_HOURS = 24
REFRESH_SECONDS = 60
WEB_POLL_SECONDS = 15
DIRECTION_WRAP_THRESHOLD = 200  # degrees
RUNNING_MEAN_SAMPLES = 10
MIN_DIRECTION_SPEED = 0.01  # m/s
MAX_CURRENT_GAP_FACTOR = 2.5

# ODR Hvalfjörður - primary wind station
MOGT_URL = "https://vedur.mogt.is/harbor/index.php"
MOGT_STATION_ID = 1035
MOGT_HARBOR_ID = 19
MOGT_STATION_NAME = "ODR Hvalfjörður"

# Þyrill - fallback for live wind arrow only
VEDUR_URL = "https://api.vedur.is/weather/observations/aws/10min"
WEATHER_STATION_ID = 1685
WEATHER_STATION_NAME = "Þyrill"

# Wind display
WIND_MAX_AGE = 30

# Plot colors and settings
WIND_ARROW_LENGTH = 0.4
WIND_COLOR = "#ffffff"
WIND_PLOT_ALPHA = 0.7
WIND_PLOT_LW = 1.2
RAW_LINE_ALPHA = 0.3
RAW_LINE_LW = 1.2
MEAN_LINE_LW = 1.7
DEPTH_PLOT_LW = 1.4

# ADCP location and basemap
MAP_LAT = 64.393931
MAP_LON = -21.466464
MAP_WIDTH = 400              # metres
MAP_IMAGE_RESOLUTION = 1000   # pixels per side
MAP_OPACITY = 0.8
WMS_URL = "https://gis.natt.is/mapcache/web-mercator/wms"
WMS_LAYERS = ["LMI_Island_einfalt"]

# Dark mode colors
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

# Matplotlib styles
PLOT_STYLE = {
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
}

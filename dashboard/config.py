"""Settings for the Hvalfjörður ADCP dashboard."""
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parents[1]

# ADCP telemetry source
INPUT_DIR = r"C:\Users\Nortek1000\Documents\Nortek\Deployment\Online"

# Intermediate and processed data
TXT_FILE = str(ROOT / "data" / "interim" / "latest.txt")
NC_FILE = str(ROOT / "data" / "processed" / "latest.nc")
WIND_HISTORY_FILE = str(ROOT / "data" / "processed" / "wind_history.csv")

# Dashboard output
EXPORT_DIR = ROOT / "output"
FONT_FAMILY = "DejaVu Sans"
FONT_FALLBACK = "Arial"

# Attribution and logo
MAINTAINER_NAME = "Sindri Bernholt"
MAINTAINER_EMAIL = "sindri@rostrannsoknir.is"
LOGO_SVG = str(ROOT / "assets" / "logos" / "rost-logo-icelandic-white.svg")
LOGO_POSITION = (0.67, 0.975)
LOGO_SIZE = 0.16

# ADCP measurements
TARGET_DEPTHS = (2, 5, 10)  # metres below surface
AVERAGING_WIDTH = 4.0       # metres, 0 for point values
MIN_DEPTH = 1               # metres below surface
DBAR_PER_METER = 1.0065

# Live monitoring
STALE_AFTER_SECONDS = 240
HISTORY_HOURS = 24
REFRESH_SECONDS = 60
WEB_POLL_SECONDS = 15
DIRECTION_WRAP_THRESHOLD = 200  # degrees
RUNNING_MEAN_SAMPLES = 10
RAW_LINE_ALPHA = 0.35
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
WIND_ARROW_LENGTH = 0.32
WIND_COLOR = "#ffffff"
WIND_PLOT_ALPHA = 0.9

# ADCP location and basemap
MAP_LAT = 64.393931
MAP_LON = -21.466464
MAP_WIDTH = 400              # metres
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

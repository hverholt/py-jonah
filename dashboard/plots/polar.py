"""Polar current vectors and optional WMS basemap (one independent figure)."""
import numpy as np
from io import BytesIO
import matplotlib.pyplot as plt
from matplotlib.image import BboxImage
from PIL import Image
from pyproj import Transformer
from .. import config as cfg

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

    # Cardinal labels sit just inside the circle instead of outside it.
    ax.set_thetagrids([0, 90, 180, 270], labels=["N", "E", "S", "W"])
    ax.tick_params(colors=cfg.TEXT, labelsize=11)
    ax.tick_params(axis="x", pad=-19)
    ax.grid(color="white", alpha=0.25, linewidth=0.7)
    ax.spines["polar"].set_color(cfg.GRID)

    for i, (depth, color) in enumerate(zip(cfg.TARGET_DEPTHS, cfg.DEPTH_COLORS)):
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
            zorder=8 + len(cfg.TARGET_DEPTHS) - i,
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

    # White dot covering the arrow origins
    ax.scatter(
        [0], [0],
        s=45,
        color="white",
        edgecolors="none",
        zorder=20,
    )
    
    ax.set_rlabel_position(135)
    for label in ax.get_yticklabels():
        label.set_color(cfg.MUTED)
        label.set_fontsize(12)

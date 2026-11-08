"""Publish the Matplotlib overview as one self-contained HTML file.

The browser sidebar and its empty lazy-initialized tabs are defined in
web/dashboard.html, web/style.css, and web/pages.js. The resulting latest.html
embeds everything so it can be served exactly as before.
"""

import base64
from io import BytesIO
from pathlib import Path
import time

import matplotlib.pyplot as plt

from . import config as cfg


WEB_DIR = Path(__file__).resolve().parent / "web"


def _atomic_write(path, content):
    """Replace a published file only after its contents are fully written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _logo_bounds(view):
    """Determine logo placement in figure fractions if a logo was loaded."""
    artist = view.get("logo_artist")
    if artist is None:
        return None

    # The overview may expose an explicit function to update its logo position.
    update = view.get("update_logo_position")
    if callable(update):
        update()

    fig = view["fig"]
    height_px, width_px = artist.get_array().shape[:2]
    fig_width, fig_height = fig.get_size_inches()
    width = cfg.LOGO_SIZE
    height = width * (height_px / width_px) * (fig_width / fig_height)
    return (cfg.LOGO_POSITION[0], cfg.LOGO_POSITION[1] - height, width, height)


def _figure_svg(view):
    """Render overview as SVG text and embed the original vector logo."""
    fig = view["fig"]
    logo_artist = view.get("logo_artist")
    logo_svg = view.get("logo_svg_bytes")
    bounds = _logo_bounds(view)

    buffer = BytesIO()
    was_visible = logo_artist.get_visible() if logo_artist is not None else False
    if logo_artist is not None:
        logo_artist.set_visible(False)
    try:
        with plt.rc_context({"svg.fonttype": "none", "svg.image_inline": True}):
            fig.savefig(buffer, format="svg", facecolor=cfg.BG)
    finally:
        if logo_artist is not None:
            logo_artist.set_visible(was_visible)

    svg = buffer.getvalue().decode("utf-8")
    start = svg.find("<svg ")
    if start == -1:
        raise ValueError("No SVG element found in exported dashboard")
    svg = svg[start:]
    svg = svg.replace("<svg ", '<svg xml:space="preserve" preserveAspectRatio="none" ', 1)

    text_style = (
        "text, tspan { "
        f"font-family: '{cfg.FONT_FAMILY}', '{cfg.FONT_FALLBACK}', sans-serif !important; "
        "white-space: pre !important; }"
    )
    tag_end = svg.find(">")
    svg = svg[:tag_end + 1] + f'\n<style type="text/css">{text_style}</style>\n' + svg[tag_end + 1:]

    if logo_svg is not None and bounds is not None:
        left, bottom, width, height = bounds
        fig_w, fig_h = fig.get_size_inches() * 72
        x, y = left * fig_w, (1 - bottom - height) * fig_h
        w, h = width * fig_w, height * fig_h
        encoded = base64.b64encode(logo_svg).decode("ascii")
        logo_tag = (
            f'<image id="dashboard-logo" preserveAspectRatio="xMidYMid meet" '
            f'x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'href="data:image/svg+xml;base64,{encoded}" />'
        )
        svg = svg.replace("</svg>", logo_tag + "\n</svg>", 1)
    return svg


def _html_page(svg):
    """Construct the existing navigable, self-contained browser dashboard."""
    html = (WEB_DIR / "dashboard.html").read_text(encoding="utf-8")
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    css += "\n" + (WEB_DIR / "fit.css").read_text(encoding="utf-8")
    js = (WEB_DIR / "pages.js").read_text(encoding="utf-8")
    js += "\n" + (WEB_DIR / "fit.js").read_text(encoding="utf-8")

    colors = {
        "bg": cfg.BG,
        "panel": cfg.PANEL,
        "grid": cfg.GRID,
        "text": cfg.TEXT,
        "muted": cfg.MUTED,
        "cyan": cfg.CYAN,
        "font": f'"{cfg.FONT_FAMILY}"',
        "font-fallback": f'"{cfg.FONT_FALLBACK}"',
    }
    theme = ":root {\n" + "".join(f"  --{name}: {value};\n" for name, value in colors.items()) + "}\n"
    return (
        html.replace("__DASHBOARD_VERSION__", str(time.time_ns()))
        .replace("__INLINE_STYLE__", theme + css)
        .replace("__INLINE_SVG__", svg)
        .replace("__INLINE_SCRIPT__", js.replace("__WEB_POLL_MS__", str(cfg.WEB_POLL_SECONDS * 1000)))
    )


def export_dashboard(view, export_dir):
    """Write only latest.html for the Overview page.

    Required ``view`` key: ``fig``. Optional keys: ``logo_artist`` and
    ``logo_svg_bytes``. Does not generate plots for unopened pages.
    """
    svg = _figure_svg(view)
    html = _html_page(svg)

    output = Path(export_dir)
    _atomic_write(output / "latest.html", html.encode("utf-8"))

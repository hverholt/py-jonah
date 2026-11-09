"""Publish two scientific SVGs and HTML panels in one self-contained page."""
import base64
import html
from io import BytesIO
from pathlib import Path
from matplotlib.legend import Legend
import time

import matplotlib.pyplot as plt

from . import config as cfg
from .plots import profiles

WEB_DIR = Path(__file__).resolve().parent / "web"


def _atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _svg(fig, css_class=""):
    buffer = BytesIO()
    with plt.rc_context({"svg.fonttype": "none", "svg.image_inline": True}):
        extra_legends = [c for ax in fig.axes for c in ax.get_children() if isinstance(c, Legend)]
        fig.savefig(buffer, format="svg", facecolor="none", bbox_inches="tight", pad_inches=0.08, bbox_extra_artists=extra_legends)
    source = buffer.getvalue().decode("utf-8")
    idx = source.find("<svg ")
    if idx == -1:
        raise ValueError("Matplotlib returned SVG without an <svg> element")
    return source[idx:].replace(
        "<svg ", f'<svg role="img" class="{css_class}" preserveAspectRatio="xMidYMid meet" ', 1
    )



def _timeseries_svgs(fig):
    """Provide axes with different physical widths for different panel shapes.

    CSS selects the best aspect ratio. Unlike SVG stretching, this keeps fonts
    and labels correctly proportioned while filling wide panels.
    """
    original_size = fig.get_size_inches().copy()
    # Nine widths spanning the original 10.5–17.5-inch range.
    # Keep these names in sync with the @container rules in web/style.css.
    variants = (
        ("size-1", 10.500),
        ("size-2", 11.375),
        ("size-3", 12.250),
        ("size-4", 13.125),
        ("size-5", 14.000),
        ("size-6", 14.875),
        ("size-7", 15.750),
        ("size-8", 16.625),
        ("size-9", 17.500),
    )
    try:
        return "".join(
            _render_timeseries_width(fig, width, name, original_size[1])
            for name, width in variants
        )
    finally:
        fig.set_size_inches(original_size, forward=False)


def _render_timeseries_width(fig, width, name, height):
    fig.set_size_inches(width, height, forward=False)
    return _svg(fig, f"timeseries-variant timeseries-{name}")



def _logo_tag():
    path = Path(cfg.LOGO_SVG)
    if not path.is_file():
        return '<span class="footer-wordmark">RÖST</span>'
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'<img class="footer-logo" alt="Röst" src="data:image/svg+xml;base64,{encoded}">'


def _escape(value):
    return html.escape(str(value), quote=True)


def _measurements_html(view):
    rows = []
    for depth, speed, color in view.get("measurements", []):
        rows.append(
            '<div class="measurement-row">'
            f'<span class="measurement-name" style="color:{_escape(color)}">'
            f'{_escape(depth)} speed</span>'
            f'<span class="measurement-value">{_escape(speed)}</span>'
            '</div>'
        )
    rows.append(
        '<div class="measurement-row measurement-depth">'
        '<span class="measurement-name">Water depth</span>'
        f'<span class="measurement-value">{_escape(view.get("water_depth", "—"))}</span>'
        '</div>'
    )
    wind_label, wind_value = view.get("wind_measurement", ("Wind", "—"))
    rows.append(
        '<div class="measurement-row measurement-wind">'
        f'<span class="measurement-name">{_escape(wind_label)}</span>'
        f'<span class="measurement-value">{_escape(wind_value)}</span>'
        '</div>'
    )
    return ''.join(rows)


def _polar_legend_html():
    items = [
        f'<li><span class="legend-arrow" style="color:{_escape(color)}"></span>'
        f'<span>{depth:g} m</span></li>'
        for depth, color in zip(cfg.TARGET_DEPTHS, cfg.DEPTH_COLORS)
    ]
    items.append(
        f'<li><span class="legend-arrow legend-wind" '
        f'style="color:{_escape(cfg.WIND_COLOR)}"></span><span>Wind</span></li>'
    )
    return '<ul class="polar-legend" aria-label="Current and wind legend">' + ''.join(items) + '</ul>'


def _profile_html(view, plot_type="velocity"):
    ds = view.get("profile_dataset")
    if ds is None:
        return '<div class="empty-state">No profile data available.</div>'

    fig = None
    try:
        fig = profiles.create_figure(ds, plot_type=plot_type)
        return _svg(fig)
    except Exception as exc:
        print(f"{plot_type.capitalize()} profiles unavailable: {exc}")
        return f'<div class="empty-state">{plot_type.capitalize()} profiles unavailable.</div>'
    finally:
        if fig is not None:
            plt.close(fig)


def _html_page(view):
    doc = (WEB_DIR / "dashboard.html").read_text(encoding="utf-8")
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    js = (WEB_DIR / "pages.js").read_text(encoding="utf-8")
    colors = {
        "bg": cfg.BG, "panel": cfg.PANEL, "grid": cfg.GRID,
        "text": cfg.TEXT, "muted": cfg.MUTED, "cyan": cfg.CYAN,
        "green": cfg.GREEN, "orange": cfg.ORANGE, "red": cfg.RED,
        "font": f'"{cfg.FONT_FAMILY}"',
        "font-fallback": f'"{cfg.FONT_FALLBACK}"',
    }
    theme = ':root {\n' + ''.join(f'--{name}: {value};\n' for name, value in colors.items()) + '}\n'
    status = view.get("status", {})
    state = status.get("state", "INITIALIZING")
    age = status.get("age")
    age_text = f"{age:.0f} s old" if age is not None else ""
    substitutions = {
        '__SVG_PROFILES__': _profile_html(view, 'velocity'),
        '__SVG_AMPLITUDE__': _profile_html(view, 'amplitude'),
        '__DASHBOARD_VERSION__': str(time.time_ns()),
        '__INLINE_STYLE__': theme + css,
        '__INLINE_SCRIPT__': js.replace('__WEB_POLL_MS__', str(cfg.WEB_POLL_SECONDS * 1000)),
        '__SVG_TIMESERIES__': _timeseries_svgs(view['figures']['timeseries']),
        '__SVG_POLAR__': _svg(view['figures']['polar']),
        '__STATUS_STATE__': _escape(state),
        '__STATUS_AGE__': _escape(age_text),
        '__STATUS_COLOR__': _escape(status.get('color', cfg.ORANGE)),
        '__LAST_DATA__': _escape(status.get('last_data', '—')),
        '__LAST_REFRESH__': _escape(status.get('last_refresh', '—')),
        '__NEXT_REFRESH__': _escape(status.get('next_refresh', '—')),
        '__MEASUREMENTS__': _measurements_html(view),
        '__POLAR_LEGEND__': _polar_legend_html(),
        '__LOGO__': _logo_tag(),
        '__MAINTAINER__': _escape(cfg.MAINTAINER_NAME),
        '__MAINTAINER_EMAIL__': _escape(cfg.MAINTAINER_EMAIL),
    }
    for key, value in substitutions.items():
        doc = doc.replace(key, value)
    return doc


def export_dashboard(view, export_dir):
    """Write latest.html only, preserving preview/live paths."""
    _atomic_write(
        Path(export_dir) / "latest.html",
        _html_page(view).encode("utf-8"),
    )

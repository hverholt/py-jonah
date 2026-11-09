"""Export HTML and lazily loaded Matplotlib SVG fragments."""
import base64
import html
import shutil
import time
from io import BytesIO
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.legend import Legend

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
    variants = enumerate(cfg.TIMESERIES_EXPORT_WIDTHS, start=1)
    try:
        return "".join(
            _render_timeseries_width(fig, width, f"size-{i}", original_size[1])
            for i, width in variants
        )
    finally:
        fig.set_size_inches(original_size, forward=False)


def _render_timeseries_width(fig, width, name, height):
    fig.set_size_inches(width, height, forward=False)
    return _svg(fig, f"timeseries-variant timeseries-{name}")


def _timeseries_variant_css(height):
    """Select the closest pre-rendered time-series width for each panel shape."""
    widths = cfg.TIMESERIES_EXPORT_WIDTHS
    rules = [
        ".timeseries-plot > .timeseries-variant { display: none; }",
        ".timeseries-plot > .timeseries-size-1 { display: block; }",
    ]
    for i in range(1, len(widths)):
        threshold = (widths[i - 1] + widths[i]) / (2 * height)
        rules.append(
            f"@container (min-aspect-ratio: {threshold:.3f}) {{ "
            f".timeseries-plot > .timeseries-size-{i} {{ display: none; }} "
            f".timeseries-plot > .timeseries-size-{i + 1} {{ display: block; }} }}"
        )
    return "\n".join(rules)



def _logo_tag(svg_path=None, alt="Röst"):
    path = Path(cfg.LOGO_SVG if svg_path is None else svg_path)

    if not path.is_file():
        if svg_path is None:
            return '<span class="footer-wordmark">RÖST</span>'
        raise FileNotFoundError(f"Logo not found: {path}")

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return (
        f'<img class="footer-logo" alt="{html.escape(alt, quote=True)}" '
        f'src="data:image/svg+xml;base64,{encoded}">'
    )


def _favicon_url():
    path = Path(cfg.FAVICON_SVG)
    if not path.is_file():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


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


def _html_page(view, plot_paths, version):
    doc = (WEB_DIR / "dashboard.html").read_text(encoding="utf-8")
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    js = (WEB_DIR / "pages.js").read_text(encoding="utf-8")
    colors = {
        "bg": cfg.BG, "panel": cfg.PANEL, "grid": cfg.GRID,
        "text": cfg.TEXT, "muted": cfg.MUTED,
        "font": f'"{cfg.FONT_FAMILY}"',
        "font-fallback": f'"{cfg.FONT_FALLBACK}"',
        "font-regular": f"{cfg.WEB_FONT_REGULAR_PX}px",
        "font-heading": f"{cfg.WEB_FONT_HEADING_PX}px",
    }
    theme = ':root {\n' + ''.join(f'--{name}: {value};\n' for name, value in colors.items()) + '}\n'
    status = view.get("status", {})
    state = status.get("state", "INITIALIZING")
    age = status.get("age")
    age_text = f"{age:.0f} s old" if age is not None else ""
    substitutions = {
        '__PLOT_POLAR__': plot_paths['polar'],
        '__PLOT_TIMESERIES__': plot_paths['timeseries'],
        '__PLOT_PROFILES__': plot_paths['profiles'],
        '__PLOT_AMPLITUDE__': plot_paths['amplitude'],
        '__DASHBOARD_VERSION__': version,
        '__INLINE_STYLE__': theme + css + "\n" + _timeseries_variant_css(
            view['figures']['timeseries'].get_size_inches()[1]
        ),
        '__INLINE_SCRIPT__': js.replace('__WEB_POLL_MS__', str(cfg.WEB_POLL_SECONDS * 1000)),
        '__STATUS_STATE__': _escape(state),
        '__STATUS_AGE__': _escape(age_text),
        '__STATUS_COLOR__': _escape(status.get('color', cfg.ORANGE)),
        '__LAST_DATA__': _escape(status.get('last_data', '—')),
        '__LAST_REFRESH__': _escape(status.get('last_refresh', '—')),
        '__NEXT_REFRESH__': _escape(status.get('next_refresh', '—')),
        '__MEASUREMENTS__': _measurements_html(view),
        '__POLAR_LEGEND__': _polar_legend_html(),
        '__LOGO__': _logo_tag(),
        '__UNIVERSITY_LOGO__': _logo_tag(cfg.UNIVERSITY_LOGO_SVG, 'University of Iceland'),
        '__FAVICON__': _favicon_url(),
        '__MAINTAINER__': _escape(cfg.MAINTAINER_NAME),
        '__MAINTAINER_EMAIL__': _escape(cfg.MAINTAINER_EMAIL),
    }
    for key, value in substitutions.items():
        doc = doc.replace(key, value)
    return doc


def export_dashboard(view, export_dir):
    """Publish plot fragments before atomically updating the HTML entry point."""
    export_dir = Path(export_dir)
    version = str(time.time_ns())
    assets_dir = export_dir / "plots" / version

    renderers = {
        "polar": lambda: _svg(view["figures"]["polar"]),
        "timeseries": lambda: _timeseries_svgs(view["figures"]["timeseries"]),
        "profiles": lambda: _profile_html(view, "velocity"),
        "amplitude": lambda: _profile_html(view, "amplitude"),
    }

    plot_paths = {}
    for name, render in renderers.items():
        filename = f"{name}.html"
        _atomic_write(assets_dir / filename, render().encode("utf-8"))
        plot_paths[name] = f"plots/{version}/{filename}"

    _atomic_write(
        export_dir / "latest.html",
        _html_page(view, plot_paths, version).encode("utf-8"),
    )

    generations = sorted(
        (path for path in (export_dir / "plots").iterdir()
         if path.is_dir() and path.name.isdigit()),
        key=lambda path: int(path.name),
    )
    for old in generations[:-cfg.PLOT_ASSET_GENERATIONS_TO_KEEP]:
        try:
            shutil.rmtree(old)
        except OSError as exc:
            print(f"Could not remove old plot assets {old}: {exc}")

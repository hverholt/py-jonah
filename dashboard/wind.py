"""ODR wind history and Þyrill fallback for live wind observations.

Only ODR Hvalfjörður is used for historical wind plots. Þyrill is used
solely when there is no sufficiently recent ODR reading for the live arrow.
"""

from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from . import config as cfg


_history = pd.DataFrame(columns=["time", "speed", "direction"])
_cache_loaded = False


def clean_wind_observations(df):
    """Return valid UTC observations (speed in m/s, FROM direction in degrees)."""
    df = df.copy()
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df["speed"] = pd.to_numeric(df["f"], errors="coerce")
    df["direction"] = pd.to_numeric(df["d"], errors="coerce")
    df = df.dropna(subset=["time", "speed", "direction"])
    return df.loc[
        (df["speed"] >= 0) & df["direction"].between(0, 360),
        ["time", "speed", "direction"],
    ]


def get_mogt_wind_history():
    """Retrieve and combine ODR Hvalfjörður's newest=1 and back=1 pages."""
    frames = []
    for mode in ("newest", "back"):
        try:
            response = requests.get(
                cfg.MOGT_URL,
                params={
                    "action": "ReadingsDrillDown",
                    "harborid": cfg.MOGT_HARBOR_ID,
                    "stationid": cfg.MOGT_STATION_ID,
                    mode: 1,
                },
                timeout=15,
            )
            response.raise_for_status()
            table = next(
                table for table in pd.read_html(StringIO(response.text))
                if any("Vindur" in str(column) for column in table.columns)
            ).copy()
            if len(table.columns) != 5:
                raise ValueError("Unexpected ODR wind table format")
            table.columns = ["time", "f", "fg", "d", "t"]
            table["time"] = pd.to_datetime(
                table["time"], format="%H:%M %d.%m.%Y",
                utc=True, errors="coerce",
            )
            frames.append(clean_wind_observations(table))
        except Exception as exc:
            print(f"ODR {mode}=1 unavailable: {exc}")

    if not frames:
        raise RuntimeError("ODR wind history unavailable")
    return (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates("time", keep="last")
        .sort_values("time")
        .reset_index(drop=True)
    )


def get_vedur_latest():
    """Retrieve Þyrill's latest reading, for the live arrow only."""
    response = requests.get(
        f"{cfg.VEDUR_URL}/latest",
        params={"station_id": cfg.WEATHER_STATION_ID, "parameters": "basic"},
        timeout=20,
    )
    response.raise_for_status()
    df = pd.DataFrame(response.json())
    if "station" in df.columns:
        df = df.loc[df["station"].astype(str) == str(cfg.WEATHER_STATION_ID)]
    return clean_wind_observations(df)


def _load_cache():
    global _cache_loaded, _history
    if _cache_loaded:
        return
    _cache_loaded = True
    path = Path(cfg.WIND_HISTORY_FILE)
    if not path.is_file():
        return
    try:
        cached = pd.read_csv(path)
        # Legacy cache files may also contain Þyrill readings.
        if "station" in cached.columns:
            cached = cached.loc[cached["station"] == cfg.MOGT_STATION_NAME]
        cached["time"] = pd.to_datetime(cached["time"], utc=True, errors="coerce")
        cached["speed"] = pd.to_numeric(cached["speed"], errors="coerce")
        cached["direction"] = pd.to_numeric(cached["direction"], errors="coerce")
        _history = cached[["time", "speed", "direction"]].dropna()
        _history = _history.sort_values("time").drop_duplicates("time", keep="last")
    except Exception as exc:
        print(f"Wind cache unavailable: {exc}")


def refresh_wind(now=None):
    """Update ODR history and choose the most recent valid live reading.

    Returns a dictionary with ``data``, ``error`` and ``history`` keys for
    app.py and plots/overview.py. A failed request keeps any cached ODR data.
    """
    global _history
    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")

    _load_cache()
    try:
        recent = get_mogt_wind_history()
        combined = (
            pd.concat([_history, recent], ignore_index=True)
            if not _history.empty else recent
        )
        _history = (combined.drop_duplicates("time", keep="last")
                    .sort_values("time"))
        _history = _history.loc[
            _history["time"].between(
                now - pd.Timedelta(hours=cfg.HISTORY_HOURS + 24),
                now + pd.Timedelta(minutes=5),
            )
        ].reset_index(drop=True)

        path = Path(cfg.WIND_HISTORY_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        _history.to_csv(temp, index=False)
        temp.replace(path)
    except Exception as exc:
        print(f"ODR wind history unavailable: {exc}")

    live = None
    if not _history.empty:
        latest = _history.iloc[-1]
        age_minutes = (now - latest["time"]).total_seconds() / 60
        if -5 <= age_minutes <= cfg.WIND_MAX_AGE:
            live = {
                "speed": float(latest["speed"]),
                "direction": float(latest["direction"]),
                "time": latest["time"],
                "station": cfg.MOGT_STATION_NAME,
            }

    if live is None:
        try:
            fallback = get_vedur_latest()
            if not fallback.empty:
                latest = fallback.sort_values("time").iloc[-1]
                age_minutes = (now - latest["time"]).total_seconds() / 60
                if -5 <= age_minutes <= cfg.WIND_MAX_AGE:
                    live = {
                        "speed": float(latest["speed"]),
                        "direction": float(latest["direction"]),
                        "time": latest["time"],
                        "station": cfg.WEATHER_STATION_NAME,
                    }
        except Exception as exc:
            print(f"Þyrill wind unavailable: {exc}")

    return {
        "data": live,
        "error": None if live is not None else "No recent wind observations",
        "history": _history.copy(),
    }


def wind_plot_series(now, history=None):
    """Return historical ODR wind on a 10-minute grid, with gaps as NaNs.

    If no ODR observations exist, return an empty DataFrame. Þyrill is never
    included in this time series.
    """
    if history is None:
        history = _history
    now = pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    start = now - pd.Timedelta(hours=cfg.HISTORY_HOURS)
    recent = history.loc[history["time"].between(start, now)].copy()
    if recent.empty:
        return pd.DataFrame()

    recent["bucket"] = recent["time"].dt.round("10min")
    values = (
        recent.sort_values("time")
        .drop_duplicates("bucket", keep="last")
        .set_index("bucket")[["speed", "direction"]]
    )
    grid = pd.date_range(start.floor("10min"), now.floor("10min"),
                         freq="10min", tz="UTC")
    return values.reindex(grid)

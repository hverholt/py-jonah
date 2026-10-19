# Hvalfjörður ADCP Monitoring

Live monitoring and visualization of ocean currents measured by a **Nortek Signature1000 ADCP** at the **Miðsandur pier, Hvalfjörður, Iceland**, for **Röst sjávarrannsóknasetur**.

The project processes ADCP telemetry, converts it to NetCDF, and displays current velocity at selected depths in a continuously updating dashboard. The dashboard includes time series, current-direction vectors, water depth, and nearby wind observations.

## Dashboard

Run the dashboard locally without updating the public website:

```cmd
python plot_adcp_dashboard.py
```

To publish updated dashboard files to the live website:

```cmd
python plot_adcp_dashboard.py --publish
```

Without `--publish`, output is written to `dashboard_preview/`. With `--publish`, output is written to `dashboard/`. Both modes export `latest.html`, `latest.svg`, and `latest.png`.

## Website

From the project directory, start a local server:

```cmd
python -m http.server 8000 --bind 127.0.0.1 --directory dashboard
```

To share the website publicly using Tailscale Funnel:

```cmd
tailscale funnel --bg 8000
```

View the published dashboard at the Funnel address followed by `/latest.html`. The dashboard and local server must remain running for live access.

## Configuration

Edit the configuration section near the top of `plot_adcp_dashboard.py` to set telemetry paths, measurement depths, refresh intervals, and display options. The plotting script uses the telemetry processing tools in `source/telemetry2netcdf.py` from the companion `py-adcp-toolbox` repository.

The dashboard requires Python and its imported scientific/plotting packages, as well as access to the incoming Nortek telemetry files.

## Maintainer

Developed and maintained by **Sindri Bernholt**  
Email: [sindri@rostrannsoknir.is](mailto:sindri@rostrannsoknir.is)

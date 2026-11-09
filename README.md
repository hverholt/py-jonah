# py-jonah

Python application for generating and continuously updating a live dashboard of acoustic Doppler current profiler (ADCP) measurements. It combines incoming telemetry, converts the data to NetCDF using [adcp-py-toolbox](https://github.com/hverholt/adcp-py-toolbox), and visualizes horizontal current velocities at selected depths below the sea surface.

The dashboard displays velocity time series, current direction and speed, pressure-derived water depth, nearby wind observations, and velocity and amplitude profiles. It produces a standalone, self-contained HTML dashboard with embedded Matplotlib plots that can be served through a web browser.

Currently used to monitor a **Nortek Signature1000 ADCP** at **Miðsandur pier, Hvalfjörður, Iceland**, for **Röst Marine Research Center** (https://www.rostrannsoknir.is).

## Installation

Install Python and Git, then install the dependencies:

```cmd
python -m pip install -r requirements.txt
```

For `adcp-py-toolbox` installation, see its [GitHub repository](https://github.com/hverholt/adcp-py-toolbox).

## Usage

Run the dashboard in preview mode:

```cmd
python run_dashboard.py
```

Or continuously update the live dashboard:

```cmd
python run_dashboard.py --live
```

Preview and live files are written to `output/preview/` and `output/live/`, respectively. Each contains a single `latest.html` file, including the Overview, Velocity profiles, and Amplitude profiles pages.

## Web access

Serve the live dashboard locally:

```cmd
python -m http.server 8000 --bind 127.0.0.1 --directory output/live
```

And optionally expose the server using Tailscale Funnel:

```cmd
tailscale funnel --bg 8000
```

Open `/latest.html` at the server address. The dashboard updates automatically while running in live mode, and the browser checks for refreshed content every 15 seconds (configurable).

## Configuration

Configure the telemetry input directory, target depths, refresh intervals, wind stations, profile color limits, and display settings in `dashboard/config.py`.

## Collaboration

Developed in collaboration with the **University of Iceland** and **Röst Marine Research Center** (https://www.rostrannsoknir.is).

## Maintainer

Developed and maintained by **Sindri Bernholt**  
[sindri@rostrannsoknir.is](mailto:sindri@rostrannsoknir.is)

# py-jonah

Python application for generating and continuously updating a live dashboard of acoustic Doppler current profiler (ADCP) measurements. It combines incoming telemetry, converts the data to NetCDF using [adcp-py-toolbox](https://github.com/hverholt/adcp-py-toolbox), and visualizes horizontal current velocities at selected depths below the sea surface.

The dashboard displays velocity time series, current direction and speed, pressure-derived water depth, and nearby wind observations. It produces a live Matplotlib display and standalone HTML, SVG, and PNG outputs that can be served through a web browser.

Currently used to monitor a **Nortek Signature1000 ADCP** at **Miðsandur pier, Hvalfjörður, Iceland**, for **Röst Marine Research Center** (https://www.rostrannsoknir.is).

## Installation

Install Python and Git, then install the dependencies:

```cmd
python -m pip install -r requirements.txt
```

For `adcp-py-toolbox` installation, see its [GitHub repository](https://github.com/hverholt/adcp-py-toolbox).

The application uses Matplotlib's Qt backend and requires a graphical desktop environment.

## Usage

Run the dashboard in preview mode:

```cmd
python plot_adcp_dashboard.py
```

Publish updated dashboard files:

```cmd
python plot_adcp_dashboard.py --publish
```

Preview and published files are written to `output/preview/` and `output/live/`, respectively. Each contains `latest.html`, `latest.svg`, and `latest.png`.

## Web access

Serve the published dashboard locally:

```cmd
python -m http.server 8000 --bind 127.0.0.1 --directory output/live
```

Optionally expose the server using Tailscale Funnel:

```cmd
tailscale funnel --bg 8000
```

Open `/latest.html` at the server address. The dashboard automatically refreshes its outputs while running.

## Configuration

Configure the telemetry input directory, target depths, refresh intervals, and display settings near the top of `plot_adcp_dashboard.py`.

## Collaboration

Developed in collaboration with the **University of Iceland** and **Röst Marine Research Center** (https://www.rostrannsoknir.is).

## Maintainer

Developed and maintained by **Sindri Bernholt**  
[sindri@rostrannsoknir.is](mailto:sindri@rostrannsoknir.is)

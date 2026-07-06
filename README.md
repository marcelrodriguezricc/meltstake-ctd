# Melt Stake CTD Recorder - by Marcel Rodriguez-Riccelli

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Layout: src](https://img.shields.io/badge/layout-src-informational)
![Platform: Raspberry%20Pi](https://img.shields.io/badge/platform-Raspberry%20Pi-C51A4A)
![OS: Linux](https://img.shields.io/badge/os-Linux-FCC624)

Controller/data handler for integrating a stereo pair of **Deepwater Exploration stellarHD** cameras into the Melt Stake system, with additional tools for 3D Particle Tracking Velocimetry (PTV). 

## Requirements

- Hardware: Xylem Aandreaa 5990 Conductivity Sensor
- Python **3.11+** (project currently uses Python 3.11.x)
- Target OS: **Debian 13 (Trixie) Lite** (Raspberry Pi)
- Tested on: **Debian 13 (Trixie) Lite** (Raspberry Pi)

## Project Layout

This repo uses a **src/** layout:

- Package code: `src/meltstake_ctd/`
- Config files: `configs/`
- Recorded data: `data/` (created at runtime unless different directory is specified)
- Aandreaa 5990 documentation: `docs/`
- Shell scripts for run and setup on Linux: `scripts/`
- Secondary programs: `tools/`
- Tests: `tests/`
- Computer-aided design assets for physical integration: `cad-assets/`

## Installation

From the repo root:

```bash
sudo ./meltstake-ptv/scripts/setup.sh
```

OR

```bash
sudo apt update
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
```

## Usage

(Linux Only) Run the bash script entrypoint from the home directory of the Raspberry Pi:

```bash
sudo ~/meltstake-ctd/scripts/run.sh
```

OR

(Mac or Linux) Run the package entrypoint from the repo root:

```bash
source .venv/bin/activate
python -m meltstake_ctd
```

OR

(Raspberry Pi Only) Have the package run automatically on startup from service script in `scripts/ctd.py` (included in setup of [Melt Stake control software](https://github.com/marcelrodriguezricc/meltstake)).

To stop:
```bash
sudo systemctl stop ctd
```

To restart:
```bash
sudo systemctl restart ctd
```

If you prefer not to install the package, you can run using `PYTHONPATH`:

```bash
PYTHONPATH=src python -m meltstake_ctd
```

After initialization, press Enter to begin capture. While capturing, entering "s", "quit", "exit", "q", "stop" will terminate the deployment.

### Arguments

The CLI typically accepts the following arguments:

- `debug`: Prints all logged lines to console for debugging.

- `config`: Filename of configuration file (under `configs/`), e.g. `--config config.toml`, if none specified defaults to `default_config.toml`.

- `data`: Path where data, logs, and other files created at runtime will be stored (default: ROOT/data).


Example: 
```bash
sudo ~/meltstake-ctd/scripts/run.sh --debug --config default_config --data ~/meltstake-ctd/data
```

Config lookup behavior is intended to support filename only (under `configs/`), e.g. `--config config.toml`.

## License

MIT — see [`LICENSE`](LICENSE).
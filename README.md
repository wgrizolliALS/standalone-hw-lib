# Standalone-HW-Scripts

A local, standalone system for acquiring and recording waveform data from multiple hardware instruments.

## Overview

This project provides direct, local data acquisition and recording capabilities for hardware instruments, complementing EPICS by handling waveform data storage that EPICS cannot manage directly. It does not require network connectivity or external services.
# Standalone-HW-Scripts

A local, standalone system for acquiring and recording waveform data from multiple hardware instruments.

## Overview

This project provides direct, local data acquisition and recording capabilities for hardware instruments, complementing EPICS by handling waveform data storage that EPICS cannot manage directly. It does not require network connectivity or external services.

## Supported Hardware

- **LabJack T8** — Multi-channel analog/digital I/O
- **Keithley** — Precision measurement instruments

## Key Features

- Direct local hardware control using Ophyd
- Real-time data acquisition and streaming
- Waveform recording and storage
- Data visualization with Plotly
- Multi-instrument support

## Project Structure

```
Standalone-HW-Scripts/
├── src/
│   ├── ophyd_local_labjack.py      # LabJack device interface
│   └── ophyd_local_keithley.py     # Keithley device interface
├── labjack_examples/               # Example scripts for LabJack
└── keithley_examples/              # Example scripts for Keithley
```

## Getting Started

### Requirements


All other dependencies (Ophyd, Bluesky, LabJack-LJM, etc.) are managed automatically via `pyproject.toml`.

### Installation

To install the package in **editable mode** (recommended for development), run the following from the project root:

```bash
pip install -e .
```

### Basic Usage

See example scripts in:
- `labjack_examples/` for LabJack data acquisition
- `keithley_examples/` for Keithley measurements

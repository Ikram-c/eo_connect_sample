
# EO Connect

EO Connect is a modular Python application that provides a programmatic interface to the Copernicus Data Space Ecosystem (CDSE). It enables users to discover and query the availability of Earth Observation satellite imagery (Sentinel-1, Sentinel-2, and Sentinel-3) based on geographic coordinates, temporal windows, and cloud-cover thresholds.

The application offers both a Command Line Interface (CLI) for pipeline automation and a PyQt6 Graphical User Interface (GUI) for interactive use.

## Background

The Copernicus Data Space Ecosystem (CDSE) is an initiative by the European Space Agency (ESA) that provides access to Earth observation data, replacing older legacy systems with modern data cube approaches and application programming interfaces (APIs) such as STAC and OData. Access to Copernicus Sentinel data operates on a free and open basis, supporting decision-making across economic, environmental, and societal dimensions.

## Features

- **Multi-Modal Interfaces:** Interact via a desktop GUI or a scriptable CLI.
- **Batch Processing:** Upload a CSV of coordinates and target dates to query thousands of locations in chunks.
- **Spatial Buffering:** Calculates bounding boxes accounting for Earth's curvature.
- **Resilient Networking:** Built-in retry logic handling transient API errors and rate-limiting from the CDSE servers.
- **Config-Driven Architecture:** All API endpoints, mathematical constants, and default parameters are centralized in a `config.yaml` file.
- **Secure Authentication:** Supports OAuth2 Keycloak token generation via environment variables.

## Prerequisites

- **Python:** Version 3.9 or higher.
- **CDSE Account:** A registered account at [dataspace.copernicus.eu](https://dataspace.copernicus.eu) is required to avoid severe rate limits.

## Installation

Clone the repository and navigate to the root directory:

```bash
git clone https://github.com/yourusername/eo_connect_project.git
cd eo_connect_project
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

Configure credentials via environment variables:

```bash
export CDSE_USERNAME="your_email@example.com"
export CDSE_PASSWORD="your_password"
```

## Usage

Run all commands from the root directory (`eo_connect_project/`).

### Launching the GUI

Start the desktop application:

```bash
python -m src.eo_connect.gui
```

### Using the CLI

View available arguments:

```bash
python -m src.eo_connect.cli --help
```

**Single Query Example:**

Query Sentinel-2 imagery near Amsterdam (52.0 N, 4.5 E) on July 16, 2025:

```bash
python -m src.eo_connect.cli query \
    --lat 52.0 \
    --lon 4.5 \
    --date "2025-07-16T12:00" \
    --collections sentinel-2 \
    --cloud-cover 30.0 \
    --buffer-days 2 \
    --buffer-km 50.0 \
    --output result.csv
```

**Batch Query Example:**

Process a CSV file containing Start latitude, Start longitude, Start date, and Start time:

```bash
python -m src.eo_connect.cli batch data/voyages.csv \
    --collections sentinel-1 sentinel-2 \
    --buffer-days 1 \
    --output batch_results.csv
```

## Configuration

Modify the `config.yaml` located at the project root to adjust API endpoints, query limits, spatial geometry constants, or default GUI parameters.

## Directory Structure

```plaintext
eo_connect_project/
├── config.yaml
├── requirements.txt
└── src/
    └── eo_connect/
        ├── __init__.py
        ├── cli.py
        ├── client.py
        ├── config.py
        ├── gui.py
        ├── models.py
        └── query.py
```

## References

Munteanu, A. (2024). Data Cubes and Cloud-Native Environments for Earth Observation: An Overview. *Scalable Computing: Practice and Experience, 25*(6). https://doi.org/10.12694/scpe.v25i6.4999

Sawyer, G., Mamais, E., & Papadakis, D. (2022). The Six Dimensions of Value Associated to the use of Copernicus Sentinel Data: Key Findings From the Sentinel Benefits Study. *Frontiers in Environmental Science, 10*. https://doi.org/10.3389/fenvs.2022.804862
EO Connect README.md
Displaying EO Connect README.md.
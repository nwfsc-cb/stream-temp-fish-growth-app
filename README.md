# Stream Temp and Fish Growth App

A **Posit Shiny for Python** web application designed for interactive stream temperature and fish growth data plotting. The application enables users to select Hydrologic Unit Codes (HUCs), fetch stream temperature model projections, process  decadal time series across seasons and view projections for fish growth based on stream temperature. It uses data from the riverscapes data exchange https://data.riverscapes.net/pt/streamtemp to download the data from the site or using this app you need a free riverscapes account.


## Features

- **Interactive HUC6 Downloader**: Map-based spatial selection interface to dowload data by HUC6 region
- **Stream temperature plots**: Analyze stream temperature data plotted on interactive maps organzied by decadal seasonal analysis. 
- **Fish growth modeling**: Integrated polynomial growth model that translates water temperature into specific growth rate metrics for 10-gram Redband Trout
- **Flowline Overlays & Spatial Inspection**: Toggleable stream channel overlays 
- **CSV Data Export**: CSV generation by HUC12
- **Patch-Level Analysis**: See means and variances of fish growth for an upstream patch of any given COMID within a HUC12


## Repository Structure
```
- app.py                  # Main Shiny application 
- downloader.py           # Module handling HUC dataset acquisition using the riverscapes API
- sorter.py               # Reach Contributing Area (COMID) processing & visualization
- sorter12.py             # HUC12 boundary spatial processing module
- filterer.py             # Data extraction & aggregation engine for CSV exports
- temp_to_growth.py       # Polynomial thermal-to-fish-growth transformation model
- dictionaries.py         # Mappings for various dictionaries used by the app
- fishtable.csv           # Empirical temperature vs. fish growth rate data
- single_huc_tab.py       # Patch-level analysis and statistics
- geopackages             # Folder containing the combined geopackages to map out HUC6 outlines
- pydex                   # riverscapes pydex file for acessing their API
- rsxml                   # Riverscapes xml (can also be installed via pip) to acess their API
```
## Usage
- Clone the repo to your local machine and make sure all the files are in a folder togeter
- Install `pixi` to manage package installation.
    - Python Installation (pip):\
    `pip install pixi`
    - Source Installation (MacOS & Linux):\
    `curl -fsSL https://pixi.sh/install.sh | bash`
    - Source Installation (Windows):\
    `powershell -ExecutionPolicy ByPass -c "irm -useb https://pixi.sh/install.ps1 | iex"`
- On Windows, run the app by entering `run.bat` in a terminal or powershell window within the app directory.
- On MacOS/Linux, navigate to the current directory within the terminal.\
  Grant permissions by running the following:
  `chmod +x run.sh`\
  Run the app using `./run.sh`



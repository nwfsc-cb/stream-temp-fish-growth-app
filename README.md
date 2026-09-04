# Stream Temp and Fish Growth Potential App

A **Posit Shiny for Python** web application designed for interactive stream temperature and fish growth potential data plotting. The application enables users to select Hydrologic Unit Codes (HUCs), fetch stream temperature model projections (Siegel et al. 2023, Fullerton et al. 2026), process decadal time series across seasons and view projections for fish growth potential based on stream temperature. It uses data from the riverscapes data exchange https://data.riverscapes.net/pt/streamtemp to download the data from the site or using this app. To download the data you need a free riverscapes account.


## Features

- **Interactive Web Interface**: Once the repo is dowloaded and the user follows the usage steps, no coding knowlege is required for app usage.
- **Interactive HUC6 Downloader**: Map-based spatial selection interface to dowload data by HUC6 region and manual download (by HUC) of smaller region areas.
- **Stream temperature plots**: Analyze stream temperature data plotted on interactive maps organzied by decadal seasonal analysis. 
- **Fish growth potential modeling**: Integrated polynomial growth model that translates water temperature into specific growth rate metrics for various fish species.
- **Flowline Overlays & Spatial Inspection**: Toggleable stream channel overlays 
- **CSV Data Export**: CSV generation by HUC12
- **Patch-Level Analysis**: See means and variances of fish growth potential for an upstream patch of any given COMID within a HUC12


## Repository Structure
```
- app.py                  # Main Shiny application 
- downloader.py           # Module handling HUC dataset acquisition using the riverscapes API
- sorter.py               # Reach Contributing Area (COMID) processing & visualization
- sorter12.py             # HUC12 boundary spatial processing module
- filterer.py             # Data extraction & aggregation engine for CSV exports
- temp_to_growth.py       # Polynomial thermal-to-fish-growth transformation model
- dictionaries.py         # Mappings for various dictionaries used by the app
- fish_type_growth.csv    # Empirical temperature vs. potential fish growth rate data
- single_huc_tab.py       # Patch-level analysis and statistics
- geopackages             # Folder containing the combined geopackages to map out HUC6 outlines
- pydex                   # riverscapes pydex file for acessing their API
- rsxml                   # Riverscapes xml (can also be installed via pip) to acess their API
```
## Usage
1. Clone the repo to your local machine and make sure all the files are in a folder together.
2. Install `pixi` to manage package installation.
    - Python Installation (pip):\
    `pip install pixi`
    - Source Installation (MacOS & Linux):\
    `curl -fsSL https://pixi.sh/install.sh | bash`
    - Source Installation (Windows):\
    `powershell -ExecutionPolicy ByPass -c "irm -useb https://pixi.sh/install.ps1 | iex"`
3. Run the app
    - On Windows, run the app by entering `run.bat` in a terminal or powershell window within the app directory.
    - On MacOS/Linux, navigate to the current directory within the terminal.\
    Grant permissions by running the following:
    `chmod +x run.sh`\
    Run the app using `./run.sh`
*Note: App may take a few minutes to launch in the browser*


## References 
#### Stream Temperature Predictions model
Past and future daily stream temperature predictions and covariates for each reach in the 1:100,000-scale National Hydrography Dataset, version 2, produced from a statistical model described in Siegel JE, Fullerton AH, FitzGerald AM, Holzer D, Jordan CE (2023) Daily stream temperature predictions for free-flowing streams in the Pacific Northwest, USA. PLOS Water 2(8): e0000119.
Siegel et al.: https://journals.plos.org/water/article?id=10.1371/journal.pwat.0000119
Fullerton et al.: https://onlinelibrary.wiley.com/doi/10.1111/1752-1688.70137
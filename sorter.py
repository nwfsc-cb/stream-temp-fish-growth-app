from datetime import datetime, timedelta
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import polars as pl

import temp_to_growth
import folium
import dictionaries

def sorter(parquet_file, start_year, fish_csv):
    '''Function to lazyload and sort the data'''

    # Lazy load dataframe
    lazy_df_temp = pl.scan_parquet(parquet_file)

    # Get decade based on Water Year
    begin_timeframe = datetime(start_year, 9, 21)
    end_timeframe = begin_timeframe + timedelta(weeks=520)

    # Filter dataframe
    huc_temps_df = (lazy_df_temp
    .filter(
        (pl.col("date") >= begin_timeframe) & # Filter by timeframe
        (pl.col("date") <= end_timeframe) & 
        (pl.col("stream_temp") != -999)) # Is not NULL value
    .with_columns( # Sort into seasons by Julian year
        pl.when((pl.col("date").dt.ordinal_day() >= 355) | (pl.col("date").dt.ordinal_day() <= 79)).then(pl.lit("winter"))
        .when((pl.col("date").dt.ordinal_day() >= 80) & (pl.col("date").dt.ordinal_day() <= 171)).then(pl.lit("spring"))
        .when((pl.col("date").dt.ordinal_day() >= 172) & (pl.col("date").dt.ordinal_day() <= 263)).then(pl.lit("summer"))
        .otherwise(pl.lit("autumn"))
        .alias("season"))
    .group_by("comid")
    .agg([ # Aggragate by season
        pl.col("stream_temp").filter(pl.col("season") == "winter").mean().alias("winter_avg"),
        pl.col("stream_temp").filter(pl.col("season") == "spring").mean().alias("spring_avg"),
        pl.col("stream_temp").filter(pl.col("season") == "summer").mean().alias("summer_avg"),
        pl.col("stream_temp").filter(pl.col("season") == "autumn").mean().alias("autumn_avg"),
    ])
    .with_columns( # Add fish growth cols
        pl.col("winter_avg").map_elements(lambda x: temp_to_growth.temp_transform(x, fish_csv), return_dtype=pl.Float64).alias("winter_fish_avg"),
        pl.col("spring_avg").map_elements(lambda x: temp_to_growth.temp_transform(x, fish_csv), return_dtype=pl.Float64).alias("spring_fish_avg"),
        pl.col("summer_avg").map_elements(lambda x: temp_to_growth.temp_transform(x, fish_csv), return_dtype=pl.Float64).alias("summer_fish_avg"),
        pl.col("autumn_avg").map_elements(lambda x: temp_to_growth.temp_transform(x, fish_csv), return_dtype=pl.Float64).alias("autumn_fish_avg")
    )
        .collect()
        .to_pandas()
    )

    return huc_temps_df

def merger(gpkg_file, huc_temps_df, target_crs=None):
    '''Function to merge gdf and huc_temp_df'''

    # Load geopackage with contributing area.
    gdf = gpd.read_file(gpkg_file, layer="contributing_area")
    gdf.rename(columns={"featureid": "comid"}, inplace=True)
    local_merged = gdf.merge(huc_temps_df, on="comid", how="left")

    return local_merged, target_crs

def process_huc_data(HUC_folder, start_year, fish_csv):
    '''Function to merge the dataframes and flowlines from all folders in the project'''

    # Establish path for all folders
    HUC_folder = Path(HUC_folder)
    HUC10_lst = [item.name for item in HUC_folder.iterdir() if item.is_dir()]
    all_merged_gdfs = []
    all_flowlines = []  # Collect flowline layers
    target_crs = None

    # Loop through all downloaded projects
    for project in HUC10_lst:
        folder_path = HUC_folder / project

        try:
            gpkg_file = next(folder_path.rglob("*.gpkg"))
            parquet_file = next(folder_path.rglob("*.gz"))
        except StopIteration:
            print(f"Skipping {project}: Missing .gpkg or .gz file in folder.")
            continue
            
        # Call sorter and merger functions to pull all the data needed
        huc_temps_df = sorter(parquet_file, start_year, fish_csv=fish_csv)
        local_merged, target_crs = merger(gpkg_file, huc_temps_df, target_crs)
        all_merged_gdfs.append(local_merged)

        # Read flowlines and standardize ID column for clean tooltips
        try:
            flow_gdf = gpd.read_file(gpkg_file, layer="flowlines")
            if "featureid" in flow_gdf.columns:
                flow_gdf.rename(columns={"featureid": "comid"}, inplace=True)
            all_flowlines.append(flow_gdf)
        except Exception as e:
            print(f"Could not read flowlines for {project}: {e}")

    # Concatenate the merged gdfs and flowlines into single GeoDataFrames
    final_gdf = pd.concat(all_merged_gdfs, ignore_index=True)
    final_flowlines = pd.concat(all_flowlines, ignore_index=True) if all_flowlines else None

    # Return both GeoDataFrames to match the Shiny app expectation
    return gpd.GeoDataFrame(final_gdf, crs=target_crs), gpd.GeoDataFrame(final_flowlines, crs=target_crs) if final_flowlines is not None else None


def visualizer(gdf, flowlines_gdf, fish, season):
    '''Make the interactive map with overlaid flowlines'''
    
    # Ensure standard coordinate reference system for interactive web mapping
    if gdf.crs is not None and gdf.crs.to_string():
        gdf = gdf.to_crs(epsg=4326)
    if flowlines_gdf is not None and flowlines_gdf.crs is not None:
        flowlines_gdf = flowlines_gdf.to_crs(epsg=4326)
    
    # Identify the feature ID column (comid vs HUC12)
    id_col = "comid" if "comid" in gdf.columns else "HUC12"
    name_col = "name" if "name" in gdf.columns else "HUC12"

    # Inject custom popup HTML directly into the GeoDataFrame as a column
    gdf["csv_popup"] = gdf.apply(
        lambda row: f"""
            <div style='text-align: center; padding: 5px;'>
                <b style='font-size: 1.1em;'>{id_col.upper()}: {row[name_col]}</b><br>
                <button class='btn btn-success btn-lg mt-3' style='width: 100%;'
                        onclick='window.parent.postMessage({{"type": "map_feature_click", "id": "{row[id_col]}"}}, "*")'>
                    Select {id_col.upper()}
                </button>
            </div>
        """,
        axis=1
    )

    season_map = dictionaries.FISH_SEASON if fish else dictionaries.SEASONS
    column_to_plot = season_map[season]
    metric_label = "Fish Growth" if fish else "Temperature"
    caption = f"{season} {metric_label}"

    tooltip_cols = [id_col, column_to_plot]
    if fish:
        cmap="plasma"
        vmin=-10
        vmax=10
    else:
        cmap="cool"
        vmin=0
        vmax=30

    # Base map: Reach Contributing Areas
    m = gdf.explore(
        column=column_to_plot,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        legend=True,
        legend_kwds={"caption": caption},
        popup=["csv_popup"],
        popup_kwds={"labels": False},  # <--- This removes the "csv_popup" column header
        tooltip=tooltip_cols,
        highlight_kwds={
            "weight": 3.5,          # Thicken border significantly on hover
            "color": "#00ffff",     # Bright blue outline when mouse passes over
            "fillOpacity": 0.85     # Brighten fill color on hover
        },
        style_kwds={"weight": 1.5, "fillOpacity": 0.7},
        tiles="https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}",  # Google Terrain URL template
        attr="Google",
        name="Reach Contributing Area"
    )

    # Overlay Stream Flowlines
    if flowlines_gdf is not None and not flowlines_gdf.empty:
        flowlines_gdf.explore(
            m=m,                         # Render onto the existing map
            color="#000000",             
            style_kwds={"weight": 1, "opacity": 0.8},
            tooltip=["comid"] if "comid" in flowlines_gdf.columns else False,
            name="Stream Flowlines"
        )

    return m
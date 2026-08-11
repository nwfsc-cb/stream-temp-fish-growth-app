from datetime import datetime, timedelta
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import polars as pl

import temp_to_growth
import dictionaries
import folium

def sorter(parquet_file, gpkg_file, start_year, fish_csv):
    '''Function to lazyload and sort the data'''

    # Lazy load dataframe
    lazy_df_temp = pl.scan_parquet(parquet_file)
    gdf = gpd.read_file(gpkg_file, layer="contributing_area")
    comid_huc_map = pl.from_pandas(gdf[["featureid", "HUC12"]].rename(columns={"featureid": "comid"})
                                   ).with_columns(pl.col("comid").cast(pl.Int64), pl.col("HUC12").cast(pl.Utf8)
    )

    # Get decade based on Water Year
    begin_timeframe = datetime(start_year, 9, 21)
    end_timeframe = begin_timeframe + timedelta(weeks=520)

    #Filter dataframe
    huc_temps_df = (lazy_df_temp
    .filter(
        (pl.col("date") >= begin_timeframe) & # Filter by timeframe
        (pl.col("date") <= end_timeframe) & 
        (pl.col("stream_temp") != -999))  # Is not NULL value
    .with_columns( # Sort into seasons by Julian year
        pl.when((pl.col("date").dt.ordinal_day() >= 355) | (pl.col("date").dt.ordinal_day() <= 79)).then(pl.lit("winter"))
        .when((pl.col("date").dt.ordinal_day() >= 80) & (pl.col("date").dt.ordinal_day() <= 171)).then(pl.lit("spring"))
        .when((pl.col("date").dt.ordinal_day() >= 172) & (pl.col("date").dt.ordinal_day() <= 263)).then(pl.lit("summer"))
        .otherwise(pl.lit("autumn"))
        .alias("season"))
    .join(comid_huc_map.lazy(), on="comid", how="left") # Add cols
    .group_by("HUC12")
    .agg([ # Aggragate by season
        pl.col("stream_temp").filter(pl.col("season") == "winter").mean().alias("winter_avg"),
        pl.col("stream_temp").filter(pl.col("season") == "spring").mean().alias("spring_avg"),
        pl.col("stream_temp").filter(pl.col("season") == "summer").mean().alias("summer_avg"),
        pl.col("stream_temp").filter(pl.col("season") == "autumn").mean().alias("autumn_avg"),
    ])
    .with_columns( # Add fish growth col
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
    gdf = gpd.read_file(gpkg_file, layer="HUC12_boundaries")
    gdf.rename(columns={"featureid": "comid"}, inplace=True)
    local_merged = gdf.merge(huc_temps_df, on="HUC12", how="left")

    return local_merged, target_crs

def process_huc_data(HUC_folder, start_year, fish_csv):
    '''Function to merge the dataframes and flowlines from all folders in the project'''

    HUC_folder = Path(HUC_folder)
    HUC10_lst = [item.name for item in HUC_folder.iterdir() if item.is_dir()]
    all_merged_gdfs = []
    all_flowlines = []  # New list to collect flowlines
    target_crs = None

    for project in HUC10_lst:
        folder_path = HUC_folder / project

        try:
            gpkg_file = next(folder_path.rglob("*.gpkg"))
            parquet_file = next(folder_path.rglob("*.gz"))
        except StopIteration:
            print(f"Skipping {project}: Missing .gpkg or .gz file in folder.")
            continue
            
        # Call sorter and merger functions
        huc_temps_df = sorter(parquet_file, gpkg_file, start_year, fish_csv=fish_csv)
        local_merged, target_crs = merger(gpkg_file, huc_temps_df, target_crs)
        all_merged_gdfs.append(local_merged)

        # Read flowlines layer (Note: adjust "flowlines" to match your exact layer name in the gpkg)
        try:
            flow_gdf = gpd.read_file(gpkg_file, layer="flowlines")
            all_flowlines.append(flow_gdf)
        except Exception as e:
            print(f"Could not read flowlines for {project}: {e}")

    # Concatenate both datasets
    final_gdf = pd.concat(all_merged_gdfs, ignore_index=True)
    final_flowlines = pd.concat(all_flowlines, ignore_index=True) if all_flowlines else None

    # Return both as GeoDataFrames
    return gpd.GeoDataFrame(final_gdf, crs=target_crs), gpd.GeoDataFrame(final_flowlines, crs=target_crs)

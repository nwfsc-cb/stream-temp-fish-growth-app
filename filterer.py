from datetime import datetime, timedelta
from pathlib import Path
import polars as pl
import geopandas as gpd
import pandas as pd
import temp_to_growth

# Filtering single huc12 data for csv generation 

def filterer(selected_id, project_dir, start_year, fish_csv):
    project_dir = Path(project_dir)
    selected_id_str = str(selected_id).strip()

    # Timeframe calculation
    begin_timeframe = datetime(int(start_year), 9, 21)
    end_timeframe = begin_timeframe + timedelta(weeks=520)

    # Inspect sub-folders inside project directory (e.g. HUC10 sub-directories)
    sub_folders = [d for d in project_dir.iterdir() if d.is_dir()]
    if not sub_folders:
        sub_folders = [project_dir]

    collected_dfs = []

    for folder in sub_folders:
        try:
            gpkg_file = next(folder.rglob("*.gpkg"))
            parquet_file = next(folder.rglob("*.gz"))
        except StopIteration:
            continue

        # Load GeoPackage layer
        gdf = gpd.read_file(gpkg_file, layer="contributing_area")
        
        gdf["HUC12_str"] = gdf["HUC12"].astype(str).str.strip() if "HUC12" in gdf.columns else ""
        gdf["comid_str"] = gdf["featureid"].astype(str).str.strip()

        # Check if selected_id matches HUC12 or COMID in this subfolder
        is_huc12_match = selected_id_str in gdf["HUC12_str"].values
        is_comid_match = selected_id_str in gdf["comid_str"].values

        if not (is_huc12_match or is_comid_match):
            continue

        # Map COMIDs to HUC12
        comid_huc_map = pl.from_pandas(
            gdf[["featureid", "HUC12"]].rename(columns={"featureid": "comid"})
        ).with_columns(
            pl.col("comid").cast(pl.Int64),
            pl.col("HUC12").cast(pl.Utf8).str.strip_chars()
        )

        lazy_df = pl.scan_parquet(parquet_file)

        filtered = (
            lazy_df
            .filter(
                (pl.col("date") >= begin_timeframe) &
                (pl.col("date") <= end_timeframe) &
                (pl.col("stream_temp") != -999)
            )
            .with_columns(
                pl.when((pl.col("date").dt.ordinal_day() >= 355) | (pl.col("date").dt.ordinal_day() <= 79)).then(pl.lit("winter"))
                .when((pl.col("date").dt.ordinal_day() >= 80) & (pl.col("date").dt.ordinal_day() <= 171)).then(pl.lit("spring"))
                .when((pl.col("date").dt.ordinal_day() >= 172) & (pl.col("date").dt.ordinal_day() <= 263)).then(pl.lit("summer"))
                .otherwise(pl.lit("autumn"))
                .alias("season")
            )
            .join(comid_huc_map.lazy(), on="comid", how="left")
        )

        # Apply filter based on match type
        if is_huc12_match:
            # Filter to all rows matching the clicked HUC12
            filtered = filtered.filter(pl.col("HUC12") == selected_id_str)
        else:
            # Direct match for single COMID
            filtered = filtered.filter(pl.col("comid").cast(pl.Utf8) == selected_id_str)

        # group by comid so every individual reach/stream segment is returned!
        sub_result = (
            filtered
            .group_by("comid")
            .agg([
                pl.col("stream_temp").filter(pl.col("season") == "winter").mean().alias("winter_avg"),
                pl.col("stream_temp").filter(pl.col("season") == "spring").mean().alias("spring_avg"),
                pl.col("stream_temp").filter(pl.col("season") == "summer").mean().alias("summer_avg"),
                pl.col("stream_temp").filter(pl.col("season") == "autumn").mean().alias("autumn_avg"),
            ])
            .with_columns(
                pl.col("winter_avg").map_elements(lambda x: temp_to_growth.temp_transform(x, fish_csv), return_dtype=pl.Float64).alias("winter_fish_avg"),
                pl.col("spring_avg").map_elements(lambda x: temp_to_growth.temp_transform(x, fish_csv), return_dtype=pl.Float64).alias("spring_fish_avg"),
                pl.col("summer_avg").map_elements(lambda x: temp_to_growth.temp_transform(x, fish_csv), return_dtype=pl.Float64).alias("summer_fish_avg"),
                pl.col("autumn_avg").map_elements(lambda x: temp_to_growth.temp_transform(x, fish_csv), return_dtype=pl.Float64).alias("autumn_fish_avg")
            )
            .collect()
            .to_pandas()
        )

        if not sub_result.empty:
            collected_dfs.append(sub_result)

    final_df = pd.concat(collected_dfs, ignore_index=True) if collected_dfs else pd.DataFrame()

    return final_df
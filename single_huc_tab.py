import sys
import asyncio

# Force Windows to use the SelectorEventLoop, which aiodns requires
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


from pathlib import Path
from datetime import datetime, timedelta
import geopandas as gpd
import polars as pl
import folium
from shiny import reactive, render, ui
import dictionaries

import temp_to_growth


try:
    import pynhd
except ImportError:
    pynhd = None


def single_huc_ui():
    """Returns the UI layout for the Single HUC12 tab."""
    return ui.nav_panel(
        "HUC12 Catchment Statistics",
        ui.card(
            ui.card_header(
                ui.p(
                    "Note: This tab extracts COMID catchments and flowlines from the active project configured on the 'All Seasons' tab.",
                    class_="text-muted",
                    style="font-size: 0.9em; margin-bottom: 15px;",
                ),
                ui.layout_column_wrap(
                    ui.input_text(
                        id="single_huc12_val",
                        label="Enter HUC12 ID:",
                        placeholder="e.g. 170900010101",
                    ),
                    ui.input_text(
                        id="single_yearval",
                        label="Water Year Start:",
                        placeholder="e.g. 1980",
                    ),
                    ui.input_select(
                        id="stats_type",
                        label="Statistics Mode:",
                        choices={
                            "temporal": "Temporal Statistics", 
                            "spatial": "Spatial Statistics"
                        }
                    ),
                    ui.input_select(
                        id="selected_fish_2",
                        label="Select Fish Species:",
                        choices=dictionaries.FISHTABLE,  
                        selected="Red_Band_Trout_Growth.csv"
                    ),
                    width=1/4
                ),
                
                ui.input_action_button(
                    "render_single_huc12", "Render Map", class_="btn-success"
                ),
                ui.hr(),
                ui.output_ui("upstream_stats")
            ),
            ui.output_ui("map_single_huc12"),
            height="900px",
        ),
    )


def single_huc_server(input, output, session, base_dir, modules):
    """Contains the reactive server logic for the Single HUC12 tab."""
    
    active_comid = reactive.Value(None)

    @reactive.Effect
    @reactive.event(input.render_single_huc12)
    def reset_comid_on_new_render():
        # Clear selected COMID when rendering a new HUC12
        active_comid.set(None)

    @reactive.Effect
    @reactive.event(input.clicked_comid)
    def update_active_comid():
        # Update state when a user clicks the popup button
        active_comid.set(input.clicked_comid())

    @reactive.Calc
    @reactive.event(input.render_single_huc12)
    def single_huc_data():
        """Fetches and caches the geodataframes for the requested HUC12."""
        huc12_id = input.single_huc12_val().strip()
        year = input.single_yearval().strip()
        
        if not huc12_id:
            return "Please enter a valid HUC12 ID."
        if not year or not year.isdigit():
            return "Please enter a valid start year."

        project = input.selected_project()
        if not project:
            return "No project selected. Please select one on the 'All Seasons' tab."

        target_dir = base_dir / project

        fish_csv = input.selected_fish_2()

        try:
            catchments_gdf, flowlines_gdf = modules["ca"].process_huc_data(target_dir, int(year), fish_csv)
        except Exception as e:
            return f"Error loading project data: {e}"

        huc_col = next((col for col in catchments_gdf.columns if "huc12" in col.lower()), None)
        if not huc_col:
            huc_col = next((col for col in catchments_gdf.columns if "huc" in col.lower()), catchments_gdf.columns[0])

        filtered_catchments = catchments_gdf[catchments_gdf[huc_col].astype(str) == huc12_id].copy()

        if filtered_catchments.empty:
            return f"HUC12 '{huc12_id}' was not found in the currently active project."

        try:
            boundary_poly = filtered_catchments.geometry.unary_union
            filtered_flowlines = gpd.clip(flowlines_gdf, boundary_poly).copy()
        except Exception:
            filtered_flowlines = gpd.GeoDataFrame()

        comid_col = next((col for col in filtered_catchments.columns if "comid" in col.lower()), huc_col)
        
        # Add the HTML button for Folium popups
        filtered_catchments['Popup'] = filtered_catchments.apply(
            lambda row: f"<button class='btn btn-info btn-sm' onclick='window.parent.postMessage({{\"type\": \"comid_click\", \"comid\": \"{row[comid_col]}\"}}, \"*\")'>Highlight Upstream of {row[comid_col]}</button>",
            axis=1
        )
        
        # Ensure COMID is a string for easy merging later
        filtered_catchments[comid_col] = filtered_catchments[comid_col].astype(str)
        bounds = filtered_catchments.total_bounds
        
        return catchments_gdf, filtered_catchments, filtered_flowlines, bounds, comid_col, huc12_id


    @reactive.Calc
    def get_upstream_comids():
        """Queries NHDPlus for upstream COMIDs when a reach is clicked."""
        current_comid = active_comid()
        if not current_comid or pynhd is None:
            return []
            
        try:
            nldi = pynhd.NLDI()
            nav = nldi.navigate_byid(
                fsource="comid",
                fid=str(current_comid),
                navigation="upstreamTributaries",
                source="flowlines",
                distance=999
            )
            if not nav.empty:
                return nav["nhdplus_comid"].astype(str).tolist()
        except Exception as e:
            print(f"Failed to fetch upstream NHD data: {e}")
            
        return []

    @reactive.Calc
    def spatial_stats_data():
        """Calculates per-reach mean and variance for the spatial statistics mode."""
        if input.stats_type() != "spatial":
            return None
            
        data = single_huc_data()
        if isinstance(data, str):
            return None
            
        _, filtered_catchments, _, _, comid_col, _ = data
        
        # Identify all COMIDs in this HUC
        all_huc_comids = filtered_catchments[comid_col].dropna().astype(str).tolist()
        query_comids_int = []
        for c in all_huc_comids:
            try:
                query_comids_int.append(int(float(c)))
            except ValueError:
                pass
                
        project = input.selected_project()
        year = input.single_yearval().strip()
        target_dir = base_dir / project
        fish_csv = input.selected_fish_2()
        try:
            begin_timeframe = datetime(int(year), 9, 21)
            end_timeframe = begin_timeframe + timedelta(days=365)
            
            all_dfs = []
            
            # Extract temperatures for all relevant COMIDs
            for p_file in target_dir.rglob("*.gz"):
                df = (pl.scan_parquet(p_file)
                      .filter(
                          (pl.col("date") >= begin_timeframe) &
                          (pl.col("date") <= end_timeframe) &
                          (pl.col("stream_temp") != -999) &
                          (pl.col("comid").is_in(query_comids_int))
                      )
                      .select(["comid", "stream_temp"])
                      .collect()
                )
                if df.height > 0:
                    all_dfs.append(df)
                    
            if not all_dfs:
                return None
                
            combined = pl.concat(all_dfs)
            
            # Calculate growth row-by-row
            combined = combined.with_columns(
                pl.col("stream_temp")
                .map_elements(lambda x: temp_to_growth.temp_transform(x, fish_csv), return_dtype=pl.Float64)
                .alias("fish_growth")
            )
            
            # Group by COMID to get mean and variance per reach
            stats = combined.group_by("comid").agg(
                pl.col("fish_growth").mean().alias("Growth_Mean"),
                pl.col("fish_growth").var().alias("Growth_Var")
            )
            
            # Convert to Pandas dataframe and prepare the COMID as string for merging
            sp_df = stats.to_pandas()
            sp_df['comid_str'] = sp_df['comid'].astype(str)
            
            sp_df = sp_df.drop(columns=['comid'])
            
            return sp_df
            
        except Exception as e:
            print(f"Error calculating spatial stats: {e}")
            return None


    @render.ui
    def upstream_stats():
        """Calculates daily fish growth statistics for upstream and non-upstream reaches (Temporal mode)."""
        if input.render_single_huc12() == 0:
            return ui.p()
            
        data = single_huc_data()
        if isinstance(data, str):
            return ui.p()
            
        year = input.single_yearval().strip()
            
        # Display instructional text for spatial mode
        if input.stats_type() == "spatial":
            return ui.div(
                ui.h5(f"Spatial Statistics ({year} Water Year)", style="margin-top: 10px;"),
                ui.p("Hover over individual reaches on the map below to view their annual mean and variance of fish growth.", class_="text-muted", style="font-size: 1.1em;")
            )
            
        # If temporal, proceed with the daily network average calculations
        fish_csv = input.selected_fish_2()
        _, filtered_catchments, _, _, comid_col, huc12_id = data
            
        current_comid = active_comid()
        upstream_comids = get_upstream_comids()
        
        if not current_comid:
            return ui.p("Click a COMID on the map to calculate network fish growth.", class_="text-muted")
            
        # Identify Upstream COMIDs
        target_comids_str = set([str(current_comid)] + upstream_comids)
        upstream_comids_int = []
        for c in target_comids_str:
            try:
                upstream_comids_int.append(int(float(c)))
            except ValueError:
                pass
                
        # Identify all COMIDs in this HUC so we can single out the non-upstream ones
        all_huc_comids = filtered_catchments[comid_col].dropna().astype(str).tolist()
        query_comids_int = set(upstream_comids_int)
        for c in all_huc_comids:
            try:
                query_comids_int.add(int(float(c)))
            except ValueError:
                pass
        
        query_comids_list = list(query_comids_int)
        
        project = input.selected_project()
        target_dir = base_dir / project
        
        try:
            # Get 1-year timeframe (365 days)
            begin_timeframe = datetime(int(year), 9, 21)
            end_timeframe = begin_timeframe + timedelta(days=365)
            
            all_dfs = []
            
            # Extract daily temperatures for all relevant COMIDs Inside upstream_stats()
            for p_file in target_dir.rglob("*.gz"):
                df = (pl.scan_parquet(p_file)
                      .filter(
                          (pl.col("date") >= begin_timeframe) &
                          (pl.col("date") <= end_timeframe) &
                          (pl.col("stream_temp") > -50) &  # FIX: Catch all NoData flags
                          (pl.col("comid").is_in(query_comids_list))
                      )
                      .select(["comid", "date", "stream_temp"])
                      .collect()
                )
                if df.height > 0:
                    all_dfs.append(df)
                    
            if not all_dfs:
                return ui.p("No data found in the parquet files for the selected network in this year.", style="color: red;")
                
            combined = pl.concat(all_dfs)
            
            # Calculate growth BEFORE taking the network average
            combined = combined.with_columns(
                pl.col("comid").is_in(upstream_comids_int).alias("is_upstream"),
                pl.col("stream_temp")
                .map_elements(lambda x: temp_to_growth.temp_transform(x, fish_csv), return_dtype=pl.Float64)
                .alias("fish_growth")
            )
            
            # Calculate the daily average fish growth for the upstream vs non-upstream groups
            daily_growth = (
                combined.group_by(["is_upstream", "date"])
                .agg(pl.col("fish_growth").mean().alias("daily_fish_growth"))
            )
            
            # Separate into the two distinct groups for stats calculations
            up_df = daily_growth.filter(pl.col("is_upstream") == True)
            non_up_df = daily_growth.filter(pl.col("is_upstream") == False)
            
            # Handle empty slices gracefully
            up_avg = up_df["daily_fish_growth"].mean() if not up_df.is_empty() else 0.0
            up_var = up_df["daily_fish_growth"].var() if not up_df.is_empty() and up_df.height > 1 else 0.0
            
            non_up_avg = non_up_df["daily_fish_growth"].mean() if not non_up_df.is_empty() else 0.0
            non_up_var = non_up_df["daily_fish_growth"].var() if not non_up_df.is_empty() and non_up_df.height > 1 else 0.0
            
            # Deal with nulls if variables somehow escaped checks
            up_avg, up_var = up_avg or 0.0, up_var or 0.0
            non_up_avg, non_up_var = non_up_avg or 0.0, non_up_var or 0.0
            
            return ui.div(
                ui.h5(f"Temporal Fish Growth Statistics ({year} Water Year)", style="margin-top: 10px;"),
                ui.div(
                    ui.p(ui.HTML(f"<b>Upstream Network Mean:</b> {up_avg:.5f} g/g/w &nbsp;|&nbsp; <b>Variance:</b> {up_var:.5f}"), style="font-size: 1.1em; color: #0056b3; margin-bottom: 5px;"),
                    ui.p(ui.HTML(f"<b>Other HUC Reaches Mean:</b> {non_up_avg:.5f} g/g/w &nbsp;|&nbsp; <b>Variance:</b> {non_up_var:.5f}"), style="font-size: 1.1em; color: #6c757d; margin-bottom: 0px;")
                )
            )
            
        except Exception as e:
            return ui.p(f"Error calculating temporal fish growth: {e}", style="color: red;")


    @render.ui
    def map_single_huc12():
        """Renders the map, querying NHDPlus for upstream networks if a COMID is clicked."""
        if input.render_single_huc12() == 0:
            return ui.p("Enter a HUC12 and Start Year, then click Render Map to begin.")
            
        data = single_huc_data()
        if isinstance(data, str):
            return ui.p(data, style="color: red;")
            
        if pynhd is None:
            return ui.p("Please install 'pynhd' (pip install pynhd) to use this interactive tab.", style="color: red;")

        _, filtered_catchments, filtered_flowlines, bounds, comid_col, huc12_id = data
        
        # Inject spatial stats if the mode is selected
        tooltip_fields = [comid_col]
        tooltip_aliases = ["COMID:"]
        
        if input.stats_type() == "spatial":
            sp_stats = spatial_stats_data()
            if sp_stats is not None and not sp_stats.empty:
                # Merge stats into filtered catchments GeoDataFrame
                filtered_catchments = filtered_catchments.merge(
                    sp_stats, left_on=comid_col, right_on='comid_str', how='left'
                )
                
                # Format the numbers for the tooltip display
                filtered_catchments['Growth_Mean'] = filtered_catchments['Growth_Mean'].round(5).astype(str).replace("nan", "N/A")
                filtered_catchments['Growth_Var'] = filtered_catchments['Growth_Var'].round(5).astype(str).replace("nan", "N/A")
                
                tooltip_fields.extend(["Growth_Mean", "Growth_Var"])
                tooltip_aliases.extend(["Mean Growth:", "Growth Variance:"])
        
        current_comid = active_comid()
        upstream_comids = get_upstream_comids()

        center_lat = (bounds[1] + bounds[3]) / 2
        center_lon = (bounds[0] + bounds[2]) / 2

        m = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles="OpenStreetMap")

        def catchment_style(feature):
            f_comid = str(feature['properties'].get(comid_col, ''))
            if f_comid == current_comid:
                return {"fillColor": "#ff0000", "color": "#000000", "weight": 2, "fillOpacity": 0.7} 
            elif f_comid in upstream_comids:
                return {"fillColor": "#ff8c00", "color": "#000000", "weight": 1, "fillOpacity": 0.6} 
            else:
                return {"fillColor": "#3186cc", "color": "#000000", "weight": 1, "fillOpacity": 0.2} 

        def flowline_style(feature):
            f_comid = str(feature['properties'].get('COMID', feature['properties'].get('comid', '')))
            if f_comid == current_comid:
                return {"color": "#ff0000", "weight": 4, "opacity": 1.0}
            elif f_comid in upstream_comids:
                return {"color": "#ff8c00", "weight": 3.5, "opacity": 0.9}
            else:
                return {"color": "#0000FF", "weight": 2, "opacity": 0.5}

        folium.GeoJson(
            filtered_catchments,
            name=f"COMIDs in {huc12_id}",
            style_function=catchment_style,
            tooltip=folium.GeoJsonTooltip(fields=tooltip_fields, aliases=tooltip_aliases),
            popup=folium.GeoJsonPopup(fields=['Popup'], labels=False)
        ).add_to(m)

        if not filtered_flowlines.empty:
            folium.GeoJson(
                filtered_flowlines,
                name="Flowlines",
                style_function=flowline_style
            ).add_to(m)

        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])

        return ui.HTML(m._repr_html_())
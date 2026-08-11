import sys
import asyncio

# Force Windows to use the SelectorEventLoop, which aiodns requires
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


from pathlib import Path
import geopandas as gpd
import folium
import pandas as pd
from shiny import App, reactive, render, ui

import downloader
import dictionaries
import sorter
import sorter12 
import filterer
from single_huc_tab import single_huc_ui, single_huc_server

MODULES = {
    "ca": sorter,
    "huc12": sorter12
}

BASE_DIR = Path("Region_Projects")

class MissingYearException(Exception):
    """Raised when the input value is too low."""
    pass

# Load and prepare the HUC6 GeoPackage globally
GPKG_DIR = Path("geopackages")
huc6_gdf = None

if GPKG_DIR.exists():
    gpkg_files = list(GPKG_DIR.glob("*.gpkg"))
    if gpkg_files:
        huc6_gdf = gpd.read_file(gpkg_files[0])
        huc6_gdf['geometry'] = huc6_gdf['geometry'].simplify(tolerance=0.01)
        
        huc_col = next((col for col in huc6_gdf.columns if 'huc' in col.lower()), huc6_gdf.columns[0])
        name_col = next((col for col in huc6_gdf.columns if col.lower() == 'name'), 'name')
        
        huc6_gdf['Popup'] = huc6_gdf.apply(
            lambda row: f"<button class='btn btn-primary btn-sm' onclick='window.parent.postMessage({{\"type\": \"huc_click\", \"huc\": \"{row[huc_col]}\"}}, \"*\")'>Select {row[name_col]}</button>",
            axis=1
        )

def get_existing_projects():
    if not BASE_DIR.exists():
        return {"": "-- No projects found --"}
    folders = [d.name for d in BASE_DIR.iterdir() if d.is_dir()]
    if not folders:
        return {"": "-- No projects found --"}
    return {f: f for f in sorted(folders)}


app_ui = ui.page_fluid(
    ui.tags.script("""
    window.addEventListener("message", (event) => {
        if (event.data && event.data.type) {
            
            // Helpful for debugging: prints the exact message to your browser's Developer Console (F12)
            console.log("Map feature clicked! Received data:", event.data); 
            
            if (event.data.type === "huc_click") {
                Shiny.setInputValue("clicked_huc", event.data.huc, {priority: "event"});
                
            } else if (event.data.type.includes("click") && event.data.type !== "huc_click") {
                // Catch-all: Grab the ID whether sorter.py calls it 'comid', 'id', or 'feature_id'
                let featureId = event.data.comid || event.data.id || event.data.feature_id;
                
                if (featureId) {
                    Shiny.setInputValue("clicked_comid", featureId, {priority: "event"});
                }
            }
        }
    });
    """),
    
    ui.panel_title("Temperature and Fish Growth Plotter"),
    
    ui.navset_card_tab(
        # Tab 1: Contains the Sidebar and the Grid
        ui.nav_panel(
            "All Seasons (Grid)",
            ui.layout_sidebar(
                ui.sidebar(
                    ui.accordion(
                        ui.accordion_panel("Downloader",
                            ui.p("Click a region on the map to select its HUC6, or enter it manually."),
                            ui.output_ui("huc_selector_map"), 
                            ui.br(),
                            ui.input_text_area( 
                                id="hucval",
                                label="HUC Value:",
                                value="",
                                placeholder="Type here or select on map..."
                            ),
                            ui.input_action_button("submit_btn", "Download Data", class_="btn-success"),
                            ui.output_text_verbatim("runlogic"),
                        ),
                        ui.accordion_panel("Plotter",
                            ui.input_select(
                                id="selected_project",
                                label="Select Existing Project:",
                                choices=get_existing_projects()
                            ),
                            ui.input_select( 
                                id="boundary_type",
                                label="Boundary Type:",
                                choices={
                                    "ca": "Reach Contributing Area",
                                    "huc12": "HUC12 Boundary"
                                },
                                selected="ca"
                            ),
                            ui.input_text_area(
                                id="yearval",
                                label="Decade Start Year:",
                                value="",
                                placeholder="Type here..."
                            ),
                            ui.input_select(
                                id="selected_fish",
                                label="Select Fish Species:",
                                choices=dictionaries.FISHTABLE,  
                                selected="Red_Band_Trout_Growth.csv"
                            ),
                            ui.input_checkbox(
                                id="toggle", 
                                label="Show Fish Growth", 
                                value=True
                            ),
                            ui.input_checkbox(
                                id="show_flowlines", 
                                label="Overlay Stream Flowlines", 
                                value=False
                            ),
                            ui.input_action_button("readydata", "Plot Data", class_="btn-primary"),
                            ui.hr(),
                            # Dynamic CSV Export Action UI
                            ui.output_ui("csv_export_ui")
                        ),
                        id="sidebar_accordion", multiple=True, open=["Plotter"]
                    ),
                    width="25%"
                ),
                
                # Grid container for seasonal outputs 
                ui.layout_column_wrap(
                    ui.card(ui.card_header("Winter"), ui.output_ui("map_winter"), height="450px"),
                    ui.card(ui.card_header("Spring"), ui.output_ui("map_spring"), height="450px"),
                    ui.card(ui.card_header("Summer"), ui.output_ui("map_summer"), height="450px"),
                    ui.card(ui.card_header("Autumn"), ui.output_ui("map_autumn"), height="450px"),
                    width=1/2,
                    fill=False
                )
            )
        ),
        single_huc_ui()
    )
)

def server(input, output, session):

    # Reactive Val to hold chosen ID from the map click
    active_feature_id = reactive.Value(None)

    @reactive.Effect
    @reactive.event(input.clicked_comid)
    def _store_selected_feature():
        active_feature_id.set(input.clicked_comid())
            
    # Register the single HUC module server logic
    single_huc_server(input, output, session, BASE_DIR, MODULES)
    
    @render.ui
    def huc_selector_map():
        if huc6_gdf is None:
            return ui.p("HUC6 Geopackage not found.", style="color: red;")
            
        bounds = huc6_gdf.total_bounds
        center_lat = (bounds[1] + bounds[3]) / 2
        center_lon = (bounds[0] + bounds[2]) / 2
        
        m = folium.Map(location=[center_lat, center_lon], zoom_start=4)
        folium.GeoJson(
            huc6_gdf,
            name="HUC6 Boundaries",
            style_function=lambda x: {'fillColor': '#3186cc', 'color': '#000000', 'weight': 1, 'fillOpacity': 0.2},
            highlight_function=lambda x: {'weight': 3, 'fillOpacity': 0.5},
            popup=folium.GeoJsonPopup(fields=['Popup'], labels=False)
        ).add_to(m)
        
        return ui.HTML(m._repr_html_())

    @reactive.Effect
    @reactive.event(input.clicked_huc)
    def _update_huc_input():
        ui.update_text_area("hucval", value=input.clicked_huc())

    @render.text
    @reactive.event(input.submit_btn)
    def runlogic():
        folder_name = f"HUC_{input.hucval()}"
        target_dir = BASE_DIR / folder_name
        downloader.download_huc_data(int(input.hucval()), str(target_dir))
        ui.update_select(
            "selected_project",
            choices=get_existing_projects(),
            selected=folder_name
        )
        return "ready!"

    @reactive.calc
    @reactive.event(input.readydata)
    def processed_data():
        if not int(input.yearval()) in range(1979, 2022):
            raise MissingYearException("Invalid year value!")
            
        if not input.selected_project():
            return None, None, None
            
        active_sorter = MODULES[input.boundary_type()]
        target_dir = BASE_DIR / input.selected_project()

        fish_csv = input.selected_fish()
        final_gdf, flowlines_gdf = active_sorter.process_huc_data(target_dir, int(input.yearval()), fish_csv)
        return final_gdf, flowlines_gdf, active_sorter

    # Conditional Render: Display the CSV button when an ID is selected
    @render.ui
    def csv_export_ui():
        feat_id = active_feature_id()
        if not feat_id:
            return ui.p("Click a feature on any seasonal map to expose export button.", style="font-style: italic; color: gray;")
        
        return ui.div(
            ui.p(f"Selected ID: ", ui.tags.b(feat_id)),
            ui.download_button("download_csv", f"Generate CSV for {feat_id}", class_="btn-info w-100")
        )

    # Download handler to compile and export CSV
    @render.download(filename=lambda: f"data_export_{active_feature_id()}.csv")
    def download_csv():
        feat_id = active_feature_id()
        if not feat_id or not input.selected_project():
            return None

        target_dir = BASE_DIR / input.selected_project()
        
        # Parse start year safely
        year_val = input.yearval()
        if not year_val or not year_val.isdigit():
            print("[DEBUG] No valid start year provided.")
            return None

        # Execute updated filterer across the project directory
        csv_df = filterer.filterer(
            selected_id=str(feat_id), 
            project_dir=target_dir,
            start_year=int(year_val),
            fish_csv=input.selected_fish()
        )
        
        yield csv_df.to_csv(index=False).encode("utf-8")

    def build_season_map(season_name):
        final_gdf, flowlines_gdf, active_sorter = processed_data()
        if final_gdf is None:
            return ui.p("Click 'Plot Data' to render maps.")
            
        folium_map = sorter.visualizer(
            gdf=final_gdf, 
            flowlines_gdf=flowlines_gdf if input.show_flowlines() else None,
            fish=input.toggle(), 
            season=season_name
        )
        return ui.HTML(folium_map._repr_html_())

    # Render maps 
    @render.ui
    def map_winter():
        return build_season_map("Winter")

    @render.ui
    def map_spring():
        return build_season_map("Spring")

    @render.ui
    def map_summer():
        return build_season_map("Summer")

    @render.ui
    def map_autumn():
        return build_season_map("Autumn")

# Run the app 
app = App(app_ui, server)
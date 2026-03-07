"""_summary_

    Returns:
        _type_: _description_
"""
from datetime import date, timedelta
import seaborn as sns
from shared import df, images, CLM5_smi_full, lon, lat, decade_to_index
from shiny import App, render, ui
from shiny.types import ImgData
from shinyswatch import theme
from theme_config import get_theme_config, GOOGLE_FONTS_URL

dark_theme = theme.darkly

# The contents of the first 'page' is a navset with two 'panels'.
page_droughts = ui.page_fluid(
    ui.card("Space for introductory text about droughts and their impacts.",
            height="250px",
            style="text-align: left;"),

    ui.page_sidebar(ui.sidebar("View settings",
                        ui.input_slider("dec", "Decade",
                                        min=date(1960, 1, 2),
                                        max=date(2020, 1, 10),
                                        value=date(1960, 1, 2),
                                        step=timedelta(days = 366*10),
                                        time_format="%Y",
                                        ticks=True),
                        ui.input_select("model", "Atmospheric forcing",
                                        choices={"Ensemble mean": "ensemble_mean",
                                                 "CESM2": "CESM2",
                                                 "GFDL-ESM4": "GFDL-ESM4",},),
                        ui.input_select("rcp", "RCP scenario",
                                        choices={"Historical": "historical",
                                                 "RCP2.6": "rcp26",
                                                 "RCP4.5": "rcp45",
                                                 "RCP8.5": "rcp85",},),
                    open="always",
                    width="300px",
                    ),  # Set sidebar width (default is 250px)

    ui.navset_card_pill(
        ui.nav_panel("Meteorological", ""),
        ui.nav_panel("Hydrological", ui.output_image("image")),
        ui.nav_panel("Agricultural", ui.output_plot("render_eu3_map", height="800px")),
        title="Drought occurence"),

    ui.navset_card_pill(
        ui.nav_panel("Crop yield", ""),
        ui.nav_panel("Forest carbon uptake"),
        ui.nav_panel("Mortality"),
        title="Impacts")))

page_model_evaluation = ui.page_fluid(
                            ui.h2("Model evaluation with RI data."),
                            "Here comparison of both model outputs" + 
                            "with observations will be shown.",
                            ui.layout_columns(
                                ui.card(ui.output_image("elter_logo")),
                                ui.card(ui.output_image("iriscc_logo")),
                                ui.card(ui.output_image("icos_logo")),
                                col_widths=(4, 4, 4),
                                style="align-items: center;"),

                            ui.h2("Hydrological model intercomparison"),
                            ui.layout_columns(
                                ui.card(ui.output_image("clm5_smi"), height="600px"),
                                ui.card(ui.output_image("mhm_smi"), height="600px"),
                                ui.card(ui.output_image("clm5_mhm_smi_corr"), height="600px"),
                                col_widths=(4, 4, 4),
                                style="align-items: center;"))

app_ui = ui.page_fluid(
            ui.head_content(
                ui.tags.link(rel="stylesheet", href=GOOGLE_FONTS_URL),
                ui.tags.style("""
                    /* Font Strategy - Consistent across Shiny & Matplotlib */
                    body {
                        font-family: Inter, system-ui, -apple-system, sans-serif;
                        letter-spacing: 0.05em; /* Add spacing for readability */
                    }
                    h1, h2, h3, h4, h5, h6 {
                        font-family: 'Crimson Text', serif;
                        font-weight: 400;
                    }
                    code, pre {
                        font-family: 'IBM Plex Mono', monospace;
                    }
                    .shiny-input-label, .form-label {
                        font-family: Inter, system-ui, -apple-system, sans-serif;
                    }
                    
                    /* Slider tick labels - monospace for numeric precision */
                    .irs-grid-text {
                        font-family: 'IBM Plex Mono', monospace !important;
                        font-size: 11px;
                    }
                    
                    /* Navigation labels */
                    .nav-link, .nav-item {
                        font-family: Inter, system-ui, -apple-system, sans-serif;
                    }
                    
                    /* Sidebar text */
                    .bslib-sidebar-layout .sidebar {
                        font-family: Inter, system-ui, -apple-system, sans-serif;
                    }
                    
                    /* Card text */
                    .card-body {
                        font-family: Inter, system-ui, -apple-system, sans-serif;
                    }
                """)
            ),
            
            ui.layout_columns(
                ui.h1("Risk on terrestrial ecosystems functioning to droughts and heatwaves",
                      style="text-align: center;"),
                ui.output_image("iriscc_logo_title", inline=True),
                col_widths=(10, 2),
                style="align-items: center;"),

            ui.navset_card_pill(
                ui.nav_spacer(),
                ui.nav_panel("Droughts and their impacts", page_droughts),
                ui.nav_panel("Model evaluation", page_model_evaluation),
                ui.nav_panel("Uncertainty", "a"),
                ui.nav_panel("References", "a"),
                ui.nav_menu("Further Information",
                            ui.nav_panel("About the data",))),

            theme=dark_theme,

            style="; ".join(["padding-top: 30px",
                             "vertical-align: middle", 
                             "text-align: center", 
                             "padding-left: 30px", 
                             "padding-right: 30px", 
                             "padding-bottom: 30px"]))



def server(input, output, session) -> None:
    """Shiny server function.

    Args:
        input: Input object for accessing reactive inputs from UI
        output: Output object for rendering outputs
        session: Shiny session object

    Returns:
        None
    """
    
    # Use dark theme with custom fonts
    theme_config = get_theme_config("dark")

    @render.plot
    def hist():
        p = sns.histplot(df, x=input.var(), 
                        facecolor=theme_config.colors['primary'], 
                        edgecolor=theme_config.palette['text'])
        return p.set(xlabel=None)
    
    @render.plot
    def render_eu3_map():
        from plots import EU3_map
        from shared import mHM_smi_full
        
        # Get selected decade from the "dec" slider input
        selected_date = input.dec()
        decade_year = selected_date.year
        
        # Get the index for this decade from the mapping
        time_index = decade_to_index.get(decade_year)
        
        if time_index is None:
            # Fallback to first available decade if not found
            decade_year = min(decade_to_index.keys())
            time_index = decade_to_index[decade_year]
        
        # Extract the 2D arrays for this decade (already pre-loaded in memory)
        clm5_smi_data = CLM5_smi_full[time_index]
        mhm_smi_data = mHM_smi_full[time_index]
        
        # Squeeze data if it has extra dimensions
        if len(clm5_smi_data.shape) > 2:
            clm5_smi_data = clm5_smi_data.squeeze()
        if len(mhm_smi_data.shape) > 2:
            mhm_smi_data = mhm_smi_data.squeeze()
        
        vmin = 0.3
        vmax = 0.6
        cmap = "inferno_r"
        
        # Create fresh map instance (required by Shiny's matplotlib backend)
        eu_map_instance = EU3_map(
            suptitle=f"Soil moisture index (SMI) for decade {decade_year}-{decade_year+9}",
            title=[f"CLM5", f"mHM"], 
            description="",
            color_mode="dark",
            theme_config=theme_config
        )
        fig, _, axs = eu_map_instance.create()
        
        # Add data to both plots with same scale
        if lon is not None and lat is not None:
            # Plot CLM5 on left axis
            eu_map_instance.pcolormesh(
                lon, 
                lat, 
                clm5_smi_data,
                ax_num=0,
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
                alpha=0.8
            )
            
            # Plot mHM on right axis
            eu_map_instance.pcolormesh(
                lon, 
                lat, 
                mhm_smi_data,
                ax_num=1,
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
                alpha=0.8
            )
            
            # Add colorbar on the right of both plots
            eu_map_instance.colorbar(
                eu_map_instance.pcolormesh_obj,
                cbar_label='Soil Moisture Index',
                extend='both',
            )
        
        return fig

    @render.data_frame
    def data():
        return df[["species", "island"]]

    @render.image
    def image():
        img: ImgData = {"src": f"{images}/ScalerMatrix.png",
                        "alt": "An example image",
                        "height": "400px"}
        return img

    @render.image
    def iriscc_logo_title():
        img: ImgData = {"src": f"{images}/iriscc-logo-full-horizontal-white.png",
               "alt": "IRISCC logo",
               "width": "130px"}
        return img

    @render.image
    def iriscc_logo():
        img: ImgData = {"src": f"{images}/iriscc-logo-full-horizontal-fullcolor.png",
               "alt": "IRISCC logo",
               "width": "130px"}
        return img

    @render.image
    def elter_logo():
        img: ImgData = {"src": f"{images}/eLTER_Logo.png",
               "alt": "eLTER logo",
               "style": "background-color: white;",
               "width": "130px"}
        return img

    @render.image
    def icos_logo():
        img: ImgData = {"src": f"{images}/ICOS RI_logo_rgb.png",
               "alt": "ICOS RI logo",
               "style": "background-color: white;",
               "width": "130px"}
        return img

    @render.image
    def clm5_smi():
        img: ImgData = {"src": f"{images}/CLM5_SMI_2003_07.nc-1.png",
               "alt": "CLM5 SMI",
               "style": "background-color: white;",
               "width": "500px"}
        return img

    @render.image
    def mhm_smi():
        img: ImgData = {"src": f"{images}/mHM_SMI_2003_07.nc-1.png",
               "alt": "mHM SMI",
               "style": "background-color: white;",
               "width": "500px"}
        return img

    @render.image
    def clm5_mhm_smi_corr():
        img: ImgData = {"src": f"{images}/smi_correlation_mhm_vs_clm5-1.png",
               "alt": "CLM5 mHM SMI correlation",
               "style": "background-color: white;",
               "width": "500px"}
        return img

app = App(app_ui, server)

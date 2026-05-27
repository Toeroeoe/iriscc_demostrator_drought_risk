"""_summary_

Returns:
    _type_: _description_
"""

from datetime import date, timedelta

<<<<<<< HEAD
<<<<<<< HEAD
import matplotlib.pyplot as plt
import seaborn as sns
from shared import (
    CLM5_smi_full,
    SPI_full,
    SPI_lat,
    SPI_lon,
    decade_to_index,
    df,
    discharge_time,
    gauge_map_html,
    gauge_meta,
    get_gauge_discharge,
    images,
    lat,
    lon,
    spi_decade_to_index,
)
=======
import seaborn as sns
from shared import CLM5_smi_full, decade_to_index, df, images, lat, lon
>>>>>>> 1690582 (sonar qube)
=======
import matplotlib.pyplot as plt
import seaborn as sns
from shared import (
    CLM5_smi_full,
    decade_to_index,
    df,
    discharge_time,
    gauge_map_html,
    gauge_meta,
    get_gauge_discharge,
    images,
    lat,
    lon,
)
>>>>>>> 4d49927 (discharge data.. and leaflet map. discharge.nc is kept out for now)
from shiny import App, render, ui
from shiny.types import ImgData
from shinyswatch import theme
from theme_config import GOOGLE_FONTS_URL, get_theme_config

dark_theme = theme.darkly

# The contents of the first 'page' is a navset with two 'panels'.
page_droughts = ui.page_fluid(
    ui.card(
        "Space for introductory text about droughts and their impacts.",
        height="250px",
        style="text-align: left;",
    ),
    ui.page_sidebar(
        ui.sidebar(
            "View settings",
            ui.input_slider(
                "dec",
                "Decade",
                min=date(1960, 1, 2),
                max=date(2020, 1, 10),
                value=date(1960, 1, 2),
                step=timedelta(days=366 * 10),
                time_format="%Y",
                ticks=True,
            ),
            ui.input_select(
                "model",
                "Atmospheric forcing",
                choices={
<<<<<<< HEAD
<<<<<<< HEAD
                    "ERA5": "ERA5",
=======
>>>>>>> 1690582 (sonar qube)
=======
                    "ERA5": "ERA5",
>>>>>>> 4d49927 (discharge data.. and leaflet map. discharge.nc is kept out for now)
                    "Ensemble mean": "ensemble_mean",
                    "CESM2": "CESM2",
                    "GFDL-ESM4": "GFDL-ESM4",
                },
<<<<<<< HEAD
<<<<<<< HEAD
                selected="ERA5",
=======
>>>>>>> 1690582 (sonar qube)
=======
                selected="ERA5",
>>>>>>> 4d49927 (discharge data.. and leaflet map. discharge.nc is kept out for now)
            ),
            ui.input_select(
                "rcp",
                "RCP scenario",
                choices={
                    "Historical": "historical",
                    "RCP2.6": "rcp26",
                    "RCP4.5": "rcp45",
                    "RCP8.5": "rcp85",
                },
            ),
            open="always",
            width="300px",
        ),  # Set sidebar width (default is 250px)
        ui.navset_card_pill(
<<<<<<< HEAD
            ui.nav_panel(
                "Meteorological", ui.output_plot("render_spi_map", height="600px")
            ),
            ui.nav_panel(
                "Hydrological",
                ui.p(
                    "Click a gauge marker to view its discharge time series.",
                    style="text-align:left; color:#888; margin-bottom:6px;",
                ),
                ui.HTML(gauge_map_html),
                ui.output_plot("discharge_plot", height="320px"),
            ),
            ui.nav_panel(
                "Agricultural", ui.output_plot("render_eu3_map", height="800px")
            ),
            title="Drought indices",
=======
            ui.nav_panel("Meteorological", ""),
            ui.nav_panel(
                "Hydrological",
                ui.p(
                    "Click a gauge marker to view its discharge time series.",
                    style="text-align:left; color:#888; margin-bottom:6px;",
                ),
                ui.HTML(gauge_map_html),
                ui.output_plot("discharge_plot", height="320px"),
            ),
            ui.nav_panel(
                "Agricultural", ui.output_plot("render_eu3_map", height="800px")
            ),
            title="Drought occurence",
>>>>>>> 1690582 (sonar qube)
        ),
        ui.navset_card_pill(
            ui.nav_panel("Crop yield", ""),
            ui.nav_panel("Forest carbon uptake"),
            ui.nav_panel("Mortality"),
            title="Impacts",
        ),
    ),
)

# ── Static informational pages ──────────────────────────────────────────────

page_authors = ui.page_fluid(
    ui.h2("Authors & Acknowledgements"),
    ui.hr(),
    ui.h3("Authors"),
    ui.p("[Author names and institutional affiliations]"),
    ui.hr(),
    ui.h3("Acknowledgements"),
    ui.p(
        "This demonstrator is part of the IRISCC project. "
        "The project has received funding from [funding body, grant number / agreement number]. "
        "The authors gratefully acknowledge the contribution of observational data provided by "
        "the eLTER, ICOS, and [other RI] research infrastructures."
    ),
    style="text-align: left; padding: 20px;",
)

page_license = ui.page_fluid(
    ui.h2("License"),
    ui.hr(),
    ui.p(
        '[Insert license name, e.g. "This software is released under the '
        'MIT License" or "CC BY 4.0 International".]'
    ),
    ui.tags.pre(
        "[Paste full license text here]",
        style="white-space: pre-wrap; font-family: 'IBM Plex Mono', monospace; "
        "font-size: 0.85em; padding: 16px;",
    ),
    style="text-align: left; padding: 20px;",
)

page_legal = ui.page_fluid(
    ui.h2("Legal Notice, Data Protection & Accessibility"),
    ui.hr(),
    ui.h3("Legal Notice (Impressum)"),
    ui.p(ui.tags.strong("Responsible organisation:")),
    ui.p("[Institution name]"),
    ui.p("[Street address, postcode, city, country]"),
    ui.p(ui.tags.strong("Contact:"), " [contact e-mail or phone number]"),
    ui.p(ui.tags.strong("Represented by:"), " [name / role]"),
    ui.hr(),
    ui.h3("Data Protection"),
    ui.p(
        "This demonstrator application does not collect, store, or process any personal data. "
        "No cookies beyond those strictly necessary for the application's operation are set, "
        "and no usage tracking or analytics are employed."
    ),
    ui.p(
        "If you have questions regarding data protection, or wish to exercise rights under "
        "the General Data Protection Regulation (GDPR), please contact: [data-protection contact or DPO e-mail]."
    ),
    ui.hr(),
    ui.h3("Accessibility"),
    ui.p(
        "We aim to make this application accessible in accordance with the "
        "Web Content Accessibility Guidelines (WCAG) 2.1, Level AA, and "
        "Directive (EU) 2016/2102 on the accessibility of public-sector websites."
    ),
    ui.p(
        "Known limitations: [describe any known gaps here]. "
        "If you encounter accessibility barriers or need content in an alternative format, "
        "please contact us at: [accessibility contact e-mail]."
    ),
    style="text-align: left; padding: 20px;",
)

# ── Model-evaluation page ─────────────────────────────────────────────────────

page_model_evaluation = ui.page_fluid(
    ui.h2("Model evaluation with RI data."),
    "Here comparison of both model outputs" + "with observations will be shown.",
    ui.layout_columns(
        ui.card(ui.output_image("elter_logo")),
        ui.card(ui.output_image("iriscc_logo")),
        ui.card(ui.output_image("icos_logo")),
        col_widths=(4, 4, 4),
        style="align-items: center;",
    ),
    ui.h2("Hydrological model intercomparison"),
    ui.layout_columns(
        ui.card(ui.output_image("clm5_smi"), height="600px"),
        ui.card(ui.output_image("mhm_smi"), height="600px"),
        ui.card(ui.output_image("clm5_mhm_smi_corr"), height="600px"),
        col_widths=(4, 4, 4),
        style="align-items: center;",
    ),
)

app_ui = ui.page_fluid(
    ui.head_content(
        ui.tags.link(rel="stylesheet", href=GOOGLE_FONTS_URL),
<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> 4d49927 (discharge data.. and leaflet map. discharge.nc is kept out for now)
        # Leaflet – loaded in the head so the map script in the Hydrological
        # tab can reference L.* as soon as it runs.
        ui.tags.link(
            rel="stylesheet",
            href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
        ),
        ui.tags.script(src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"),
<<<<<<< HEAD
        # Proj4.js + Proj4Leaflet — needed for non-Mercator CRS in Leaflet
        ui.tags.script(
            src="https://cdnjs.cloudflare.com/ajax/libs/proj4js/2.15.0/proj4.js"
        ),
        ui.tags.script(
            src="https://cdn.jsdelivr.net/npm/proj4leaflet@1.0.2/src/proj4leaflet.js"
        ),
=======
>>>>>>> 1690582 (sonar qube)
=======
>>>>>>> 4d49927 (discharge data.. and leaflet map. discharge.nc is kept out for now)
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
                """),
    ),
    ui.layout_columns(
        ui.h1(
            "Risk on terrestrial ecosystems functioning to droughts and heatwaves",
            style="text-align: center;",
        ),
        ui.output_image("iriscc_logo_title", inline=True),
        col_widths=(10, 2),
        style="align-items: center;",
    ),
    ui.navset_card_pill(
        ui.nav_spacer(),
        ui.nav_panel("Droughts and their impacts", page_droughts),
<<<<<<< HEAD
<<<<<<< HEAD
        ui.nav_panel("Uncertainty", "a"),
        ui.nav_panel("Model evaluation", page_model_evaluation),
=======
        ui.nav_panel("Model evaluation", page_model_evaluation),
        ui.nav_panel("Uncertainty", "a"),
>>>>>>> 1690582 (sonar qube)
=======
        ui.nav_panel("Uncertainty", "a"),
        ui.nav_panel("Model evaluation", page_model_evaluation),
>>>>>>> 4d49927 (discharge data.. and leaflet map. discharge.nc is kept out for now)
        ui.nav_menu(
            "Further Information",
            ui.nav_panel("About the data"),
            ui.nav_panel("References", "a"),
            "---",
            ui.nav_panel("Authors & Acknowledgements", page_authors),
            ui.nav_panel("LICENSE", page_license),
            "---",
            ui.nav_panel("Legal Notice", page_legal),
        ),
        id="main_navset",
    ),
    # ── Footer ────────────────────────────────────────────────────────
    ui.tags.footer(
        ui.tags.hr(style="margin-top: 30px; opacity: 0.25;"),
        ui.tags.p(
            ui.tags.a(
                "Legal Notice | Data Protection | Accessibility",
                href="#",
                onclick=(
                    "document.querySelector('[data-value=\"Legal Notice\"]')"
                    ".click(); return false;"
                ),
                style="color: #888; text-decoration: none;",
            ),
            style=(
                "text-align: center; padding: 14px 0 24px 0; "
                "font-size: 0.82em; color: #888;"
            ),
        ),
    ),
    theme=dark_theme,
    style="; ".join(
        [
            "padding-top: 30px",
            "vertical-align: middle",
            "text-align: center",
            "padding-left: 30px",
            "padding-right: 30px",
            "padding-bottom: 30px",
        ]
    ),
)


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
        p = sns.histplot(
            df,
            x=input.var(),
            facecolor=theme_config.colors["primary"],
            edgecolor=theme_config.palette["text"],
        )
        return p.set(xlabel=None)

<<<<<<< HEAD
    @render.plot
    def render_spi_map():
        from plots import EU1_map

        selected_date = input.dec()
        decade_year = selected_date.year
        model = input.model()

        _model_labels = {
            "ERA5": "ERA5",
            "ensemble_mean": "Ensemble mean",
            "CESM2": "CESM2",
            "GFDL-ESM4": "GFDL-ESM4",
        }
        model_label = _model_labels.get(model, model)

        # Only ERA5 forcing data is currently available for SPI
        if model != "ERA5":
            c = theme_config.colors
            fig, ax = plt.subplots(figsize=(4, 1.5))
            fig.patch.set_facecolor(c["background"])
            ax.set_facecolor(c["background"])
            ax.text(
                0.5,
                0.5,
                f'SPI data for "{model_label}" is not yet available.',
                ha="center",
                va="center",
                color=c["text"],
                fontsize=11,
                transform=ax.transAxes,
            )
            ax.axis("off")
            return fig

        time_index = spi_decade_to_index.get(decade_year)
        if time_index is None:
            decade_year = min(spi_decade_to_index.keys())
            time_index = spi_decade_to_index[decade_year]

        spi_data = SPI_full[time_index]

        spi_map = EU1_map(
            suptitle=(
                f"Standardized Precipitation Index (SPI)\n"
                f"{model_label}, {decade_year}–{decade_year + 9}"
            ),
            title=[],  # single title only — avoids overlap with suptitle
            description="",
            color_mode="dark",
            theme_config=theme_config,
            cbar_width_ratio=0.04,
        )
        fig, _, _ = spi_map.create()

        spi_map.pcolormesh(
            SPI_lon,
            SPI_lat,
            spi_data,
            cmap="RdBu",
            vmin=-0.5,
            vmax=0.5,
            alpha=0.85,
        )
        spi_map.colorbar(
            spi_map.pcolormesh_obj,
            cbar_label="SPI (dimensionless)",
            extend="both",
        )
        return fig

=======
>>>>>>> 1690582 (sonar qube)
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
            suptitle=f"Soil moisture index (SMI) for decade {decade_year}-{decade_year + 9}",
<<<<<<< HEAD
            title=["CLM5", "mHM"],
=======
            title=[f"CLM5", f"mHM"],
>>>>>>> 1690582 (sonar qube)
            description="",
            color_mode="dark",
            theme_config=theme_config,
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
                alpha=0.8,
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
                alpha=0.8,
            )

            # Add colorbar on the right of both plots
            eu_map_instance.colorbar(
                eu_map_instance.pcolormesh_obj,
                cbar_label="Soil Moisture Index",
                extend="both",
            )

<<<<<<< HEAD
        return fig

    @render.plot
    def discharge_plot():
        """Render observed + simulated discharge for the clicked gauge."""
        # selected_gauge is injected by the Leaflet JS via Shiny.setInputValue;
        # it doesn't exist until the user clicks, so guard against that.
        try:
            gauge_id = input.selected_gauge()
        except Exception:
            return None
        if not gauge_id:
            return None

        qobs, qsim = get_gauge_discharge(gauge_id)
        if qobs is None and qsim is None:
            return None

        # Gauge label from metadata
        row = gauge_meta.loc[gauge_meta["gauge_id"] == gauge_id]
        if not row.empty:
            r = row.iloc[0]
            title = f"{r['river']} at {r['station']} ({r['country']})"
        else:
            title = gauge_id

        tc = get_theme_config("dark")
        c = tc.colors

        # Aggregate daily → monthly means for a readable comparison
        import pandas as pd

        qobs_mo = (
            pd.Series(qobs, index=discharge_time).resample("ME").mean()
            if qobs is not None
            else None
        )
        qsim_mo = (
            pd.Series(qsim, index=discharge_time).resample("ME").mean()
            if qsim is not None
            else None
        )

        fig, ax = plt.subplots(figsize=(12, 3.5))
        fig.patch.set_facecolor(c["background"])
        ax.set_facecolor(c["background"])

        if qobs_mo is not None:
            ax.plot(
                qobs_mo.index,
                qobs_mo.values,
                color=c["primary"],
                linewidth=0.9,
                alpha=0.9,
                label="Observed",
            )
        if qsim_mo is not None:
            ax.plot(
                qsim_mo.index,
                qsim_mo.values,
                color="#bb86fc",
                linewidth=1.2,
                alpha=0.9,
                label="Simulated",
            )

        ax.set_title(title, color=c["text"], fontsize=12, pad=8)
        ax.set_ylabel("Discharge (m\u00b3 s\u207b\u00b9)", color=c["text"])
        ax.set_xlabel("Date", color=c["text"])
        ax.tick_params(colors=c["text"])
        for spine in ax.spines.values():
            spine.set_edgecolor(c["border"])
        ax.legend(
            facecolor=c["background"],
            edgecolor=c["border"],
            labelcolor=c["text"],
            fontsize=10,
        )
        ax.grid(True, color=c["border"], alpha=0.3, linewidth=0.5)
        fig.tight_layout()
=======
>>>>>>> 1690582 (sonar qube)
        return fig

    @render.plot
    def discharge_plot():
        """Render observed + simulated discharge for the clicked gauge."""
        # selected_gauge is injected by the Leaflet JS via Shiny.setInputValue;
        # it doesn't exist until the user clicks, so guard against that.
        try:
            gauge_id = input.selected_gauge()
        except Exception:
            return None
        if not gauge_id:
            return None

        qobs, qsim = get_gauge_discharge(gauge_id)
        if qobs is None and qsim is None:
            return None

        # Gauge label from metadata
        row = gauge_meta.loc[gauge_meta["gauge_id"] == gauge_id]
        if not row.empty:
            r = row.iloc[0]
            title = f"{r['river']} at {r['station']} ({r['country']})"
        else:
            title = gauge_id

        tc = get_theme_config("dark")
        c = tc.colors

        # Aggregate daily → monthly means for a readable comparison
        import pandas as pd

        qobs_mo = (
            pd.Series(qobs, index=discharge_time).resample("ME").mean()
            if qobs is not None
            else None
        )
        qsim_mo = (
            pd.Series(qsim, index=discharge_time).resample("ME").mean()
            if qsim is not None
            else None
        )

        fig, ax = plt.subplots(figsize=(12, 3.5))
        fig.patch.set_facecolor(c["background"])
        ax.set_facecolor(c["background"])

        if qobs_mo is not None:
            ax.plot(
                qobs_mo.index,
                qobs_mo.values,
                color=c["primary"],
                linewidth=0.9,
                alpha=0.9,
                label="Observed (Q\u2080\u2087\u2085)",
            )
        if qsim_mo is not None:
            ax.plot(
                qsim_mo.index,
                qsim_mo.values,
                color="#bb86fc",
                linewidth=1.2,
                alpha=0.9,
                label="Simulated (Q\u209b\u1d35\u2098)",
            )

        ax.set_title(title, color=c["text"], fontsize=12, pad=8)
        ax.set_ylabel("Discharge (m\u00b3 s\u207b\u00b9)", color=c["text"])
        ax.set_xlabel("Date", color=c["text"])
        ax.tick_params(colors=c["text"])
        for spine in ax.spines.values():
            spine.set_edgecolor(c["border"])
        ax.legend(
            facecolor=c["background"],
            edgecolor=c["border"],
            labelcolor=c["text"],
            fontsize=10,
        )
        ax.grid(True, color=c["border"], alpha=0.3, linewidth=0.5)
        fig.tight_layout()
        return fig

    @render.data_frame
    def data():
        return df[["species", "island"]]

    @render.image
    def image():
        img: ImgData = {
            "src": f"{images}/ScalerMatrix.png",
            "alt": "An example image",
            "height": "400px",
        }
        return img

    @render.image
    def iriscc_logo_title():
        img: ImgData = {
            "src": f"{images}/iriscc-logo-full-horizontal-white.png",
            "alt": "IRISCC logo",
            "width": "130px",
        }
        return img

    @render.image
    def iriscc_logo():
        img: ImgData = {
            "src": f"{images}/iriscc-logo-full-horizontal-fullcolor.png",
            "alt": "IRISCC logo",
            "width": "130px",
        }
        return img

    @render.image
    def elter_logo():
        img: ImgData = {
            "src": f"{images}/eLTER_Logo.png",
            "alt": "eLTER logo",
            "style": "background-color: white;",
            "width": "130px",
        }
        return img

    @render.image
    def icos_logo():
        img: ImgData = {
            "src": f"{images}/ICOS RI_logo_rgb.png",
            "alt": "ICOS RI logo",
            "style": "background-color: white;",
            "width": "130px",
        }
        return img

    @render.image
    def clm5_smi():
        img: ImgData = {
            "src": f"{images}/CLM5_SMI_2003_07.nc-1.png",
            "alt": "CLM5 SMI",
            "style": "background-color: white;",
            "width": "500px",
        }
        return img

    @render.image
    def mhm_smi():
        img: ImgData = {
            "src": f"{images}/mHM_SMI_2003_07.nc-1.png",
            "alt": "mHM SMI",
            "style": "background-color: white;",
            "width": "500px",
        }
        return img

    @render.image
    def clm5_mhm_smi_corr():
        img: ImgData = {
            "src": f"{images}/smi_correlation_mhm_vs_clm5-1.png",
            "alt": "CLM5 mHM SMI correlation",
            "style": "background-color: white;",
            "width": "500px",
        }
        return img


app = App(app_ui, server)

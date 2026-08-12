"""_summary_

Returns:
    _type_: _description_
"""

from datetime import date, timedelta

import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import numpy as np
import re
from shared import (
    SMI_lat,
    SMI_lon,
    SMI_STAT_DATA_BY_THRESH,
    DEFAULT_SMI_THRESH,
    SMI_THRESHOLDS,
    SPI_lat,
    SPI_lon,
    SPI_STAT_DATA,
    SPI_THRESHOLDS,
    DEFAULT_SPI_AGG,
    DEFAULT_SPI_THRESH,
    discharge_time,
    gauge_map_html,
    gauge_meta,
    get_gauge_discharge,
    images,
)
from shiny import App, render, ui
from shiny.types import ImgData
from shinyswatch import theme
from theme_config import GOOGLE_FONTS_URL, get_theme_config

dark_theme = theme.darkly

# Atmospheric-forcing display labels (shared by the map and its caption).
MODEL_LABELS = {
    "ERA5": "ERA5",
    "ensemble_mean": "Ensemble mean",
    "CESM2": "CESM2",
    "GFDL-ESM4": "GFDL-ESM4",
}

# Per-statistic plotting configuration for the meteorological (SPI) map.
# `scale` is applied to the raw field before plotting (e.g. fraction → %).
# `meaning` is a plain-language clause used to build the plot caption.

# SPI threshold severity descriptions for text captions
SPI_THRESHOLD_LABELS = {
    -1.0: "Abnormally dry or worse",
    -1.5: "Moderate drought or worse",
    -2.0: "Severe drought or worse",
}

SPI_STATISTICS = {
    "mean": {
        "label": "Mean index",
        "cmap": "RdBu",
        "vmin": -0.5,
        "vmax": 0.5,
        "extend": "both",
        "scale": 1.0,
        "cbar_label": "Mean SPI (dimensionless)",
        "meaning": (
            "The decadal average of the 92-day SPI. Values below zero mark "
            "drier-than-average conditions, but the decadal mean smooths over "
            "individual dry and wet spells and is hard to interpret on its own"
        ),
    },
    "dfreq": {
        "label": "Drought frequency",
        "cmap": "YlOrRd",
        "vmin": 0.0,
        "vmax": 40.0,
        "extend": "max",
        "scale": 100.0,
        "cbar_label": "Time in drought (%)",
        "meaning": (
            "The share of time the 92-day SPI stayed at or below a threshold "
            "(moderate drought or worse); higher values mean drought conditions "
            "occurred more often during the decade"
        ),
    },
    "min": {
        "label": "Peak severity",
        "cmap": "YlOrRd_r",
        "vmin": -4.0,
        "vmax": -1.0,
        "extend": "min",
        "scale": 1.0,
        "cbar_label": "Minimum SPI reached",
        "meaning": (
            "The most negative 92-day SPI reached during the decade — the single "
            "most severe meteorological drought; more negative values indicate "
            "more extreme dry peaks"
        ),
    },
    "maxspell": {
        "label": "Longest dry spell",
        "cmap": "YlOrRd",
        "vmin": 0.0,
        "vmax": 200.0,
        "extend": "max",
        "scale": 1.0,
        "cbar_label": "Longest spell (days)",
        "meaning": (
            "The length of the longest uninterrupted period with the 92-day SPI "
            "at or below a threshold; longer spells indicate more persistent drought"
        ),
    },
}

# Custom color scheme for SMI mean statistic (from R code)
# Colors: dark red (dry) to dark blue (wet)
SMI_COLORS = [
    "#730000",  # very dry
    "#E60000",  # dry
    "#FFAA00",  # moderately dry
    "#FCD37F",  # slightly dry
    "#FFFE01",  # near normal
    "transparent",  # normal (will be handled specially)
    "#C6EAC3",  # slightly wet
    "#79CA6C",  # moderately wet
    "#4CA666",  # wet
    "#2C6476",  # very wet
    "#0E1D43"   # extremely wet
]
# Breakpoints: 0 to 1 for SMI index
SMI_BREAKS = [0.0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.7, 0.8, 0.9, 0.95, 0.98, 1.0]

# Create custom colormap and norm for SMI mean
# Note: The middle "transparent" value (0.3-0.7) should actually be a normal color
# Looking at the R code, it seems like 0.3-0.7 is meant to be near-normal/neutral
# Let's use a light color for the middle range instead of transparent
SMI_COLORS_ADJUSTED = [
    "#730000",  # 0.0-0.02: very dry
    "#E60000",  # 0.02-0.05: dry
    "#FFAA00",  # 0.05-0.1: moderately dry
    "#FCD37F",  # 0.1-0.2: slightly dry
    "#FFFE01",  # 0.2-0.3: near normal
    "#FFFFFF",  # 0.3-0.7: normal (white/neutral)
    "#C6EAC3",  # 0.7-0.8: slightly wet
    "#79CA6C",  # 0.8-0.9: moderately wet
    "#4CA666",  # 0.9-0.95: wet
    "#2C6476",  # 0.95-0.98: very wet
    "#0E1D43"   # 0.98-1.0: extremely wet
]
SMI_CMAP = ListedColormap(SMI_COLORS_ADJUSTED)
SMI_NORM = BoundaryNorm(SMI_BREAKS, SMI_CMAP.N)

# SMI threshold severity descriptions for text captions (lower SMI = drier)
SMI_THRESHOLD_LABELS = {
    0.0: "Exceptional drought or worse",
    0.2: "Extreme drought or worse",
    0.3: "Severe drought or worse",
    0.5: "Moderate drought or worse",
}

# Per-statistic plotting configuration for the agricultural (SMI) maps.
# SMI is a 0..1 soil-moisture index (0 = driest). Two hydrological models
# (CLM5, mHM) are shown side by side, so there is no atmospheric-forcing choice.
SMI_STATISTICS = {
    "mean": {
        "label": "Mean index",
        "cmap": SMI_CMAP,  # Custom color scheme for SMI
        "norm": SMI_NORM,  # Custom boundaries for color mapping
        "vmin": 0.0,
        "vmax": 1.0,
        "extend": "neither",  # No over/under colors needed
        "scale": 1.0,
        "cbar_label": "Mean SMI (dimensionless)",
        "meaning": (
            "The decadal average of soil moisture (SMI). Values closer to 0 indicate drier "
            "conditions on average, while values closer to 1 indicate wetter conditions. "
            "The mean smooths over individual dry and wet spells and represents overall moisture availability"
        ),
    },
    "dfreq": {
        "label": "Drought frequency",
        "cmap": "YlOrRd",
        "vmin": 0.0,
        "vmax": 40.0,
        "extend": "max",
        "scale": 100.0,
        "cbar_label": "Time in drought (%)",
        "meaning": (
            "The share of time the soil moisture (SMI) stayed at or below a threshold "
            "(moderate drought or worse); higher values mean drought conditions "
            "occurred more often during the decade"
        ),
    },
    "min": {
        "label": "Peak severity",
        "cmap": SMI_CMAP,  # Same custom color scheme as mean (0-1 SMI scale)
        "norm": SMI_NORM,  # Same boundaries for consistency
        "vmin": 0.0,
        "vmax": 1.0,
        "extend": "neither",
        "scale": 1.0,
        "cbar_label": "Minimum SMI reached",
        "meaning": (
            "The lowest soil moisture (SMI) value reached during the decade — the single "
            "most severe agricultural drought; lower values indicate more extreme dry conditions"
        ),
    },
    "maxspell": {
        "label": "Longest dry spell",
        "cmap": "YlOrRd",
        "vmin": 0.0,
        "vmax": 200.0,
        "extend": "max",
        "scale": 1.0,
        "cbar_label": "Longest spell (days)",
        "meaning": (
            "The length of the longest uninterrupted period with soil moisture (SMI) "
            "at or below a threshold; longer spells indicate more persistent drought"
        ),
    },
}

def _blank_ocean(data, mean_map, decade_year):
    """Blank cells that are ocean/missing in the reference mean field.

    Some statistic files (notably maxspell/dfreq from CDO's consecsum) store
    ocean as 0 rather than a fill value, which would otherwise be drawn at the
    bottom of the colour scale instead of revealing the ocean basemap. The mean
    field is reliably masked, so we use its NaN pattern as the land-sea mask.
    """
    if mean_map is not None and decade_year in mean_map:
        return np.where(np.isnan(mean_map[decade_year]), np.nan, data)
    return data


# The contents of the first 'page' is a navset with two 'panels'.
page_droughts = ui.page_fluid(
    ui.card(
        ui.markdown(
            """

            Droughts are among the most far-reaching climate-related hazards.
            They develop slowly, but their effects can be severe and widespread. A drought is defined as precipitation persistently below normal levels (a *meteorological drought*). If the deficit continues and is potentially accompanied by an increased water demand from a dry atmosphere, it depletes soil moisture and reduces water available to plants (an *agricultural drought*). Eventually, it can lower river discharge (a *hydrological drought*).

            These interlinked forms of drought place terrestrial ecosystems and
            the services they provide under considerable stress. They reduce
            crop yields and forest carbon uptake, threaten drinking-water and
            energy supplies, and can amplify heatwaves and the risk of
            wildfires. Under a warming climate, droughts are expected to become
            more frequent and more severe across many regions of Europe.

            This demonstrator lets you explore how meteorological,
            hydrological, and agricultural droughts have evolved over recent
            decades and what they mean for ecosystem functioning. Use the
            **view settings** on the left to select a decade, atmospheric
            forcing, and emission scenario, and switch between the tabs to
            examine drought occurrence and its impacts.
            """
        ),
        style="text-align: left;",
    ),
    ui.page_sidebar(
        ui.sidebar(
            "View settings",
            ui.div(
                ui.tags.strong(
                    "Reference period: 1960–1999",
                    style="font-size: 0.85em;",
                ),
                ui.tags.br(),
                ui.tags.span(
                    "All drought indices are calculated relative to this "
                    "baseline period.",
                    style="font-size: 0.75em;",
                ),
                style=(
                    "border: 1px solid #f0ad4e; "
                    "border-left: 4px solid #f0ad4e; "
                    "background-color: rgba(240, 173, 78, 0.12); "
                    "border-radius: 6px; "
                    "padding: 10px 12px; "
                    "margin-bottom: 14px; "
                    "text-align: left;"
                ),
            ),
            ui.input_slider(
                "dec",
                "Decade",
                min=date(1960, 1, 2),
                max=date(2010, 1, 10),
                value=date(1960, 1, 2),
                step=timedelta(days=366 * 10),
                time_format="%Y",
                ticks=True,
            ),
            ui.input_select(
                "statistic",
                "Statistic",
                choices={
                    "dfreq": "Drought frequency",
                    "maxspell": "Longest dry spell",
                    "min": "Peak severity",
                    "mean": "Mean index",
                },
                selected="dfreq",
            ),
            ui.output_ui("dynamic_threshold_slider"),
            ui.input_select(
                "model",
                "Atmospheric forcing",
                choices={
                    "ERA5": "ERA5",
                    "Ensemble mean": "ensemble_mean",
                    "CESM2": "CESM2",
                    "GFDL-ESM4": "GFDL-ESM4",
                },
                selected="ERA5",
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
        ),
        ui.navset_card_pill(
            ui.nav_panel(
                "Meteorological",
                ui.row(
                    ui.column(
                        9,  # 7/12 ≈ 58% width
                        ui.output_plot("render_spi_map", height="600px"),
                        style="margin: 0 auto;",  # Center the column
                    ),
                ),
            ui.output_ui("spi_caption"),
            ),
            ui.nav_panel(
                "Agricultural",
                ui.row(
                    ui.column(
                        11,
                        ui.output_plot("render_eu3_map", height="650px"),

                        style="margin: 0 auto;"
                    ),
                ),
                ui.output_ui("smi_caption"),
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
            id="drought_tab",  # Add id to detect active tab
            title="Drought occurence",  # Tab set title
        ),
        ui.navset_card_pill(
            ui.nav_panel("Crop yield", ""),
            ui.nav_panel("Forest carbon uptake"),
            ui.nav_panel("Mortality"),
            title="Impacts",
        ),
    ),  # Close page_sidebar
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
        # Warm up the Google Fonts connection before the stylesheet request so
        # web-UI fonts arrive sooner (matplotlib uses the bundled fonts).
        ui.tags.link(rel="preconnect", href="https://fonts.googleapis.com"),
        ui.tags.link(
            rel="preconnect",
            href="https://fonts.gstatic.com",
            crossorigin="anonymous",
        ),
        ui.tags.link(rel="stylesheet", href=GOOGLE_FONTS_URL),
        # Leaflet – loaded in the head so the map script in the Hydrological
        # tab can reference L.* as soon as it runs.
        ui.tags.link(
            rel="stylesheet",
            href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
        ),
        ui.tags.script(src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"),
        # Proj4.js + Proj4Leaflet — needed for EPSG:3035 LAEA equal-area projection
        ui.tags.script(
            src="https://cdnjs.cloudflare.com/ajax/libs/proj4js/2.15.0/proj4.js"
        ),
        ui.tags.script(
            src="https://cdn.jsdelivr.net/npm/proj4leaflet@1.0.2/src/proj4leaflet.js"
        ),
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
            "Risk on terrestrial ecosystems functioning to droughts",
            style="text-align: center;",
        ),
        ui.output_image("iriscc_logo_title", inline=True),
        col_widths=(10, 2),
        style="align-items: center;",
    ),
    ui.navset_card_pill(
        ui.nav_spacer(),
        ui.nav_panel("Droughts and their impacts", page_droughts),
        ui.nav_panel("Uncertainty", "a"),
        ui.nav_panel("Model evaluation", page_model_evaluation),
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

    def _message_fig(message: str):
        """Return a small figure showing an informational message."""
        c = theme_config.colors
        fig, ax = plt.subplots(figsize=(4, 1.5))
        fig.patch.set_facecolor(c["background"])
        ax.set_facecolor(c["background"])
        ax.text(
            0.5,
            0.5,
            message,
            ha="center",
            va="center",
            color=c["text"],
            fontsize=11,
            wrap=True,
            transform=ax.transAxes,
        )
        ax.axis("off")
        return fig

    @render.ui
    def dynamic_threshold_slider():
        """Dynamically show threshold slider based on active tab and statistic.

        - mean: No threshold (mean index value)
        - min (peak severity): No threshold (minimum value reached)
        - dfreq, maxspell: Show threshold (depends on threshold for counting)
        """
        stat_key = input.statistic()
        active_tab = input.drought_tab()  # Get active tab from navset

        # Statistics that don't use thresholds
        if stat_key in ["mean", "min"]:
            return None

        # Show threshold based on active tab (for dfreq and maxspell)
        if active_tab == "Meteorological":
            # Show SPI threshold as a slider with discrete steps
            if SPI_THRESHOLDS:
                # Calculate step size from available thresholds (e.g., -2, -1.5, -1 = step of 0.5)
                if len(SPI_THRESHOLDS) >= 2:
                    step_size = SPI_THRESHOLDS[1] - SPI_THRESHOLDS[0]
                else:
                    step_size = 0.5

                return ui.div(
                    ui.input_slider(
                        "spi_thresh",
                        "SPI threshold",
                        min=min(SPI_THRESHOLDS),
                        max=max(SPI_THRESHOLDS),
                        value=DEFAULT_SPI_THRESH if DEFAULT_SPI_THRESH is not None else -1.0,
                        step=step_size,
                        ticks=True,
                    )
                )
        elif active_tab == "Agricultural":
            # Show SMI threshold
            if SMI_THRESHOLDS:
                return ui.div(
                    ui.input_slider(
                        "smi_thresh",
                        "SMI threshold",
                        min=min(SMI_THRESHOLDS),
                        max=max(SMI_THRESHOLDS),
                        value=DEFAULT_SMI_THRESH if DEFAULT_SMI_THRESH is not None else 0.0,
                        step=0.1,
                        ticks=True,
                    )
                )

        return None

    @render.plot
    def render_spi_map():
        from plots import EU1_map

        # Check if we're on the Meteorological tab first
        active_tab = input.drought_tab()
        if active_tab != "Meteorological":
            # Don't render if not on the correct tab
            return _message_fig("Select the Meteorological tab to view SPI data.")

        decade_year = input.dec().year
        model = input.model()
        stat_key = input.statistic()
        stat = SPI_STATISTICS.get(stat_key, SPI_STATISTICS["mean"])
        model_label = MODEL_LABELS.get(model, model)

        # Only ERA5 forcing data is currently available for SPI
        if model != "ERA5":
            return _message_fig(
                f'SPI data for "{model_label}" is not yet available.'
            )

        # Verify we have latitude / longitude for the selected aggregation
        if SPI_lat is None or SPI_lon is None:
            return _message_fig(
                "SPI latitude/longitude data not available – cannot draw map."
            )

        # Get the SPI threshold - handle case where slider doesn't exist (for 'mean' and 'min' stats)
        # Use the first available threshold as fallback
        selected_thresh = None

        # Try to get the input value
        try:
            spi_thresh_val = input.spi_thresh()
            if spi_thresh_val is not None:
                selected_thresh = float(spi_thresh_val)
        except (RuntimeError, TypeError, AttributeError):
            # input.spi_thresh() doesn't exist yet
            pass

        # Fallback to first available threshold if we don't have a valid value
        if selected_thresh is None or SPI_THRESHOLDS is None or len(SPI_THRESHOLDS) == 0:
            selected_thresh = SPI_THRESHOLDS[0] if SPI_THRESHOLDS else -1.0
        else:
            # Find the nearest available threshold
            selected_thresh = min(SPI_THRESHOLDS, key=lambda t: abs(t - selected_thresh))

        spi_thresh = selected_thresh
        stat_data = SPI_STAT_DATA.get(DEFAULT_SPI_AGG, {}).get(spi_thresh, {}).get(stat_key, {})
        if not stat_data:
            return _message_fig(
                f'The "{stat["label"]}" statistic has not been computed yet.'
            )

        # Fall back to the earliest available decade if this one is missing
        if decade_year not in stat_data:
            decade_year = min(stat_data.keys())

        spi_data = stat_data[decade_year] * stat["scale"]
        spi_data = _blank_ocean(spi_data, SPI_STAT_DATA.get(DEFAULT_SPI_AGG, {}).get(spi_thresh, {}).get("mean"), decade_year)

        # For drought frequency, calculate dynamic vmin/vmax based on actual data range
        # This makes the colormap more informative when actual values vary significantly
        if stat_key == "dfreq":
            # Calculate min/max excluding NaN values
            valid_data = spi_data[~np.isnan(spi_data)]
            if len(valid_data) > 0:
                data_min = float(np.nanmin(valid_data))
                data_max = float(np.nanmax(valid_data))
                # Add small padding (5% of range) to avoid edge clipping
                data_range = data_max - data_min
                padding = data_range * 0.05 if data_range > 0 else 1.0
                dynamic_vmin = max(0, data_min - padding)  # Don't go below 0 for percentage
                dynamic_vmax = min(100, data_max + padding)  # Cap at 100 for percentage (not 40!)
            else:
                dynamic_vmin, dynamic_vmax = 0, 100
        else:
            dynamic_vmin, dynamic_vmax = stat["vmin"], stat["vmax"]

        spi_map = EU1_map(
            suptitle=f"Meteorological drought \u2014 {stat['label']}",
            title=[],  # single title only — avoids overlap with suptitle
            description="",
            color_mode="dark",
            theme_config=theme_config,
            cbar_width_ratio=0.04,
        )
        fig, _, _ = spi_map.create()

        # Determine coordinate arrays for pcolormesh
        # SPI now uses curvilinear 2D coordinates (xc/yc) from domain file
        if SPI_lon is None or SPI_lat is None:
            # Fallback to index grid if coordinates not available
            lon_grid, lat_grid = np.meshgrid(
                np.arange(spi_data.shape[1]),
                np.arange(spi_data.shape[0])
            )
        elif SPI_lon.ndim == 2 and SPI_lat.ndim == 2:
            # Use 2D curvilinear coordinates directly (already meshgrid format)
            if SPI_lon.shape == SPI_lat.shape == spi_data.shape:
                lon_grid = SPI_lon
                lat_grid = SPI_lat
            else:
                # Shape mismatch - fallback to index grid
                lon_grid, lat_grid = np.meshgrid(
                    np.arange(spi_data.shape[1]),
                    np.arange(spi_data.shape[0])
                )
        elif SPI_lon.ndim == 1 and SPI_lat.ndim == 1:
            # Use 1D coordinate arrays and create meshgrid
            if (SPI_lon.size == spi_data.shape[1] and SPI_lat.size == spi_data.shape[0]):
                lon_grid, lat_grid = np.meshgrid(SPI_lon, SPI_lat)
            else:
                # Size mismatch - fallback to index grid
                lon_grid, lat_grid = np.meshgrid(
                    np.arange(spi_data.shape[1]),
                    np.arange(spi_data.shape[0])
                )
        else:
            # Unknown format - fallback to index grid
            lon_grid, lat_grid = np.meshgrid(
                np.arange(spi_data.shape[1]),
                np.arange(spi_data.shape[0])
            )

        spi_map.pcolormesh(
            lon_grid,
            lat_grid,
            spi_data,
            cmap=stat["cmap"],
            vmin=dynamic_vmin,
            vmax=dynamic_vmax,
            alpha=0.85,
        )
        spi_map.colorbar(
            spi_map.pcolormesh_obj,
            cbar_label=stat["cbar_label"],
            extend=stat["extend"],
        )
        return fig

    @render.ui
    def spi_caption():
        decade_year = input.dec().year
        model = input.model()
        stat_key = input.statistic()
        stat = SPI_STATISTICS.get(stat_key, SPI_STATISTICS["mean"])
        model_label = MODEL_LABELS.get(model, model)

        if model != "ERA5":
            text = (
                f'SPI data for the \u201c{model_label}\u201d forcing is not yet '
                "available. Select \u201cERA5\u201d to view the maps."
            )
        else:
            # spi_thresh is now a float from the slider input
            spi_thresh = float(input.spi_thresh())
            stat_data = SPI_STAT_DATA.get(DEFAULT_SPI_AGG, {}).get(spi_thresh, {}).get(stat_key, {})
            shown_year = (
                decade_year
                if decade_year in stat_data or not stat_data
                else min(stat_data.keys())
            )

            # Build the meaning text with the actual threshold value for dfreq and maxspell
            if stat_key in ["dfreq", "maxspell"]:
                base_meaning = stat['meaning'].replace("a threshold", f"{spi_thresh}")
                # Replace the parenthetical severity description based on threshold
                if spi_thresh in SPI_THRESHOLD_LABELS:
                    base_meaning = re.sub(
                        r'\(.*?or worse\)',
                        f"({SPI_THRESHOLD_LABELS[spi_thresh]})",
                        base_meaning
                    )
            else:
                base_meaning = stat['meaning']

            # Enhanced caption with bold highlights for key facts
            text = (
                f"<strong>{stat['label'].upper()}</strong> of meteorological drought "
                f"({decade_year}–{decade_year + 9}).<br><br>"
                f"<strong>Statistic:</strong> {stat['label']}<br>"
                f"<strong>Threshold:</strong> SPI ≤ {spi_thresh:.1f}<br>"
                f"<strong>Reference period:</strong> 1960–1999<br><br>"
                f"{base_meaning}."
            )

        return ui.HTML(
            f"<div style='text-align: left; color: #bbb; font-size: 14px; line-height: 1.6; padding: 5px 10px 10px 10px; background-color: rgba(255,255,255,0.05); border-radius: 5px;'>{text}</div>"
        )

    @render.ui
    def smi_caption():
        """Dynamic caption for SMI (Agricultural) tab with threshold descriptions."""
        stat_key = input.statistic()
        stat = SMI_STATISTICS.get(stat_key, SMI_STATISTICS["mean"])
        decade_year = input.dec().year

        # Get the SMI threshold - handle case where slider doesn't exist (for 'mean' and 'min' stats)
        selected_thresh = None
        try:
            smi_thresh_val = input.smi_thresh()
            if smi_thresh_val is not None:
                selected_thresh = float(smi_thresh_val)
        except (RuntimeError, TypeError, AttributeError):
            pass

        # Fallback to first available threshold
        if selected_thresh is None or SMI_THRESHOLDS is None or len(SMI_THRESHOLDS) == 0:
            selected_thresh = SMI_THRESHOLDS[0] if SMI_THRESHOLDS else 0.2
        else:
            selected_thresh = min(SMI_THRESHOLDS, key=lambda t: abs(t - selected_thresh))

        # Build the meaning text with the actual threshold value for dfreq and maxspell
        if stat_key in ["dfreq", "maxspell"]:
            base_meaning = stat['meaning'].replace("a threshold", f"{selected_thresh}")
            # Replace the parenthetical severity description based on threshold
            if selected_thresh in SMI_THRESHOLD_LABELS:
                base_meaning = re.sub(
                    r'\(.*?or worse\)',
                    f"({SMI_THRESHOLD_LABELS[selected_thresh]})",
                    base_meaning
                )
        else:
            base_meaning = stat['meaning']

        # Check if data is available for this threshold and statistic
        clm5_stat = SMI_STAT_DATA_BY_THRESH["CLM5"].get(selected_thresh, {}).get(stat_key)
        if not clm5_stat:
            text = (
                f'The "{stat["label"]}" statistic is not available for the "{selected_thresh}" '
                "SMI threshold."
            )
        else:
            # Find shown year
            if decade_year in clm5_stat:
                shown_year = decade_year
            elif clm5_stat:
                shown_year = min(clm5_stat.keys())
            else:
                shown_year = decade_year

            # Enhanced caption with bold highlights for key facts
            text = (
                f"<strong>{stat['label'].upper()}</strong> of agricultural drought "
                f"({decade_year}–{decade_year + 9}).<br><br>"
                f"<strong>Statistic:</strong> {stat['label']}<br>"
                f"<strong>Threshold:</strong> SMI ≤ {selected_thresh:.1f}<br>"
                f"<strong>Reference period:</strong> 1960–1999<br><br>"
                f"{base_meaning}."
            )

        return ui.HTML(
            f"<div style='text-align: left; color: #bbb; font-size: 14px; line-height: 1.6; padding: 5px 10px 10px 10px; background-color: rgba(255,255,255,0.05); border-radius: 5px;'>{text}</div>"
        )

    @render.plot
    def render_eu3_map():
        from plots import EU3_map

        # Check if we're on the Agricultural tab first
        active_tab = input.drought_tab()
        if active_tab != "Agricultural":
            # Don't render if not on the correct tab
            return _message_fig("Select the Agricultural tab to view SMI data.")

        stat_key = input.statistic()
        stat = SMI_STATISTICS.get(stat_key, SMI_STATISTICS["mean"])
        decade_year = input.dec().year

        # Get the SMI threshold - handle case where slider doesn't exist (for 'mean' and 'min' stats)
        # Use the first available threshold as fallback
        selected_thresh = None

        # Try to get the input value
        try:
            smi_thresh_val = input.smi_thresh()
            if smi_thresh_val is not None:
                selected_thresh = float(smi_thresh_val)
        except (RuntimeError, TypeError, AttributeError):
            # input.smi_thresh() doesn't exist yet
            pass

        # Fallback to first available threshold if we don't have a valid value
        if selected_thresh is None or SMI_THRESHOLDS is None or len(SMI_THRESHOLDS) == 0:
            selected_thresh = SMI_THRESHOLDS[0] if SMI_THRESHOLDS else 0.2
        else:
            # Find the nearest available threshold
            selected_thresh = min(SMI_THRESHOLDS, key=lambda t: abs(t - selected_thresh))

        smi_thresh = selected_thresh
        clm5_stat = SMI_STAT_DATA_BY_THRESH["CLM5"].get(smi_thresh, {}).get(stat_key)
        mhm_stat = SMI_STAT_DATA_BY_THRESH["mHM"].get(smi_thresh, {}).get(stat_key)
        if not clm5_stat or not mhm_stat:
            return _message_fig(
                f'The “{stat["label"]}” statistic is not available for soil '
                "moisture (SMI)."
            )

        # Fall back to the earliest available decade if this one is missing.
        if decade_year not in clm5_stat:
            decade_year = min(clm5_stat.keys())

        clm5_smi_data = clm5_stat[decade_year] * stat["scale"]
        mhm_smi_data = mhm_stat[decade_year] * stat["scale"]
        clm5_smi_data = _blank_ocean(
            clm5_smi_data, SMI_STAT_DATA_BY_THRESH["CLM5"].get(smi_thresh, {}).get("mean"), decade_year
        )
        mhm_smi_data = _blank_ocean(
            mhm_smi_data, SMI_STAT_DATA_BY_THRESH["mHM"].get(smi_thresh, {}).get("mean"), decade_year
        )

        # For drought frequency, calculate dynamic vmin/vmax based on actual data range
        # This makes the colormap more informative when actual values vary significantly
        if stat_key == "dfreq":
            # Calculate min/max from both models (excluding NaN values)
            all_valid = np.concatenate([
                clm5_smi_data[~np.isnan(clm5_smi_data)],
                mhm_smi_data[~np.isnan(mhm_smi_data)]
            ])
            if len(all_valid) > 0:
                data_min = float(np.nanmin(all_valid))
                data_max = float(np.nanmax(all_valid))
                # Add small padding (5% of range) to avoid edge clipping
                data_range = data_max - data_min
                padding = data_range * 0.05 if data_range > 0 else 1.0
                dynamic_vmin = max(0, data_min - padding)  # Don't go below 0 for percentage
                dynamic_vmax = min(100, data_max + padding)  # Cap at 100 for percentage (not 40!)
                print(f"DEBUG SMI dfreq: data_min={data_min:.2f}, data_max={data_max:.2f}, dynamic_vmin={dynamic_vmin:.2f}, dynamic_vmax={dynamic_vmax:.2f}")
            else:
                dynamic_vmin, dynamic_vmax = 0, 100
                print(f"DEBUG SMI dfreq: No valid data, using defaults 0, 100")
        else:
            dynamic_vmin, dynamic_vmax = stat["vmin"], stat["vmax"]
            print(f"DEBUG SMI {stat_key}: using static vmin={dynamic_vmin}, vmax={dynamic_vmax}")

        # Create fresh map instance (required by Shiny's matplotlib backend)
        # Always use horizontal colorbar for all Agricultural statistics (uniform layout)
        use_horizontal_cbar = True  # All SMI statistics now use horizontal colorbar at bottom
        eu_map_instance = EU3_map(
            suptitle=(
                f"Soil moisture (SMI) — {stat['label'].lower()}, "
                f"{decade_year}–{decade_year + 9}"
            ),
            title=["CLM5", "mHM"],
            description="",
            color_mode="dark",
            theme_config=theme_config,
            horizontal_cbar=use_horizontal_cbar,
        )
        fig, gs, _ = eu_map_instance.create()

        # Add data to both plots with the same scale
        if SMI_lon is not None and SMI_lat is not None:
            # Prepare pcolormesh arguments
            pcolormesh_kwargs = {
                "cmap": stat["cmap"],
                "alpha": 0.8,
            }
            # Add norm if available (for custom color boundaries)
            if "norm" in stat:
                pcolormesh_kwargs["norm"] = stat["norm"]
            else:
                pcolormesh_kwargs["vmin"] = dynamic_vmin
                pcolormesh_kwargs["vmax"] = dynamic_vmax

            eu_map_instance.pcolormesh(
                SMI_lon,
                SMI_lat,
                clm5_smi_data,
                ax_num=0,
                **pcolormesh_kwargs
            )
            eu_map_instance.pcolormesh(
                SMI_lon,
                SMI_lat,
                mhm_smi_data,
                ax_num=1,
                **pcolormesh_kwargs
            )

            # Add colorbar using EU3_map.colorbar() method
            # For SMI mean and min statistics with custom norm, use special colorbar
            if stat_key in ["mean", "min"] and "norm" in stat:
                midpoints = [(SMI_BREAKS[i] + SMI_BREAKS[i+1]) / 2 for i in range(len(SMI_BREAKS)-1)]
                labels = [
                    "Exceptional\ndrought",
                    "Extreme\ndrought",
                    "Severe\ndrought",
                    "Moderate\ndrought",
                    "Abnormally\ndry",
                    "Normal",
                    "Abnormally\nwet",
                    "Moderate\nwetness",
                    "Severe\nwetness",
                    "Extreme\nwetness",
                    "Exceptional\nwetness"
                ]

                eu_map_instance.colorbar(
                    eu_map_instance.pcolormesh_obj,
                    cbar_label="",  # Remove colorbar label
                    extend=stat["extend"],
                    horizontal=True,
                )

                # Update colorbar ticks and labels after creation
                cbar = eu_map_instance.cbar
                if cbar is not None:
                    cbar.set_ticks(midpoints)
                    cbar.set_ticklabels(labels)

                    # Set tick label color to white and increase font size
                    for tick in cbar.ax.get_xticklabels():
                        tick.set_color("white")
                        tick.set_fontsize(8)

                    # Show tick labels explicitly and adjust positioning
                    cbar.ax.tick_params(axis='x', which='both',
                                       labelbottom=True, bottom=False, top=False,
                                       labelsize=8, colors='white')

                    # Ensure labels are visible above the colorbar
                    cbar.ax.tick_params(axis='x', pad=15)
            else:
                # All other statistics (dfreq, maxspell) use horizontal colorbar with standard label
                eu_map_instance.colorbar(
                    eu_map_instance.pcolormesh_obj,
                    cbar_label=stat["cbar_label"],
                    extend=stat["extend"],
                    horizontal=True,  # Always horizontal for Agricultural section
                )

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
                label=f"Observed ({gauge_id})",
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
        return fig

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

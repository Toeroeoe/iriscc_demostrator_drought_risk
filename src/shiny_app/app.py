"""_summary_

Returns:
    _type_: _description_
"""

from datetime import date, timedelta

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.font_manager import FontProperties
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
    eval_station_meta,
    eval_map_html,
    EVAL_VARIABLES,
    get_eval_series,
)
from shiny import App, render, ui
from shiny.types import ImgData
from shinyswatch import theme
from theme_config import GOOGLE_FONTS_URL, get_theme_config

# Try to import R integration for drought hydrograph
try:
    from drought_hydrograph_r import drought_hydrograph_r_available
    R_AVAILABLE = drought_hydrograph_r_available()
except ImportError:
    R_AVAILABLE = False
    # Provide a dummy function for fallback
    def create_drought_hydrograph_image(*args, **kwargs):
        return None

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
            "The percentage of time during which the 92-day SPI stayed at or below the threshold "
            "(moderate drought or worse). Higher values indicate that drought conditions occurred "
            "more frequently over the decade"
        ),
    },
    "min": {
        "label": "Peak severity",
        "cmap": "YlOrRd_r",
        "vmin": -4.0,
        "vmax": -1.0,
        "extend": "both",
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
            "The percentage of time during which soil moisture stayed at or below the threshold "
            "(moderate drought or worse). Higher values indicate that drought conditions occurred "
            "more frequently over the decade"
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
# Intro card first (full width), then sidebar + content
page_droughts = ui.div(
    # Intro card (full width at top)
    ui.card(
        ui.markdown(
            """

            Droughts are among the most far-reaching climate-related hazards.
            They develop slowly, but their effects can be severe and widespread. A drought is defined as precipitation persistently below normal levels (a *meteorological drought*, <a href="#mckee1993" class="citation-link">McKee et al., 1993</a>). If the deficit continues and is potentially accompanied by an increased water demand from a dry atmosphere, it depletes soil moisture and reduces water available to plants (an *agricultural drought*, <a href="#samaniego2018" class="citation-link">Samaniego et al., 2018</a>). Eventually, it can lower river discharge (a *hydrological drought*,
            <a href="#thober2019" class="citation-link">Thober et al., 2019</a>).

            These interlinked forms of drought place terrestrial ecosystems and
            the services they provide under considerable stress. They reduce
            crop yields and forest carbon uptake, threaten drinking-water and
            energy supplies, and can amplify heatwaves and the risk of
            wildfires. Under a warming climate, droughts are expected to become
            more frequent and more severe across many regions of Europe (<a href="#samaniego2018" class="citation-link">Samaniego et al., 2018</a>).

            This demonstrator lets you explore how meteorological,
            hydrological, and agricultural droughts have evolved over recent
            decades and what they mean for ecosystem functioning (<a href="#shrestha2026" class="citation-link">Shrestha et al., 2026</a>; <a href="#poppe2023" class="citation-link">Poppe Terán et al., 2023</a>). Use the
            **view settings** below to select a decade, atmospheric
            forcing, and emission scenario, and switch between the tabs to
            examine drought occurrence and its impacts.

            <style>
            .citation-link {
                color: var(--bs-success);
                text-decoration: none;
            }
            .citation-link:hover {
                text-decoration: underline;
            }
            html {
                scroll-behavior: smooth;
            }
            </style>
            """
        ),
        style="text-align: left;",
    ),
    # Sidebar and navsets below intro
    ui.page_sidebar(
        ui.sidebar(
            "View settings",
            ui.output_ui("reference_period_display"),
            ui.output_ui("conditional_sidebar_controls"),
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
                ui.output_plot("render_spi_map", height="600px"),
                ui.output_ui("spi_caption"),
            ),
            ui.nav_panel(
                "Agricultural",
                ui.output_plot("render_eu3_map", height="650px"),
                ui.output_ui("smi_caption"),
            ),
            ui.nav_panel(
                "Hydrological",
                ui.p(
                    "Select a station using the dropdown in the sidebar or click on a gauge marker in the map to view its drought hydrograph.",
                    style="text-align:left; color:#888; margin-bottom:6px;",
                ),
                ui.HTML(gauge_map_html),
                ui.output_ui("drought_hydrograph_container"),
                ui.output_ui("drought_hydrograph_caption"),
            ),
            id="main_tab",  # Track active tab for conditional sidebar controls
            title="Drought occurence",
        ),
        ui.navset_card_pill(
            ui.nav_panel("Crop yield", ""),
            ui.nav_panel("Forest carbon uptake"),
            title="Impacts",
        )
    ),  # Close page_sidebar
)  # Close outer div

# ── Static informational pages ──────────────────────────────────────────────

page_authors = ui.page_fluid(
    ui.h2("Authors & Acknowledgements"),
    ui.hr(),
    ui.h3("Authors"),
    ui.p(
        ui.strong("Christian Poppe Terán"), " Institute of Bio- and Geosciences: Agrosphere (IBG-3), Research Centre Jülich (FZJ), Jülich, Germany",
        style="margin-bottom: 1em; display: block; text-align: left;"
    ),
    ui.p(
        ui.strong("Pallav Kumar Shrestha"), " Helmholtz Centre for Environmental Research (UFZ), Leipzig, Germany",
        style="margin-bottom: 1em; display: block; text-align: left;"
    ),
    ui.p(
        ui.strong("Alexandre Belleflamme"), " Institute of Bio- and Geosciences: Agrosphere (IBG-3), Research Centre Jülich (FZJ), Jülich, Germany",
        style="margin-bottom: 1em; display: block; text-align: left;"
    ),
    ui.p(
        ui.strong("Luis Samaniego"), " Helmholtz Centre for Environmental Research (UFZ), Leipzig, Germany",
        style="margin-bottom: 1em; display: block; text-align: left;"
    ),
    ui.p(
        ui.strong("Harry Vereecken"), " Institute of Bio- and Geosciences: Agrosphere (IBG-3), Research Centre Jülich (FZJ), Jülich, Germany",
        style="margin-bottom: 2em; display: block; text-align: left;"
    ),
    ui.h3("Acknowledgements"),
    ui.p(
        "This demonstrator is part of the IRISCC project. IRISCC is funded by the European Union Grant Agreement Number 101131261.",
        style="margin-bottom: 1em; display: block; text-align: left;"
    ),
    ui.p(
        "The authors gratefully acknowledge the contribution of observational data provided by the eLTER, ICOS, and GRDC research infrastructures.",
        style="margin-bottom: 1em; display: block; text-align: left;"
    ),
    ui.HTML(
        "<p style='margin-bottom: 2em; display: block; text-align: left;'>"
        "We also gratefully acknowledge the allocation of compute time under the project cibg31 "
        "on JURECA-DC at the Jülich Supercomputing Centre. "
        "<a href='#jureca2018' style='color: #5cb85c; text-decoration: none;'>Jülich Supercomputing Centre, 2018</a>"
        "</p>"
    )
)

page_license = ui.page_fluid(
    ui.h2("License"),
    ui.hr(),
    ui.p(
        'This software is released under the CC BY 4.0 International license.'
    ),
    ui.tags.pre(
        """Attribution 4.0 International

        =======================================================================

        Creative Commons Corporation ("Creative Commons") is not a law firm and
        does not provide legal services or legal advice. Distribution of
        Creative Commons public licenses does not create a lawyer-client or
        other relationship. Creative Commons makes its licenses and related
        information available on an "as-is" basis. Creative Commons gives no
        warranties regarding its licenses, any material licensed under their
        terms and conditions, or any related information. Creative Commons
        disclaims all liability for damages resulting from their use to the
        fullest extent possible.

        Using Creative Commons Public Licenses

        Creative Commons public licenses provide a standard set of terms and
        conditions that creators and other rights holders may use to share
        original works of authorship and other material subject to copyright
        and certain other rights specified in the public license below. The
        following considerations are for informational purposes only, are not
        exhaustive, and do not form part of our licenses.

             Considerations for licensors: Our public licenses are
             intended for use by those authorized to give the public
             permission to use material in ways otherwise restricted by
             copyright and certain other rights. Our licenses are
             irrevocable. Licensors should read and understand the terms
             and conditions of the license they choose before applying it.
             Licensors should also secure all rights necessary before
             applying our licenses so that the public can reuse the
             material as expected. Licensors should clearly mark any
             material not subject to the license. This includes other CC-
             licensed material, or material used under an exception or
             limitation to copyright. More considerations for licensors:
            wiki.creativecommons.org/Considerations_for_licensors

             Considerations for the public: By using one of our public
             licenses, a licensor grants the public permission to use the
             licensed material under specified terms and conditions. If
             the licensor's permission is not necessary for any reason--for
             example, because of any applicable exception or limitation to
             copyright--then that use is not regulated by the license. Our
             licenses grant only permissions under copyright and certain
             other rights that a licensor has authority to grant. Use of
             the licensed material may still be restricted for other
             reasons, including because others have copyright or other
             rights in the material. A licensor may make special requests,
             such as asking that all changes be marked or described.
             Although not required by our licenses, you are encouraged to
             respect those requests where reasonable. More considerations
             for the public:
            wiki.creativecommons.org/Considerations_for_licensees

        =======================================================================

        Creative Commons Attribution 4.0 International Public License

        By exercising the Licensed Rights (defined below), You accept and agree
        to be bound by the terms and conditions of this Creative Commons
        Attribution 4.0 International Public License ("Public License"). To the
        extent this Public License may be interpreted as a contract, You are
        granted the Licensed Rights in consideration of Your acceptance of
        these terms and conditions, and the Licensor grants You such rights in
        consideration of benefits the Licensor receives from making the
        Licensed Material available under these terms and conditions.


        Section 1 -- Definitions.

          a. Adapted Material means material subject to Copyright and Similar
             Rights that is derived from or based upon the Licensed Material
             and in which the Licensed Material is translated, altered,
             arranged, transformed, or otherwise modified in a manner requiring
             permission under the Copyright and Similar Rights held by the
             Licensor. For purposes of this Public License, where the Licensed
             Material is a musical work, performance, or sound recording,
             Adapted Material is always produced where the Licensed Material is
             synched in timed relation with a moving image.

          b. Adapter's License means the license You apply to Your Copyright
             and Similar Rights in Your contributions to Adapted Material in
             accordance with the terms and conditions of this Public License.

          c. Copyright and Similar Rights means copyright and/or similar rights
             closely related to copyright including, without limitation,
             performance, broadcast, sound recording, and Sui Generis Database
             Rights, without regard to how the rights are labeled or
             categorized. For purposes of this Public License, the rights
             specified in Section 2(b)(1)-(2) are not Copyright and Similar
             Rights.

          d. Effective Technological Measures means those measures that, in the
             absence of proper authority, may not be circumvented under laws
             fulfilling obligations under Article 11 of the WIPO Copyright
             Treaty adopted on December 20, 1996, and/or similar international
             agreements.

          e. Exceptions and Limitations means fair use, fair dealing, and/or
             any other exception or limitation to Copyright and Similar Rights
             that applies to Your use of the Licensed Material.

          f. Licensed Material means the artistic or literary work, database,
             or other material to which the Licensor applied this Public
             License.

          g. Licensed Rights means the rights granted to You subject to the
             terms and conditions of this Public License, which are limited to
             all Copyright and Similar Rights that apply to Your use of the
             Licensed Material and that the Licensor has authority to license.

          h. Licensor means the individual(s) or entity(ies) granting rights
             under this Public License.

          i. Share means to provide material to the public by any means or
             process that requires permission under the Licensed Rights, such
             as reproduction, public display, public performance, distribution,
             dissemination, communication, or importation, and to make material
             available to the public including in ways that members of the
             public may access the material from a place and at a time
             individually chosen by them.

          j. Sui Generis Database Rights means rights other than copyright
             resulting from Directive 96/9/EC of the European Parliament and of
             the Council of 11 March 1996 on the legal protection of databases,
             as amended and/or succeeded, as well as other essentially
             equivalent rights anywhere in the world.

          k. You means the individual or entity exercising the Licensed Rights
             under this Public License. Your has a corresponding meaning.


        Section 2 -- Scope.

          a. License grant.

               1. Subject to the terms and conditions of this Public License,
                  the Licensor hereby grants You a worldwide, royalty-free,
                  non-sublicensable, non-exclusive, irrevocable license to
                  exercise the Licensed Rights in the Licensed Material to:

                    a. reproduce and Share the Licensed Material, in whole or
                       in part; and

                    b. produce, reproduce, and Share Adapted Material.

               2. Exceptions and Limitations. For the avoidance of doubt, where
                  Exceptions and Limitations apply to Your use, this Public
                  License does not apply, and You do not need to comply with
                  its terms and conditions.

               3. Term. The term of this Public License is specified in Section
                  6(a).

               4. Media and formats; technical modifications allowed. The
                  Licensor authorizes You to exercise the Licensed Rights in
                  all media and formats whether now known or hereafter created,
                  and to make technical modifications necessary to do so. The
                  Licensor waives and/or agrees not to assert any right or
                  authority to forbid You from making technical modifications
                  necessary to exercise the Licensed Rights, including
                  technical modifications necessary to circumvent Effective
                  Technological Measures. For purposes of this Public License,
                  simply making modifications authorized by this Section 2(a)
                  (4) never produces Adapted Material.

               5. Downstream recipients.

                    a. Offer from the Licensor -- Licensed Material. Every
                       recipient of the Licensed Material automatically
                       receives an offer from the Licensor to exercise the
                       Licensed Rights under the terms and conditions of this
                       Public License.

                    b. No downstream restrictions. You may not offer or impose
                       any additional or different terms or conditions on, or
                       apply any Effective Technological Measures to, the
                       Licensed Material if doing so restricts exercise of the
                       Licensed Rights by any recipient of the Licensed
                       Material.

               6. No endorsement. Nothing in this Public License constitutes or
                  may be construed as permission to assert or imply that You
                  are, or that Your use of the Licensed Material is, connected
                  with, or sponsored, endorsed, or granted official status by,
                  the Licensor or others designated to receive attribution as
                  provided in Section 3(a)(1)(A)(i).

          b. Other rights.

               1. Moral rights, such as the right of integrity, are not
                  licensed under this Public License, nor are publicity,
                  privacy, and/or other similar personality rights; however, to
                  the extent possible, the Licensor waives and/or agrees not to
                  assert any such rights held by the Licensor to the limited
                  extent necessary to allow You to exercise the Licensed
                  Rights, but not otherwise.

               2. Patent and trademark rights are not licensed under this
                  Public License.

               3. To the extent possible, the Licensor waives any right to
                  collect royalties from You for the exercise of the Licensed
                  Rights, whether directly or through a collecting society
                  under any voluntary or waivable statutory or compulsory
                  licensing scheme. In all other cases the Licensor expressly
                  reserves any right to collect such royalties.


        Section 3 -- License Conditions.

        Your exercise of the Licensed Rights is expressly made subject to the
        following conditions.

          a. Attribution.

               1. If You Share the Licensed Material (including in modified
                  form), You must:

                    a. retain the following if it is supplied by the Licensor
                       with the Licensed Material:

                         i. identification of the creator(s) of the Licensed
                            Material and any others designated to receive
                            attribution, in any reasonable manner requested by
                            the Licensor (including by pseudonym if
                            designated);

                        ii. a copyright notice;

                       iii. a notice that refers to this Public License;

                        iv. a notice that refers to the disclaimer of
                            warranties;

                         v. a URI or hyperlink to the Licensed Material to the
                            extent reasonably practicable;

                    b. indicate if You modified the Licensed Material and
                       retain an indication of any previous modifications; and

                    c. indicate the Licensed Material is licensed under this
                       Public License, and include the text of, or the URI or
                       hyperlink to, this Public License.

               2. You may satisfy the conditions in Section 3(a)(1) in any
                  reasonable manner based on the medium, means, and context in
                  which You Share the Licensed Material. For example, it may be
                  reasonable to satisfy the conditions by providing a URI or
                  hyperlink to a resource that includes the required
                  information.

               3. If requested by the Licensor, You must remove any of the
                  information required by Section 3(a)(1)(A) to the extent
                  reasonably practicable.

               4. If You Share Adapted Material You produce, the Adapter's
                  License You apply must not prevent recipients of the Adapted
                  Material from complying with this Public License.


        Section 4 -- Sui Generis Database Rights.

        Where the Licensed Rights include Sui Generis Database Rights that
        apply to Your use of the Licensed Material:

          a. for the avoidance of doubt, Section 2(a)(1) grants You the right
             to extract, reuse, reproduce, and Share all or a substantial
             portion of the contents of the database;

          b. if You include all or a substantial portion of the database
             contents in a database in which You have Sui Generis Database
             Rights, then the database in which You have Sui Generis Database
             Rights (but not its individual contents) is Adapted Material; and

          c. You must comply with the conditions in Section 3(a) if You Share
             all or a substantial portion of the contents of the database.

        For the avoidance of doubt, this Section 4 supplements and does not
        replace Your obligations under this Public License where the Licensed
        Rights include other Copyright and Similar Rights.


        Section 5 -- Disclaimer of Warranties and Limitation of Liability.

          a. UNLESS OTHERWISE SEPARATELY UNDERTAKEN BY THE LICENSOR, TO THE
             EXTENT POSSIBLE, THE LICENSOR OFFERS THE LICENSED MATERIAL AS-IS
             AND AS-AVAILABLE, AND MAKES NO REPRESENTATIONS OR WARRANTIES OF
             ANY KIND CONCERNING THE LICENSED MATERIAL, WHETHER EXPRESS,
             IMPLIED, STATUTORY, OR OTHER. THIS INCLUDES, WITHOUT LIMITATION,
             WARRANTIES OF TITLE, MERCHANTABILITY, FITNESS FOR A PARTICULAR
             PURPOSE, NON-INFRINGEMENT, ABSENCE OF LATENT OR OTHER DEFECTS,
             ACCURACY, OR THE PRESENCE OR ABSENCE OF ERRORS, WHETHER OR NOT
             KNOWN OR DISCOVERABLE. WHERE DISCLAIMERS OF WARRANTIES ARE NOT
             ALLOWED IN FULL OR IN PART, THIS DISCLAIMER MAY NOT APPLY TO YOU.

          b. TO THE EXTENT POSSIBLE, IN NO EVENT WILL THE LICENSOR BE LIABLE
             TO YOU ON ANY LEGAL THEORY (INCLUDING, WITHOUT LIMITATION,
             NEGLIGENCE) OR OTHERWISE FOR ANY DIRECT, SPECIAL, INDIRECT,
             INCIDENTAL, CONSEQUENTIAL, PUNITIVE, EXEMPLARY, OR OTHER LOSSES,
             COSTS, EXPENSES, OR DAMAGES ARISING OUT OF THIS PUBLIC LICENSE OR
             USE OF THE LICENSED MATERIAL, EVEN IF THE LICENSOR HAS BEEN
             ADVISED OF THE POSSIBILITY OF SUCH LOSSES, COSTS, EXPENSES, OR
             DAMAGES. WHERE A LIMITATION OF LIABILITY IS NOT ALLOWED IN FULL OR
             IN PART, THIS LIMITATION MAY NOT APPLY TO YOU.

          c. The disclaimer of warranties and limitation of liability provided
             above shall be interpreted in a manner that, to the extent
             possible, most closely approximates an absolute disclaimer and
             waiver of all liability.


        Section 6 -- Term and Termination.

          a. This Public License applies for the term of the Copyright and
             Similar Rights licensed here. However, if You fail to comply with
             this Public License, then Your rights under this Public License
             terminate automatically.

          b. Where Your right to use the Licensed Material has terminated under
             Section 6(a), it reinstates:

               1. automatically as of the date the violation is cured, provided
                  it is cured within 30 days of Your discovery of the
                  violation; or

               2. upon express reinstatement by the Licensor.

             For the avoidance of doubt, this Section 6(b) does not affect any
             right the Licensor may have to seek remedies for Your violations
             of this Public License.

          c. For the avoidance of doubt, the Licensor may also offer the
             Licensed Material under separate terms or conditions or stop
             distributing the Licensed Material at any time; however, doing so
             will not terminate this Public License.

          d. Sections 1, 5, 6, 7, and 8 survive termination of this Public
             License.


        Section 7 -- Other Terms and Conditions.

          a. The Licensor shall not be bound by any additional or different
             terms or conditions communicated by You unless expressly agreed.

          b. Any arrangements, understandings, or agreements regarding the
             Licensed Material not stated herein are separate from and
             independent of the terms and conditions of this Public License.


        Section 8 -- Interpretation.

          a. For the avoidance of doubt, this Public License does not, and
             shall not be interpreted to, reduce, limit, restrict, or impose
             conditions on any use of the Licensed Material that could lawfully
             be made without permission under this Public License.

          b. To the extent possible, if any provision of this Public License is
             deemed unenforceable, it shall be automatically reformed to the
             minimum extent necessary to make it enforceable. If the provision
             cannot be reformed, it shall be severed from this Public License
             without affecting the enforceability of the remaining terms and
             conditions.

          c. No term or condition of this Public License will be waived and no
             failure to comply consented to unless expressly agreed to by the
             Licensor.

          d. Nothing in this Public License constitutes or may be interpreted
             as a limitation upon, or waiver of, any privileges and immunities
             that apply to the Licensor or You, including from the legal
             processes of any jurisdiction or authority.


        =======================================================================

        Creative Commons is not a party to its public
        licenses. Notwithstanding, Creative Commons may elect to apply one of
        its public licenses to material it publishes and in those instances
        will be considered the “Licensor.” The text of the Creative Commons
        public licenses is dedicated to the public domain under the CC0 Public
        Domain Dedication. Except for the limited purpose of indicating that
        material is shared under a Creative Commons public license or as
        otherwise permitted by the Creative Commons policies published at
        creativecommons.org/policies, Creative Commons does not authorize the
        use of the trademark "Creative Commons" or any other trademark or logo
        of Creative Commons without its prior written consent including,
        without limitation, in connection with any unauthorized modifications
        to any of its public licenses or any other arrangements,
        understandings, or agreements concerning use of licensed material. For
        the avoidance of doubt, this paragraph does not form part of the
        public licenses.

        Creative Commons may be contacted at creativecommons.org.""",
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
    ui.p("Research Centre Jülich (FZJ), Jülich, Germany"),
    ui.p("Wilhelm-Johnen-Str., 52428 Jülich, Germany"),
    ui.p("Entered in the Commercial Register of the District Court of Düren, Germany: No. HR B 3498"),
    ui.p("Value Added Tax ID No. in accordance with § 27 a of the German VAT Law (Umsatzsteuergesetz): DE 122624631"),
    ui.p("Tax No.: 213/5700/0033"),
    ui.hr(),
    ui.h4("Board of Directors"),
    ui.p("Prof. Dr. Astrid Lambrecht (Chair of the Board of Directors)"),
    ui.p("Dr. Stephanie Bauer (Vice-Chair)"),
    ui.p("Prof. Dr. Ir. Pieter Jansens"),
    ui.p("Prof. Dr. Laurens Kuipers"),
    ui.hr(),
    ui.h4("Supervisory Board"),
    ui.p("Ministerialdirektor Stefan Müller"),
    ui.hr(),
    ui.h4("Responsible in the sense of § 18, Abs. 2, Medienstaatsvertrag (MStV)"),
    ui.p("Petra Schäfer"),
    ui.p("Forschungszentrum Jülich"),
    ui.p("Leiterin Unternehmenskommunikation"),
    ui.p("Wilhelm-Johnen-Straße, 52428 Jülich"),
    ui.hr(),
    ui.h4("Contact"),
    ui.p(
        "General inquiries: +49 2461 61-0",
        ui.br(),
        "General fax no.: +49 2461 61-8100"
    ),
    ui.p(
        "Internet: http://www.fz-juelich.de",
        ui.br(),
        "e-mail: info@fz-juelich.de"
    ),
    ui.hr(),
    ui.h4("Copyright"),
    ui.p(
        "Copyright and all other rights concerning this website are held by Forschungszentrum Jülich GmbH. "
        "Use of the information contained on the website, including excerpts, is permitted for educational, "
        "scientific or private purposes, provided the source is quoted (unless otherwise expressly stated on the "
        "respective website). Use for commercial purposes is not permitted unless explicit permission has been "
        "granted by Forschungszentrum Jülich."
    ),
    ui.p(
        "For further information, contact: ",
        ui.a("Corporate Communications", href="http://www.fz-juelich.de/portal/EN/Press/CorporateCommunications/_node.html", target="_blank")
    ),
    ui.hr(),
    ui.h3("Disclaimer"),
    ui.p("Contents of the Website of Forschungszentrum Jülich:"),
    ui.p(
        "The website of Forschungszentrum Jülich has been compiled with due diligence. However, "
        "Forschungszentrum Jülich neither guarantees nor accepts liability for the information being "
        "up-to-date, complete or accurate."
    ),
    ui.p("Links to External Websites:"),
    ui.p(
        "This website may contain links to external third-party websites. These links to third party sites "
        "do not imply approval of their contents. Responsibility for the content of these websites lies "
        "solely with the respective provider or operator of the site. Illegal contents were not recognizable "
        "at the time of setting the link. We do not accept any liability for the continual accessibility or "
        "up-to-dateness, completeness or correctness of the contents of such websites. If we become aware of "
        "any infringements of the law, we will remove such links immediately."
    ),
    ui.hr(),
    ui.h3("Data Protection"),
    ui.h4("Data protection declaration"),
    ui.p(
        "We take the protection of your personal data very seriously and process the data collected when you "
        "visit this website in accordance with the latest provisions of data protection law. We neither "
        "publish your data nor pass it on to unentitled third parties. In the following declaration we set out "
        "what data we collect during your visit to our websites, exactly how it is used and whom you can "
        "contact if you have any further questions."
    ),
    ui.h4("Contact details of the person responsible for processing your data"),
    ui.p(
        "Dr. Christian Poppe Terán; Institute of Bio- and Geosciences, Agrosphere (IBG-3); Forschungszentrum "
        "Jülich GmbH; 52425 Jülich; Germany; e-mail: ",
        ui.a("c.poppe@fz-juelich.de", href="mailto:c.poppe@fz-juelich.de")
    ),
    ui.h4("Contact details of FZJ's data protection officer"),
    ui.p(
        "Mr. Frank Rinkens; Forschungszentrum Jülich GmbH; 52425 Jülich; Germany; phone: +49 2461 61-9005; "
        "e-mail: ",
        ui.a("DSB@fz-juelich.de", href="mailto:DSB@fz-juelich.de")
    ),
    ui.hr(),
    ui.h3("Accessibility"),
    ui.p(
        "We aim to make this application accessible in accordance with the "
        "Web Content Accessibility Guidelines (WCAG) 2.1, Level AA, and "
        "Directive (EU) 2016/2102 on the accessibility of public-sector websites."
    ),
    style="text-align: left; padding: 20px;",
)

# ── Model-evaluation page ────────────────────────────────────────────────────

# Station dropdown choices for the evaluation page (graceful when the data
# files have not been downloaded yet).
if eval_station_meta is not None and len(eval_station_meta) > 0:
    _eval_station_choices = dict(
        zip(eval_station_meta["station_id"], eval_station_meta["station_name"])
    )
    _eval_default_station = None  # No default station selected
else:
    _eval_station_choices = {}
    _eval_default_station = None

page_model_evaluation = ui.div(
    # Intro card (full width at top)
    ui.card(
        ui.markdown(
            """
            Model evaluation with ICOS Reference Infrastructure data. The land surface model CLM5 (<a href="#lawrence2019" class="citation-link">Lawrence et al., 2019</a>) is compared here with observations from the ICOS (Integrated Carbon Observation System) reference, a pan-European research network dedicated to long-term greenhouse gas flux measurements. This comparison allows users to assess how well the model reproduces observed soil moisture and vegetation carbon uptake across different climates and ecosystems in Europe.

            Two key variables are available for evaluation. Soil moisture (SWC) represents topsoil volumetric water content measured by ICOS soil chambers, which is compared against CLM5 surface soil moisture simulations. Gross Primary Production (GPP) quantifies carbon uptake by vegetation through eddy-covariance tower measurements, providing a benchmark for CLM5 photosynthesis estimates. Both variables are critical for understanding ecosystem responses to drought conditions.

            The Community Land Model version 5 (CLM5, <a href="#lawrence2019" class="citation-link">Lawrence et al., 2019</a>) includes state-of-the-art representations of land surface processes, vegetation dynamics, and hydrology. For European applications, while studies have identified systematic biases in simulated ecosystem process variability, the overall representation of ecosystem processes variability is  (<a href="#poppe2025" class="citation-link">Poppe Terán et al., 2025</a>).

            To explore the model performance, select a station using the dropdown in the sidebar or by clicking a marker on the interactive map. European stations are displayed on the map, while non-European stations remain selectable through the dropdown. Choose either soil moisture or GPP to view the comparison. The time series panel shows daily observations as thin lines with monthly means overlaid as thicker lines, where gaps indicate periods of missing data. The scatter plot displays monthly means of ICOS versus CLM5 with a 1:1 reference line for visual assessment of model bias.

            Performance metrics including correlation (r) and Root Mean Square Error (RMSE) are calculated from monthly means over the overlapping observation and simulation period. These statistics are reported only when the overlap period is at least three months, ensuring that the metrics are based on sufficient data to be statistically meaningful.

            <style>
            .citation-link {
                color: var(--bs-success);
                text-decoration: none;
            }
            .citation-link:hover {
                text-decoration: underline;
            }
            </style>
            """
        ),
        style="text-align: left; padding: 15px 20px;",
    ),
    # Sidebar with the selection controls + interactive station map
    ui.page_sidebar(
        ui.sidebar(
            "View settings",
            ui.output_ui("eval_station_highlight"),
            ui.input_select(
                "eval_station",
                "Station",
                choices=_eval_station_choices,
                selected="DE-RuS",  # Selhausen Juellich as default
            ),
            ui.input_select(
                "eval_variable",
                "Variable",
                choices={
                    "sm": "Soil moisture (SWC, %)",
                    "gpp": "Gross primary production (GPP, gC m⁻² d⁻¹)",
                },
                selected="sm",
            ),
            open="always",
            width="300px",
        ),
        ui.div(
            ui.p(
                "Select a station using the dropdown in the sidebar or click on a station marker in the map to compare the ICOS observations with the CLM5 simulation.",
                style="text-align:left; color:#888; margin-bottom:6px;",
            ),
            # Composite panel: interactive map + scatter plot side by side on top,
            # full-width time series below. Plots use transparent backgrounds so
            # the panel blends into the page instead of looking like separate cards.
            ui.div(
                ui.div(
                    ui.div(ui.HTML(eval_map_html), class_="eval-map-cell"),
                    ui.div(
                        ui.output_plot("eval_xy_plot", height=520),
                        class_="eval-xy-cell",
                    ),
                    class_="eval-composite-top",
                ),
                ui.div(
                    ui.output_plot("eval_timeseries_plot", height=480),
                    class_="eval-ts-cell",
                ),
                class_="eval-composite",
            ),
            ui.output_ui("eval_caption"),
        ),
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

                    /* Sidebar styling - applied by default in both states */
                    .bslib-sidebar-layout aside.sidebar {
                        position: static;
                        width: 300px;
                        box-sizing: border-box;
                        background: #2a2a2a !important;
                        border: 1px solid #3a3a3a;
                        border-radius: 4px;
                        box-shadow: 0 1px 4px rgba(0,0,0,0.2);
                        padding: 10px !important;
                        transition: position 0.3s ease, left 0.3s ease;
                    }

                    /* Style the sidebar header/title with grey background only */
                    .bslib-sidebar-layout aside.sidebar .sidebar-header,
                    .bslib-sidebar-layout aside.sidebar header {
                        background-color: #e9ecef !important;
                        color: #333;
                        font-weight: 600;
                        padding: 8px 12px;
                        border-bottom: 1px solid #dee2e6;
                        margin: -10px -10px 10px -10px;
                        border-radius: 4px 4px 0 0;
                        position: relative;
                        top: -10px;
                    }

                    /* Ensure sidebar content area starts after the header */
                    .bslib-sidebar-layout aside.sidebar > div {
                        margin-top: 0;
                    }

                    /* Align sidebar and main content at the top */
                    .bslib-sidebar-layout > .row {
                        align-items: flex-start;
                    }

                    /* Ensure main content aligns vertically with sidebar */
                    .bslib-sidebar-layout .main {
                        padding-top: 0;
                    }

                    /* Fixed state - only changes position to fixed when scrolling past intro */
                    .bslib-sidebar-layout aside.sidebar.is-fixed {
                        position: fixed !important;
                        top: 20px;
                        /* left value set dynamically via JavaScript to match natural position */
                        max-height: calc(100vh - 40px);
                        overflow-y: auto;
                        z-index: 100;
                    }

                    /* Add left margin to main content when sidebar is fixed */
                    .bslib-sidebar-layout.is-scrolled .container,
                    .bslib-sidebar-layout.is-scrolled main .container {
                        margin-left: 355px !important;
                    }

                    /* Card text */
                    .card-body {
                        font-family: Inter, system-ui, -apple-system, sans-serif;
                    }

                    /* Model evaluation: composite panel (map + scatter on top,
                       full-width time series below), blending into the page */
                    .eval-composite {
                        display: flex;
                        flex-direction: column;
                        gap: 12px;
                        max-width: 100%;
                        overflow-x: hidden;
                    }
                    .eval-composite-top {
                        display: grid;
                        grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
                        gap: 12px;
                        align-items: start;
                        width: 100%;
                    }
                    .eval-map-cell,
                    .eval-xy-cell,
                    .eval-ts-cell {
                        min-width: 0;
                        width: 100%;
                    }
                    .eval-map-cell #eval-map {
                        max-width: none !important;
                        margin: 0 !important;
                    }
                    .eval-composite img {
                        width: 100% !important;
                        height: auto !important;
                        display: block;
                    }
                """),
                # JavaScript for scroll-based sidebar behavior.
                # The app contains one sidebar layout per page; always operate
                # on the layout that is currently visible.
                ui.tags.script("""
                document.addEventListener('DOMContentLoaded', function() {
                    function getVisibleLayout() {
                        const layouts = document.querySelectorAll('.bslib-sidebar-layout');
                        for (const layout of layouts) {
                            if (layout.offsetWidth > 0) return layout;
                        }
                        return null;
                    }

                    function handleScroll() {
                        const sidebarLayout = getVisibleLayout();
                        if (!sidebarLayout) return;
                        const sidebar = sidebarLayout.querySelector('aside.sidebar');
                        if (!sidebar) return;

                        // Outer container (parent of page_sidebar)
                        const container = sidebarLayout.parentNode;
                        if (!container) return;

                        // Intro card: first direct child .card of the page
                        const introCard = Array.from(container.children).find(child =>
                            child.classList && child.classList.contains('card')
                        );
                        if (!introCard) return;

                        const rect = introCard.getBoundingClientRect();
                        const triggerPoint = window.pageYOffset + rect.top + rect.height + 30;
                        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
                        const shouldBeFixed = scrollTop > triggerPoint;
                        const isCurrentlyFixed = sidebar.classList.contains('is-fixed');

                        if (shouldBeFixed && !isCurrentlyFixed) {
                            // Pin the sidebar in place (left from viewport edge)
                            sidebar.style.left = sidebar.getBoundingClientRect().left + 'px';
                            sidebar.classList.add('is-fixed');
                            sidebarLayout.classList.add('is-scrolled');
                        } else if (!shouldBeFixed && isCurrentlyFixed) {
                            sidebar.style.left = '';
                            sidebar.classList.remove('is-fixed');
                            sidebarLayout.classList.remove('is-scrolled');
                        }
                    }

                    window.addEventListener('resize', handleScroll, { passive: true });
                    window.addEventListener('scroll', handleScroll, { passive: true });
                    handleScroll(); // Initial check
                });
                """),
    ),
    ui.layout_columns(
        ui.h1(
            "Drought risk on terrestrial ecosystems functioning",
            style="text-align: center;",
        ),
        ui.output_image("iriscc_logo_title", inline=True),
        col_widths=(10, 2),
        style="align-items: center;",
    ),
    ui.navset_card_pill(
        ui.nav_spacer(),
        ui.nav_panel("Droughts and impacts", page_droughts),
        ui.nav_panel("Model evaluation", page_model_evaluation),
        ui.nav_menu(
            "Further Information",
            ui.nav_panel("References", ui.markdown(
                """
                <div class="references-container">
                <h2 id="references">References</h2>

                <div id="hersbach2020" class="reference-item"><strong>Hersbach, H.</strong>, Bell, B., Berrisford, P., Hirahara, S., Horányi, A., Muñoz-Sabater, J., Nicolas, J., Peubey, C., Radu, R., Schepers, D., Simmons, A., Soci, C., Abdalla, S., Abellan, X., Balsamo, G., Bechtold, P., Biavati, G., Bidlot, J., Bonavita, M., et al. (2020). The ERA5 global reanalysis. <em>Quarterly Journal of the Royal Meteorological Society</em>, 146(730), 1999–2049. <a href="https://doi.org/10.1002/qj.3803" target="_blank">https://doi.org/10.1002/qj.3803</a></div>

                <div id="lawrence2019" class="reference-item"><strong>Lawrence, D. M.</strong>, Fisher, R. A., Koven, C. D., Oleson, K. W., Swenson, S. C., Bonan, G., Collier, N., Ghimire, B., van Kampenhout, L., Kennedy, D., Kluzek, E., Lawrence, P. J., Li, F., Li, H., Lombardozzi, D., Riley, W. J., Sacks, W. J., Shi, M., Vertenstein, M., et al. (2019). The Community Land Model Version 5: Description of New Features, Benchmarking, and Impact of Forcing Uncertainty. <em>Journal of Advances in Modeling Earth Systems</em>, 11(12), 4245–4287. <a href="https://doi.org/10.1029/2018MS001583" target="_blank">https://doi.org/10.1029/2018MS001583</a></div>

                <div id="mckee1993" class="reference-item"><strong>McKee, T. B.,</strong> Doesken, N. J., & Kleist, J. (1993). The relationship of drought frequency and duration to time scales. <em>Proceedings of the 8th Conference on Applied Climatology</em>, 179–184. <a href="https://doi.org/10.6" target="_blank">https://doi.org/10.6</a></div>

                <div id="poppe2025" class="reference-item"><strong>Poppe Terán, C.</strong>, Naz, B. S., Vereecken, H., Baatz, R., Fisher, R. A., & Hendricks Franssen, H.-J. (2025). Systematic Underestimation of Type-Specific Ecosystem Process Variability in the Community Land Model v5 over Europe. <em>Geoscientific Model Development</em>, 18(2), 287–317. <a href="https://doi.org/10.5194/gmd-18-287-2025" target="_blank">https://doi.org/10.5194/gmd-18-287-2025</a></div>

                <div id="poppe2023" class="reference-item"><strong>Poppe Terán, C.</strong>, Naz, B. S., Graf, A., et al. (2023). Rising Water-Use Efficiency in European Grasslands Is Driven by Increased Primary Production. <em>Communications Earth & Environment</em>, 4(1), 95. <a href="https://doi.org/10.1038/s43247-023-00757-x" target="_blank">https://doi.org/10.1038/s43247-023-00757-x</a></div>

                <div id="samaniego2018" class="reference-item"><strong>Samaniego, L.</strong>, Thober, S., Kumar, R., Wanders, N., Rakovec, O., Pan, M., Zink, M., Sheffield, J., Wood, E. F., & Marx, A. (2018). Anthropogenic warming exacerbates European soil moisture droughts. <em>Nature Climate Change</em>, 8(5), 421–426. <a href="https://doi.org/10.1038/s41558-018-0138-5" target="_blank">https://doi.org/10.1038/s41558-018-0138-5</a></div>

                <div id="shrestha2026" class="reference-item"><strong>Shrestha, P. K.</strong>, Lenz, K., Modiri, E., Kelbling, M., Kholis, A. N., Lüdke, V. S., Najafi, H., & Samaniego, L. (2026). The European Drought Monitor – EO-powered 1-km daily drought monitoring with 6-day latency. EGU General Assembly 2026, Vienna, Austria, 3–8 May 2026, EGU26-7629. <a href="https://doi.org/10.5194/egusphere-egu26-7629" target="_blank">https://doi.org/10.5194/egusphere-egu26-7629</a></div>

                <div id="thober2019" class="reference-item"><strong>Thober, S.</strong>, Cuntz, M., Kelbling, M., Kumar, R., Mai, J., & Samaniego, L. (2019). The multiscale routing model mRM v1.0: simple river routing at resolutions from 1 to 50 km. <em>Geoscientific Model Development</em>, 12(6), 2501–2521. <a href="https://doi.org/10.5194/gmd-12-2501-2019" target="_blank">https://doi.org/10.5194/gmd-12-2501-2019</a></div>

                <div id="grdc" class="reference-item"><strong>Global Runoff Data Centre (GRDC).</strong> GRDC - The Global Runoff Data Centre. 56068 Koblenz, Germany. <a href="https://www.bafg.de/GRDC" target="_blank">https://www.bafg.de/GRDC</a></div>

                <div id="jureca2018" class="reference-item"><strong>Jülich Supercomputing Centre.</strong> JURECA: Modular supercomputer at Jülich Supercomputing Centre. <em>Journal of large-scale research facilities</em>, 4, A132 (2018). <a href="https://doi.org/10.17815/jlsrf-4-121-1" target="_blank">https://doi.org/10.17815/jlsrf-4-121-1</a></div>
                </div>

                <style>
                .references-container {
                    width: 60%;
                    text-align: left;
                    font-size: 0.9em;
                }
                .references-container h2 {
                    margin-bottom: 0.5em;
                }
                .reference-item {
                    margin-bottom: 0.5em;
                    text-align: justify;
                }
                .references-container a {
                    color: var(--bs-success);
                    text-decoration: underline;
                }
                .references-container a:hover {
                    text-decoration: none;
                }
                </style>
                """
            )),
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


# ── Model-evaluation helpers (ICOS observations vs CLM5) ─────────────────────

# ISO 3166-1 alpha-2 country codes used as the prefix of ICOS station IDs.
COUNTRY_NAMES = {
    "BE": "Belgium",
    "CD": "Democratic Republic of the Congo",
    "CH": "Switzerland",
    "CZ": "Czechia",
    "DE": "Germany",
    "DK": "Denmark",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GF": "French Guiana",
    "GL": "Greenland",
    "GR": "Greece",
    "IE": "Ireland",
    "IT": "Italy",
    "NL": "Netherlands",
    "NO": "Norway",
    "SE": "Sweden",
    "UK": "United Kingdom",
}


def _eval_station_name(station_id: str) -> str:
    """Human-readable station name, falling back to the station ID."""
    if eval_station_meta is not None:
        row = eval_station_meta[eval_station_meta["station_id"] == station_id]
        if not row.empty:
            return str(row.iloc[0]["station_name"])
    return station_id


def _eval_monthly_stats(icos, clm5):
    """Pearson r and RMSE of CLM5 vs ICOS on monthly means of the overlap period."""
    if icos is None or clm5 is None:
        return None
    joined = pd.concat(
        {"obs": icos.resample("ME").mean(), "sim": clm5.resample("ME").mean()}, axis=1
    ).dropna()
    if len(joined) < 3:
        return None
    o = joined["obs"].to_numpy(dtype=float)
    s = joined["sim"].to_numpy(dtype=float)
    return {
        "r": float(np.corrcoef(o, s)[0, 1]),
        "rmse": float(np.sqrt(np.mean((s - o) ** 2))),
        "n": int(len(joined)),
        "obs": joined["obs"],
        "sim": joined["sim"],
    }


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
        fig.patch.set_alpha(0)
        ax.set_facecolor("none")
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
    def reference_period_display():
        """Dynamically show the reference period based on the active tab."""
        active_tab = input.main_tab()

        if active_tab == "Meteorological":
            ref_period = "1961–1990"
        else:  # Agricultural or Hydrological
            ref_period = "1960–1999"

        return ui.div(
            ui.tags.strong(
                f"Reference period: {ref_period}",
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
        )

    @render.ui
    def dynamic_threshold_slider():
        """Dynamically show threshold slider based on active tab and statistic.

        - mean: No threshold (mean index value)
        - min (peak severity): No threshold (minimum value reached)
        - dfreq, maxspell: Show threshold (depends on threshold for counting)
        """
        active_tab = input.main_tab()

        # Only show threshold slider for Meteorological and Agricultural tabs
        if active_tab not in ("Meteorological", "Agricultural"):
            return None

        stat_key = input.statistic()

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

    @render.ui
    def conditional_sidebar_controls():
        """Show different sidebar controls based on the active tab."""
        active_tab = input.main_tab()

        if active_tab == "Hydrological":
            # Show persistence slider and station selector for Hydrological tab
            return ui.div(
                ui.input_slider(
                    "persistence",
                    "Drought persistence (months)",
                    min=1,
                    max=12,
                    value=1,
                    step=1,
                    ticks=False,
                ),
                ui.input_select(
                    "station_select",
                    "Select station",
                    choices=dict(zip(gauge_meta["gauge_id"], gauge_meta["station"])),
                    selected=gauge_meta["gauge_id"].iloc[0] if len(gauge_meta) > 0 else None,
                ),
            )
        elif active_tab in ("Meteorological", "Agricultural"):
            # Show statistic dropdown for Meteorological and Agricultural tabs
            return ui.div(
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
            )
        else:
            return None

    @render.plot
    def render_spi_map():
        from plots import EU1_map

        # Check if we're on the Meteorological tab first
        active_tab = input.main_tab()
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

        # For drought frequency and longest spell, calculate dynamic vmin/vmax based on actual data range
        # This makes the colormap more informative when actual values vary significantly from the default
        if stat_key in ["dfreq", "maxspell"]:
            valid_data = spi_data[~np.isnan(spi_data)]
            if len(valid_data) > 0:
                data_min = float(np.nanmin(valid_data))
                data_max = float(np.nanmax(valid_data))
                # Add small padding (5% of range) to avoid edge clipping
                data_range = data_max - data_min
                padding = data_range * 0.05 if data_range > 0 else 1.0
                dynamic_vmin = max(0, data_min - padding)  # Don't go below 0
                # For maxspell, cap at 730 days (2 years) to preserve variability on the lower side
                if stat_key == "maxspell":
                    dynamic_vmax = min(730, data_max + padding)  # Cap at 2 years
                else:
                    dynamic_vmax = data_max + padding  # No cap for dfreq
            else:
                dynamic_vmin, dynamic_vmax = stat["vmin"], stat["vmax"]
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
        # Only show caption on Meteorological tab
        if input.main_tab() != "Meteorological":
            return None

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

            # Enhanced caption with reorganized structure and detailed explanations
            text = (
                f"<strong>{stat['label'].upper()}</strong> of meteorological drought "
                f"({decade_year}–{decade_year + 9}).<br><br>"
                f"<strong>Drought index:</strong> The Standardized Precipitation Index (SPI) is calculated "
                f"locally for each 3 km pixel by fitting a gamma distribution to the precipitation "
                f"accumulation over the specified aggregation period and transforming it to a standard "
                f"normal distribution (mean=0, standard deviation=1). This local approach ensures that "
                f"statistical references and threshold fits are specific to each pixel's climate. Aggregation "
                f"periods such as 92 days represent the timescale over which precipitation is accumulated "
                f"before calculating the SPI, with longer aggregations capturing more persistent drought "
                f"conditions. Negative SPI values indicate below-average precipitation, with more negative "
                f"values representing increasingly severe drought conditions.<br><br>"
                f"<strong>What the drought frequency statistic shows:</strong> {base_meaning}.<br><br>"
                f"<strong>Threshold:</strong> SPI ≤ {spi_thresh:.1f}<br><br>"
                f"<strong>Reference period:</strong> 1961–1990. This period serves as the climatological "
                f"baseline for the gamma distribution fitting. The SPI values are standardized relative to "
                f"this reference period, allowing consistent comparison of drought severity across time and space.<br><br>"
                f"<strong>Data source:</strong> ERA5 reanalysis "
                f"(<a href='#hersbach2020' class='citation-link'>Hersbach et al., 2020</a>) downscaled to 3 km "
                f"resolution using bilinear interpolation, within the EURO-CORDEX domain."
            )

        return ui.HTML(
            f"<div style='text-align: left; color: #fff; font-size: 14px; line-height: 1.6; padding: 5px 10px 10px 10px; background-color: rgba(240, 173, 78, 0.12); border: 1px solid #f0ad4e; border-left: 4px solid #f0ad4e; border-radius: 6px;'>{text}<style>.citation-link {{ color: var(--bs-success); text-decoration: none; }} .citation-link:hover {{ text-decoration: underline; }}</style></div>"
        )

    @render.ui
    def smi_caption():
        """Dynamic caption for SMI (Agricultural) tab with threshold descriptions."""
        # Only show caption on Agricultural tab
        if input.main_tab() != "Agricultural":
            return None

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

            # Enhanced caption with reorganized structure and detailed explanations
            text = (
                f"<strong>{stat['label'].upper()}</strong> of agricultural drought "
                f"({decade_year}–{decade_year + 9}).<br><br>"
                f"<strong>Drought index:</strong> The Soil Moisture Index (SMI) is a normalized indicator "
                f"of soil moisture conditions, calculated locally for each pixel by comparing the simulated "
                f"soil moisture to the climatological distribution over the reference period. This local "
                f"approach ensures that statistical references and threshold fits are specific to each "
                f"pixel's climate and soil characteristics. SMI values range from 0 (extremely dry) to 1 "
                f"(extremely wet), with lower values indicating drier conditions and increased agricultural "
                f"drought risk.<br><br>"
                f"<strong>What this statistic shows:</strong> {base_meaning}.<br><br>"
                f"<strong>Threshold:</strong> SMI ≤ {selected_thresh:.1f}<br><br>"
                f"<strong>Reference period:</strong> 1960–1999. This period serves as the climatological "
                f"baseline for normalizing soil moisture values. The SMI is standardized relative to this "
                f"reference period, allowing consistent comparison of drought severity across time and space.<br><br>"
                f"<strong>Data sources:</strong> CLM5 (Community Land Model version 5) land surface model "
                f"(<a href='#lawrence2019' class='citation-link'>Lawrence et al., 2019</a>; "
                f"<a href='#poppe2025' class='citation-link'>Poppe Terán et al., 2025</a>) and mHM (mesoscale Hydrological Model) "
                f"hydrological model (<a href='#thober2019' class='citation-link'>Thober et al., 2019</a>) simulations at 3km resolution, integrated between "
                f"both models. Atmospheric forcing: ERA5 reanalysis "
                f"(<a href='#hersbach2020' class='citation-link'>Hersbach et al., 2020</a>), adjustable "
                f"through the sidebar. Soil moisture drought analysis follows "
                f"(<a href='#samaniego2018' class='citation-link'>Samaniego et al., 2018</a>) "
                f"within the EURO-CORDEX domain."
            )

        return ui.HTML(
            f"<div style='text-align: left; color: #fff; font-size: 14px; line-height: 1.6; padding: 5px 10px 10px 10px; background-color: rgba(240, 173, 78, 0.12); border: 1px solid #f0ad4e; border-left: 4px solid #f0ad4e; border-radius: 6px;'>{text}<style>.citation-link {{ color: var(--bs-success); text-decoration: none; }} .citation-link:hover {{ text-decoration: underline; }}</style></div>"
        )

    @render.plot
    def render_eu3_map():
        from plots import EU3_map

        # Check if we're on the Agricultural tab first
        active_tab = input.main_tab()
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

        # For drought frequency and longest spell, calculate dynamic vmin/vmax based on actual data range
        # This makes the colormap more informative when actual values vary significantly from the default
        if stat_key in ["dfreq", "maxspell"]:
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
                dynamic_vmin = max(0, data_min - padding)  # Don't go below 0
                # For maxspell, cap at 730 days (2 years) to preserve variability on the lower side
                if stat_key == "maxspell":
                    dynamic_vmax = min(730, data_max + padding)  # Cap at 2 years
                else:
                    dynamic_vmax = data_max + padding  # No cap for dfreq
            else:
                dynamic_vmin, dynamic_vmax = stat["vmin"], stat["vmax"]
        else:
            dynamic_vmin, dynamic_vmax = stat["vmin"], stat["vmax"]

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

        ax.set_title(
            title,
            color=c["text"],
            fontsize=12,
            pad=8,
            family=tc.get_font_family('heading')
        )
        ax.set_ylabel(
            "Discharge (m³ s⁻¹)",
            color=c["text"],
            fontsize=tc.font_sizes['base'],
            family=tc.get_font_family('body')
        )
        ax.set_xlabel(
            "Date",
            color=c["text"],
            fontsize=tc.font_sizes['base'],
            family=tc.get_font_family('body')
        )
        ax.tick_params(colors=c["text"], labelsize=tc.font_sizes['small'])

        # Hide spines for modern look
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.legend(
            facecolor=c["background"],
            edgecolor=c["border"],
            labelcolor=c["text"],
            prop=FontProperties(family=tc.get_font_family('body'), size=tc.font_sizes['small']),
            framealpha=0.9
        )
        ax.grid(True, color="#ffffff", alpha=0.25, linewidth=0.7, zorder=0)
        # Prevent Shiny from calling tight_layout which can cause issues
        fig.tight_layout = lambda *a, **kw: None
        return fig

    @render.plot
    def drought_hydrograph():
        """Render drought hydrograph for the clicked gauge.

        Creates a matplotlib figure showing observed discharge with drought
        thresholds and inset plots.
        """
        # selected_gauge is injected by the Leaflet JS via Shiny.setInputValue;
        # it doesn't exist until the user clicks, so guard against that.
        try:
            gauge_id = input.selected_gauge()
        except Exception:
            return None
        if not gauge_id:
            return None

        # Get decade year from the slider, default to first available decade
        try:
            dec_date = input.dec()
            decade_year = dec_date.year
        except Exception:
            # Default to None to let the function determine the first available decade
            decade_year = None

        # Get persistence value
        try:
            persistence = input.persistence()
        except Exception:
            persistence = 1  # default

        # Generate drought hydrograph using Python implementation
        try:
            from drought_hydrograph import create_drought_hydrograph
            fig = create_drought_hydrograph(gauge_id, decade_year, persistence)
            return fig
        except Exception as e:
            print(f"Error creating drought hydrograph: {e}")
            import traceback
            traceback.print_exc()
            return None

    @render.ui
    def drought_hydrograph_caption():
        """Dynamic caption for drought hydrograph with detailed information."""
        # Get theme colors
        tc = get_theme_config("dark")
        c = tc.colors

        # selected_gauge is injected by the Leaflet JS via Shiny.setInputValue
        try:
            gauge_id = input.selected_gauge()
        except Exception:
            return None
        if not gauge_id:
            return None

        # Get decade year from the slider
        try:
            dec_date = input.dec()
            decade_year = dec_date.year
        except Exception:
            decade_year = 1960  # default

        # Get persistence value
        try:
            persistence = input.persistence()
        except Exception:
            persistence = 1  # default

        # Get gauge metadata for station name
        row = gauge_meta.loc[gauge_meta["gauge_id"] == gauge_id]
        if not row.empty:
            r = row.iloc[0]
            station_name = r.get('station', 'Unknown Station')
            river_name = r.get('river', 'Unknown River')
            country = r.get('country', 'Unknown Country')
        else:
            station_name = gauge_id
            river_name = "Unknown River"
            country = "Unknown Country"

        # Build the descriptive text
        text = (
            f"<strong>MONTHLY HYDROLOGICAL DROUGHT ANALYSIS</strong><br><br>"
            f"<strong>Station:</strong> {station_name} ({gauge_id})<br>"
            f"<strong>River:</strong> {river_name}<br>"
            f"<strong>Country:</strong> {country}<br>"
            f"<strong>Period:</strong> {decade_year}–{decade_year + 9}<br><br>"
            f"This drought hydrograph shows the monthly streamflow (blue line) for the selected gauge "
            f"over the decade, overlaid with two drought threshold curves (orange shading):<br>"
            f"• <strong style='color: {c['warning']};'>10-year return period threshold</strong> (Q10): "
            f"Streamflow values below this threshold occur approximately once every 10 years on average. "
            f"Areas shaded in light orange indicate months where streamflow fell below this threshold.<br>"
            f"• <strong style='color: {c['danger']};'>50-year return period threshold</strong> (Q50): "
            f"Streamflow values below this threshold occur approximately once every 50 years on average, "
            f"representing exceptional drought conditions. Darker orange shading indicates these extreme events.<br><br>"
            f"The inset plots provide additional insights:<br>"
            f"• <strong>Total drought events:</strong> Number of distinct drought events over the decade (an event is a run of {persistence}+ consecutive months below a threshold)<br>"
            f"• <strong>Drought months by month of year:</strong> Which calendar months are most drought-prone over the decade<br><br>"
            f"<strong>Persistence parameter:</strong> {persistence}+ consecutive months (minimum duration for drought event)<br><br>"
            f"<strong>Reference period:</strong> 1960–1999 (thresholds calculated relative to this baseline)<br><br>"
            f"<strong>Data sources:</strong> Simulated discharge data only. Streamflow time series generated by the mesoscale "
            f"Hydrological Model (mHM, <a href='#thober2019' class='citation-link'>Thober et al., 2019</a>) at 3 km resolution, "
            f"forced with ERA5 reanalysis data (<a href='#hersbach2020' class='citation-link'>Hersbach et al., 2020</a>). "
            f"No observed discharge data are used in this analysis."
        )

        return ui.HTML(
            f"<div style='text-align: left; color: #fff; font-size: 14px; line-height: 1.6; "
            f"padding: 5px 10px 10px 10px; background-color: rgba(240, 173, 78, 0.12); "
            f"border: 1px solid #f0ad4e; border-left: 4px solid #f0ad4e; border-radius: 6px;'>{text}<style>.citation-link {{ color: var(--bs-success); text-decoration: none; }} .citation-link:hover {{ text-decoration: underline; }}</style></div>"
        )

    @render.ui
    def drought_hydrograph_container():
        """Dynamically render drought hydrograph panel."""
        # selected_gauge is injected by the Leaflet JS via Shiny.setInputValue;
        # it doesn't exist until the user clicks, so guard against that.
        try:
            gauge_id = input.selected_gauge()
        except Exception:
            return ui.markdown("*Click a gauge marker to view its hydrograph.*")
        if not gauge_id:
            return ui.markdown("*Click a gauge marker to view its hydrograph.*")

        return ui.output_plot("drought_hydrograph", height="750px")

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

    # ── Model evaluation: ICOS reference observations vs CLM5 ────────────────

    @render.ui
    def eval_station_highlight():
        """Highlighted station info at the top of the sidebar (similar to reference period)."""
        try:
            station_id = input.eval_station()
        except Exception:
            return None
        if station_id is None or eval_station_meta is None:
            return ui.div(
                ui.tags.strong(f"Station ID: {station_id}", style="font-size: 0.85em;"),
                style=(
                    "border: 1px solid #f0ad4e; "
                    "border-left: 4px solid #f0ad4e; "
                    "background-color: rgba(240, 173, 78, 0.12); "
                    "border-radius: 6px; "
                    "padding: 10px 12px; "
                    "margin-bottom: 14px; "
                    "text-align: left;"
                ),
            )
        row = eval_station_meta[eval_station_meta["station_id"] == station_id]
        if row.empty:
            return None
        r = row.iloc[0]
        country = COUNTRY_NAMES.get(station_id.split("-")[0], station_id.split("-")[0])
        return ui.div(
            ui.tags.strong(f"Station ID: {station_id}", style="font-size: 0.85em;"),
            ui.tags.br(),
            ui.tags.span(f"Country: {country}", style="font-size: 0.75em;"),
            ui.tags.br(),
            ui.tags.span(
                f"Coords: {r['latitude']:.2f}° N, {r['longitude']:.2f}° E",
                style="font-size: 0.75em;",
            ),
            ui.tags.br(),
            ui.tags.span(
                f"CLM5 cell: {r['cell_latitude']:.2f}° N, {r['cell_longitude']:.2f}° E",
                style="font-size: 0.75em;",
            ),
            ui.tags.br(),
            ui.tags.span(
                f"Distance: {r['distance_km']:.1f} km",
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
        )

    @render.ui
    def eval_site_info():
        """Metadata panel for the selected ICOS station (without station name/ID)."""
        try:
            station_id = input.eval_station()
        except Exception:
            return None
        if station_id is None or eval_station_meta is None:
            return ui.markdown(
                "*Evaluation data not available — download the files with "
                "`evaluation/download.py` first.*"
            )
        row = eval_station_meta[eval_station_meta["station_id"] == station_id]
        if row.empty:
            return None
        r = row.iloc[0]
        country = COUNTRY_NAMES.get(station_id.split("-")[0], station_id.split("-")[0])
        fields = [
            ("Country", country),
            ("Coordinates", f"{r['latitude']:.2f}°, {r['longitude']:.2f}°"),
            ("CLM5 cell centre", f"{r['cell_latitude']:.2f}°, {r['cell_longitude']:.2f}°"),
            ("Station → cell", f"{r['distance_km']:.1f} km"),
        ]
        html_rows = "".join(
            f"<tr><td style='padding: 2px 14px 2px 0; color: #999;'>{k}</td>"
            f"<td style='padding: 2px 0;'>{v}</td></tr>"
            for k, v in fields
        )
        return ui.HTML(
            f"<table style='width: 100%; font-size: 13px; margin-top: 12px; "
            f"border-collapse: collapse;'>{html_rows}</table>"
        )

    @render.plot
    def eval_timeseries_plot():
        """Daily ICOS vs CLM5 time series with monthly-mean overlay and stats."""
        try:
            station_id = input.eval_station()
            variable = input.eval_variable()
        except Exception:
            return None
        if station_id is None or variable not in EVAL_VARIABLES:
            return None
        spec = EVAL_VARIABLES[variable]
        icos, clm5 = get_eval_series(station_id, variable)
        if icos is None or clm5 is None or len(icos) < 2:
            return _message_fig(f"No {spec['label']} data available for {station_id}.")

        tc = get_theme_config("dark")
        c = tc.colors

        # Reindex to complete date range to insert NaN at gaps (prevents lines across missing data)
        full_idx = pd.date_range(icos.index.min(), icos.index.max(), freq="D")
        icos = icos.reindex(full_idx)
        clm5 = clm5.reindex(full_idx)

        # Monthly means - DON'T dropna, preserve NaN months as gaps
        icos_mo = icos.resample("ME").mean()
        clm5_mo = clm5.resample("ME").mean()

        # For statistics, use only non-NaN data
        stats = _eval_monthly_stats(icos.dropna(), clm5.dropna())

        # Check for sufficient overlap (same threshold as XY plot)
        if stats is None:
            return _message_fig(f"Overlap shorter than 3 months for {station_id} — too few monthly means for statistics.")

        fig, ax = plt.subplots(figsize=(13.3, 4.8))
        fig.patch.set_alpha(0)
        ax.set_facecolor("none")

        # Hydrograph blue (#4dabf7) for ICOS to match the hydrograph section, thicker monthly lines
        ax.plot(icos.index, icos.values, color="#4dabf7", linewidth=0.8, alpha=0.7, label="ICOS (daily)")
        ax.plot(clm5.index, clm5.values, color="#bb86fc", linewidth=0.8, alpha=0.65, label="CLM5 (daily)")
        ax.plot(icos_mo.index, icos_mo.values, color="#4dabf7", linewidth=2.8, label="ICOS (monthly mean)")
        ax.plot(clm5_mo.index, clm5_mo.values, color="#bb86fc", linewidth=2.8, label="CLM5 (monthly mean)")

        ax.set_ylabel(f"{spec['abbr']} ({spec['unit']})", color=c["text"], fontsize=tc.font_sizes["base"], family=tc.get_font_family("mono"))
        ax.set_xlabel("Date", color=c["text"], fontsize=tc.font_sizes["base"], family=tc.get_font_family("mono"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.tick_params(colors=c["text"], labelsize=tc.font_sizes["small"])
        plt.setp(ax.get_xticklabels(), ha="center", family=tc.get_font_family("mono"))
        plt.setp(ax.get_yticklabels(), family=tc.get_font_family("mono"))
        # Hide spines for modern look
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.grid(True, color="#ffffff", alpha=0.25, linewidth=0.7, zorder=0)
        ax.legend(
            loc="upper center",
            bbox_to_anchor=(0.5, 1.12),
            ncol=4,
            frameon=False,
            handlelength=1.5,
            labelcolor=c["text"],
            prop=FontProperties(family=tc.get_font_family("mono"), size=tc.font_sizes["small"]),
        )
        if stats is not None:
            ax.text(
                0.99,
                0.03,
                f"r = {stats['r']:.2f}   RMSE = {stats['rmse']:.3f} {spec['unit']}   (monthly means, n = {stats['n']})",
                transform=ax.transAxes,
                ha="right",
                va="bottom",
                color=c["text"],
                fontsize=tc.font_sizes["small"],
                family=tc.get_font_family("mono"),
                bbox=dict(boxstyle="round,pad=0.35", facecolor=c["background"], edgecolor=c["border"], alpha=0.9),
            )
        fig.tight_layout = lambda *a, **kw: None
        return fig

    @render.plot
    def eval_xy_plot():
        """CLM5 vs ICOS scatter (monthly means) with 1:1 reference line."""
        try:
            station_id = input.eval_station()
            variable = input.eval_variable()
        except Exception:
            return None
        if station_id is None or variable not in EVAL_VARIABLES:
            return None
        spec = EVAL_VARIABLES[variable]
        icos, clm5 = get_eval_series(station_id, variable)
        stats = _eval_monthly_stats(icos, clm5)
        if icos is None or clm5 is None or len(icos) < 2:
            return _message_fig(f"No {spec['label']} data available for {station_id}.")
        if stats is None:
            return _message_fig(f"Overlap shorter than 3 months for {station_id} — too few monthly means to compare.")

        tc = get_theme_config("dark")
        c = tc.colors
        o, s = stats["obs"], stats["sim"]

        fig, ax = plt.subplots(figsize=(6.5, 5.2))
        fig.patch.set_alpha(0)
        ax.set_facecolor("none")

        ax.scatter(o, s, s=25, color="#4dabf7", alpha=0.75, edgecolors="none", label="monthly means")
        lo, hi = min(o.min(), s.min()), max(o.max(), s.max())
        ax.plot([lo, hi], [lo, hi], color=c["text"], linestyle="--", linewidth=1, alpha=0.7, label="1:1")
        ax.set_xlabel(f"ICOS {spec['abbr']} ({spec['unit']})", color=c["text"], fontsize=tc.font_sizes["base"], family=tc.get_font_family("mono"))
        ax.set_ylabel(f"CLM5 {spec['abbr']} ({spec['unit']})", color=c["text"], fontsize=tc.font_sizes["base"], family=tc.get_font_family("mono"))
        ax.tick_params(colors=c["text"], labelsize=tc.font_sizes["small"])
        plt.setp(ax.get_xticklabels(), family=tc.get_font_family("mono"))
        plt.setp(ax.get_yticklabels(), family=tc.get_font_family("mono"))
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.grid(True, color="#ffffff", alpha=0.25, linewidth=0.7, zorder=0)
        ax.legend(
            facecolor=c["background"],
            edgecolor=c["border"],
            labelcolor=c["text"],
            prop=FontProperties(family=tc.get_font_family("mono"), size=tc.font_sizes["small"]),
            framealpha=0.9,
        )
        ax.text(
            0.99,
            0.03,
            f"r = {stats['r']:.2f}   RMSE = {stats['rmse']:.3f} {spec['unit']}",
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            color=c["text"],
            fontsize=tc.font_sizes["small"],
            family=tc.get_font_family("mono"),
            bbox=dict(boxstyle="round,pad=0.35", facecolor=c["background"], edgecolor=c["border"], alpha=0.9),
        )
        fig.tight_layout = lambda *a, **kw: None
        return fig

    @render.ui
    def eval_caption():
        """Descriptive caption for the model-evaluation plots."""
        try:
            station_id = input.eval_station()
            variable = input.eval_variable()
        except Exception:
            return None
        if station_id is None or variable not in EVAL_VARIABLES:
            return None
        spec = EVAL_VARIABLES[variable]
        name = _eval_station_name(station_id)
        country = COUNTRY_NAMES.get(station_id.split("-")[0], station_id.split("-")[0])
        meta_row = None
        if eval_station_meta is not None:
            row = eval_station_meta[eval_station_meta["station_id"] == station_id]
            if not row.empty:
                meta_row = row.iloc[0]
        var_text = {
            "sm": (
                "Soil water content of the first soil layer (SWC_1, volumetric water content in %). "
                "ICOS values are the reference observations; CLM5 values come from the model grid cell nearest to the station."
            ),
            "gpp": (
                "Gross primary production (GPP) - total carbon fixed by plant photosynthesis. "
                "Both ICOS and CLM5 report GPP as positive carbon uptake (gC m⁻² d⁻¹)."
            ),
        }[variable]
        coords = "n/a"
        cell = "n/a"
        if meta_row is not None:
            coords = f"{meta_row['latitude']:.2f}°, {meta_row['longitude']:.2f}°"
            cell = f"{meta_row['cell_latitude']:.2f}°, {meta_row['cell_longitude']:.2f}° ({meta_row['distance_km']:.1f} km from the station)"
        icos, clm5 = get_eval_series(station_id, variable)
        stats = _eval_monthly_stats(icos, clm5)

        head = (
            f"<strong>{spec['label'].upper()} AT {station_id}</strong><br><br>"
            f"<strong>Station:</strong> {name} ({country})<br>"
            f"<strong>Coordinates:</strong> {coords}<br>"
            f"<strong>CLM5 cell:</strong> {cell}<br><br>"
            f"{var_text}<br><br>"
        )
        if icos is None or clm5 is None or len(icos) < 2:
            text = head + (
                "No overlapping data between the ICOS reference observations and CLM5 "
                "for this station/variable."
            )
        elif stats is None:
            period = f"{icos.index.min():%Y-%m} to {icos.index.max():%Y-%m}"
            text = head + (
                f"<strong>Overlap period:</strong> {period}<br><br>"
                "The overlap is shorter than 3 months, so the time series is shown, "
                "but correlation and RMSE are not reported."
            )
        else:
            period = f"{icos.index.min():%Y-%m} to {icos.index.max():%Y-%m}"
            text = head + (
                f"<strong>Overlap period:</strong> {period}<br><br>"
                f"The time series shows the daily observations and simulation over the overlapping period, "
                f"with monthly means as thick lines. The scatter plot compares monthly means of CLM5 (y-axis) "
                f"against ICOS (x-axis) around the 1:1 line.<br><br>"
                f"<strong>Model performance (monthly means):</strong> Pearson r = {stats['r']:.2f}, "
                f"RMSE = {stats['rmse']:.3f} {spec['unit']} (n = {stats['n']} months)."
            )
        return ui.HTML(
            f"<div style='text-align: left; color: #fff; font-size: 14px; line-height: 1.6; "
            f"padding: 5px 10px 10px 10px; background-color: rgba(240, 173, 78, 0.12); "
            f"border: 1px solid #f0ad4e; border-left: 4px solid #f0ad4e; border-radius: 6px;'>{text}</div>"
        )


app = App(app_ui, server)

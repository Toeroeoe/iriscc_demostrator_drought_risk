from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Literal, Optional

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from cartopy.mpl import geoaxes
from matplotlib.gridspec import GridSpec
from matplotlib.layout_engine import LayoutEngine
from theme_config import ThemeConfig


# ── Cached static basemap ────────────────────────────────────────────────────
# The ocean/land/coastline basemap never changes, but cartopy re-reads and
# re-parses the Natural Earth shapefiles on every add_feature()/coastlines()
# call. Caching the parsed geometries once per process removes that repeated
# disk I/O + parsing from every plot render.
_PLATE_CARREE = ccrs.PlateCarree()


@lru_cache(maxsize=None)
def _cached_ne_geometries(category: str, name: str, scale: str) -> tuple:
    """Load and cache Natural Earth geometries once per process."""
    feature = cfeature.NaturalEarthFeature(category, name, scale)
    return tuple(feature.geometries())


def _add_cached_basemap(
    ax,
    *,
    ocean_color: str,
    land_color: str,
    alpha_ocean: float,
    alpha_land: float,
    coastline_lw: float,
) -> None:
    """Draw the static ocean/land/coastline basemap from cached geometries.

    Mirrors the previous ``add_feature(OCEAN/LAND)`` + ``coastlines()`` calls
    (same 110m Natural Earth data, colours and z-orders) but reuses geometries
    cached across renders instead of re-reading the shapefiles each time.
    """
    ax.add_geometries(
        _cached_ne_geometries("physical", "ocean", "110m"),
        _PLATE_CARREE,
        facecolor=ocean_color,
        edgecolor=ocean_color,
        alpha=alpha_ocean,
        zorder=0,
    )
    ax.add_geometries(
        _cached_ne_geometries("physical", "land", "110m"),
        _PLATE_CARREE,
        facecolor=land_color,
        edgecolor=land_color,
        alpha=alpha_land,
        zorder=0,
    )
    ax.add_geometries(
        _cached_ne_geometries("physical", "coastline", "110m"),
        _PLATE_CARREE,
        facecolor="none",
        edgecolor="black",
        linewidth=coastline_lw,
        zorder=2,
    )


class _NoOpLayoutEngine(LayoutEngine):
    """A no-op layout engine that satisfies Shiny's compatibility check.

    Shiny inspects ``fig.get_layout_engine()``:
    - If falsy  → installs TightLayoutEngine (bad for GeoAxes).
    - If truthy and ``adjust_compatible=False`` → also installs TightLayoutEngine.
    - If truthy and ``adjust_compatible=True``  → leaves the engine alone (good).

    We need an engine that is truthy, has ``adjust_compatible=True``, and
    whose ``execute()`` is a no-op so it never calls tight_layout.
    """

    _adjust_compatible = True
    _colorbar_gridspec = True

    def execute(self, fig) -> None:  # type: ignore[override]
        pass  # deliberately do nothing


# FONT STRATEGY - Consistent with Shiny App:
# 1. BODY: Inter → axis labels, legend, tick labels
# 2. HEADING: Crimson Text → plot titles
# 3. MONO: IBM Plex Mono → grid labels, coordinate labels


@dataclass(kw_only=True)
class demo_fig:
    title: List[str] = field(default_factory=list)
    suptitle: str = ""
    description: str

    theme_config: ThemeConfig

    color_mode: Literal["light", "dark"] = "dark"

    # Screen-resolution DPI. These maps are only ever displayed in the browser,
    # so print-quality DPI just makes rendering slower and the PNG payload
    # larger with no visible benefit.
    dpi: int = 100

    fy: float = 6.7
    fx: float = 4

    projection: None | ccrs.Projection = None

    # Point size for map/plot titles (suptitle is this + 2). Shiny renders the
    # figure at its own dpi, so on-screen text height ≈ point_size * dpi / 72.
    fs_title: int = 16

    def __post_init__(self):

        # Apply theme to matplotlib
        self.theme_config.apply_to_matplotlib()
        self.palette = self.theme_config.get_plot_palette()

        self.fig = plt.figure(figsize=(self.fx, self.fy), dpi=self.dpi)
        # Install a no-op layout engine so Shiny sees a truthy, adjust_compatible
        # engine and leaves it alone instead of replacing it with tight layout.
        self.fig.set_layout_engine(_NoOpLayoutEngine())
        self.fig.tight_layout = lambda *a, **kw: None  # belt-and-braces

        # Create GridSpec with 3 columns: plot1, plot2, colorbar
        self.gs = GridSpec(
            figure=self.fig,
            nrows=1,
            ncols=3,
            width_ratios=[1, 1, 0.08],  # Two equal plots, narrow colorbar
            wspace=0.26,  # Spacing between subplots
            left=0.01,  # Remove left margin
            right=0.91,  # Leave space for colorbar label
            top=0.92,  # Remove top margin
            bottom=0.04,  # Remove bottom margin
        )

        self.fig.patch.set_alpha(0.0)
        # Use theme text color instead of hardcoded white
        mpl.rcParams["text.color"] = self.palette["text"]

        self.fig.suptitle(
            self.suptitle,
            fontsize=self.fs_title + 2,
            x=0.5,  # Center over the full figure so long titles don't clip
            y=0.98,
            fontfamily=self.theme_config.get_font_family("heading"),
            color=self.palette["text"],
        )

        # Prevent Shiny's fig.tight_layout() from corrupting GeoAxes layout
        self.fig.tight_layout = lambda *a, **kw: None

    def create_axes(self):

        self.ax = self.fig.add_subplot(self.gs[0, 0], projection=self.projection)

        self.ax2 = self.fig.add_subplot(self.gs[0, 1], projection=self.projection)

        for ax in [self.ax, self.ax2]:
            ax.spines.right.set_visible(False)
            ax.spines.top.set_visible(False)
            ax.spines.bottom.set_visible(False)
            ax.spines.left.set_visible(False)

        self.ax.set_title(
            self.title[0] if len(self.title) > 0 else "",
            fontsize=self.fs_title,
            y=1.01,
            fontfamily=self.theme_config.get_font_family(
                "heading"
            ),  # Elegant serif for titles
            fontweight=400,  # Match Shiny CSS font-weight: 400 (normal)
            color=self.theme_config.colors["text"],  # Use theme text color
        )
        self.ax2.set_title(
            self.title[1] if len(self.title) > 1 else "",
            fontsize=self.fs_title,
            y=1.01,
            fontfamily=self.theme_config.get_font_family(
                "heading"
            ),  # Elegant serif for titles
            fontweight=400,  # Match Shiny CSS font-weight: 400 (normal)
            color=self.theme_config.colors["text"],  # Use theme text color
        )
        # Apply text color to axis tick labels
        self.ax.tick_params(colors=self.theme_config.colors["text"])
        self.ax2.tick_params(colors=self.theme_config.colors["text"])

        return self.fig, self.gs, [self.ax, self.ax2]

    def save(self, path: str):
        self.fig.savefig(path, dpi=self.dpi, bbox_inches="tight", pad_inches=0.1)


@dataclass(kw_only=True)
class EU1_map(demo_fig):
    """Single-panel European map.  Mirrors EU3_map but renders one plot + colorbar."""

    title: List[str] = field(default_factory=list)
    description: str = ""
    rotnpole_lat: float = 39.25
    rotnpole_lon: float = -162.0
    semmj_axis: int = 6370000
    semmn_axis: int = 6370000
    lon_extents: List[float] = field(default_factory=lambda: [351.1, 57])
    lat_extents: List[float] = field(default_factory=lambda: [27, 65.7])
    ocean_color: str = "#a6cee3"
    land_color: str = "#636363"
    alpha_ocean: float = 0.8
    alpha_land: float = 0.8
    coastline_lw: float = 0.8
    grid_lw: float = 0.8
    grid_color: str = "grey"
    grid_linestyle: str = "--"
    # Point size for gridline labels, colorbar label and colorbar ticks.
    fs_map_label: int = 12
    cbar_width_ratio: float = 0.05
    pcolormesh_obj: Optional[object] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Override demo_fig to use a 2-column GridSpec (map + colorbar)."""
        self.theme_config.apply_to_matplotlib()
        self.palette = self.theme_config.get_plot_palette()

        # Prevent matplotlib / Shiny from calling tight_layout on this figure.
        # GeoAxes are incompatible with tight_layout and it corrupts the
        # manually specified GridSpec margins.
        mpl.rcParams["figure.autolayout"] = False

        self.fig = plt.figure(figsize=(self.fx, self.fy), dpi=self.dpi)

        # Belt-and-braces: replace tight_layout on the figure object so that
        # Shiny's internal fig.tight_layout() call becomes a no-op.
        # Install the same no-op layout engine so Shiny leaves it alone.
        self.fig.set_layout_engine(_NoOpLayoutEngine())
        self.fig.tight_layout = lambda *a, **kw: None

        self.gs = GridSpec(
            figure=self.fig,
            nrows=1,
            ncols=2,
            width_ratios=[1, self.cbar_width_ratio],
            wspace=0.2,  # increased gap between map and colorbar
            left=0.02,
            right=0.90,
            top=0.98,  # Removed title, minimal top space
            bottom=0.10,  # room below axes for latitude tick labels
        )
        self.fig.patch.set_alpha(0.0)
        mpl.rcParams["text.color"] = self.palette["text"]
        self.fig.suptitle(
            "",  # No suptitle - info shown in caption below
            fontsize=self.fs_title + 2,
            x=0.5,
            y=0.98,
            fontfamily=self.theme_config.get_font_family("heading"),
            color=self.palette["text"],
        )

    def create(self):
        self.plot_projection = ccrs.PlateCarree()
        self.globe = ccrs.Globe(
            semimajor_axis=self.semmj_axis,
            semiminor_axis=self.semmn_axis,
        )
        self.projection = ccrs.RotatedPole(
            pole_longitude=self.rotnpole_lon,
            pole_latitude=self.rotnpole_lat,
            globe=self.globe,
        )

        self.ax = self.fig.add_subplot(self.gs[0, 0], projection=self.projection)

        for spine in self.ax.spines.values():
            spine.set_visible(False)

        self.ax.set_title(
            self.title[0] if self.title else "",
            fontsize=self.fs_title,
            y=1.01,
            fontfamily=self.theme_config.get_font_family("heading"),
            fontweight=300,
            color=self.theme_config.colors["text"],
        )
        self.ax.tick_params(colors=self.theme_config.colors["text"])

        _add_cached_basemap(
            self.ax,
            ocean_color=self.ocean_color,
            land_color=self.land_color,
            alpha_ocean=self.alpha_ocean,
            alpha_land=self.alpha_land,
            coastline_lw=self.coastline_lw,
        )

        proj_lon_extents, proj_lat_extents, _ = self.ax.projection.transform_points(  # type: ignore[union-attr]
            self.plot_projection,
            np.array(self.lon_extents),
            np.array(self.lat_extents),
        ).T
        self.ax.set_extent([*proj_lon_extents, *proj_lat_extents])  # type: ignore[union-attr]

        gl = self.ax.gridlines(  # type: ignore[union-attr]
            crs=self.plot_projection,
            linewidth=self.grid_lw,
            color=self.grid_color,
            linestyle=self.grid_linestyle,
            draw_labels=True,
            x_inline=False,
            y_inline=False,
            zorder=5,
        )
        gl.top_labels = False
        gl.right_labels = True
        gl.left_labels = False
        gl.bottom_labels = True
        _label_style = {
            "size": self.fs_map_label,
            "fontfamily": self.theme_config.get_font_family("mono"),
            "color": self.theme_config.colors["text"],
        }
        gl.ylabel_style = _label_style
        gl.xlabel_style = _label_style

        return self.fig, self.gs, [self.ax]

    def pcolormesh(
        self,
        lon: np.ndarray,
        lat: np.ndarray,
        data: np.ndarray,
        cmap: str = "RdBu",
        vmin: float | None = None,
        vmax: float | None = None,
        **kwargs,
    ):
        self.pcolormesh_obj = self.ax.pcolormesh(
            lon,
            lat,
            data,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            transform=self.plot_projection,
            rasterized=True,
            shading="nearest",
            antialiased=True,
            **kwargs,
        )
        return self.pcolormesh_obj

    def colorbar(self, colormesh, cbar_label: str = "", extend: str = "neither"):
        if self.pcolormesh_obj is None:
            raise ValueError("Call pcolormesh() before colorbar().")
        cbar_ax = self.fig.add_subplot(self.gs[0, 1])
        pos = cbar_ax.get_position()
        new_height = pos.height * 0.8
        cbar_ax.set_position(
            (
                pos.x0,
                pos.y0 + (pos.height - new_height) / 2,
                pos.width,
                new_height,
            )
        )
        self.cbar = self.fig.colorbar(
            colormesh, cax=cbar_ax, orientation="vertical", extend=extend
        )
        self.cbar.set_label(
            cbar_label,
            fontfamily=self.theme_config.get_font_family("mono"),
            fontsize=self.fs_map_label,
            color=self.theme_config.colors["text"],
            rotation=270,  # Vertical label (top to bottom)
            labelpad=20,  # Original padding
        )
        self.cbar.ax.tick_params(
            labelsize=self.fs_map_label, colors=self.theme_config.colors["text"]
        )
        for lbl in self.cbar.ax.get_yticklabels():
            lbl.set_fontfamily(self.theme_config.get_font_family("mono"))
            lbl.set_color(self.theme_config.colors["text"])
        return self.cbar

    def save(self, path: str):
        self.fig.savefig(path, dpi=self.dpi, bbox_inches="tight", pad_inches=0.1)


@dataclass(kw_only=True)
class EU3_map(demo_fig):
    title: List[str] = field(default_factory=list)
    description: str
    rotnpole_lat: float = 39.25
    rotnpole_lon: float = -162.0

    semmj_axis: int = 6370000
    semmn_axis: int = 6370000

    lon_extents: List[float] = field(default_factory=lambda: [351.1, 57])
    lat_extents: List[float] = field(default_factory=lambda: [27, 65.7])

    ocean_color: str = "#a6cee3"
    land_color: str = "#636363"
    alpha_ocean: float = 0.8
    alpha_land: float = 0.8

    coastline_lw: float = 0.8
    grid_lw: float = 0.8
    grid_color: str = "grey"
    grid_linestyle: str = "--"

    # Point size for gridline labels, colorbar label and colorbar ticks.
    fs_map_label: int = 12

    # Option for horizontal colorbar below plots
    horizontal_cbar: bool = False

    # For efficient pcolormesh updates
    pcolormesh_obj: Optional[object] = field(default=None, init=False, repr=False)
    pcolormesh_obj2: Optional[object] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Override demo_fig to use different GridSpec layout for horizontal colorbar."""
        # Apply theme to matplotlib
        self.theme_config.apply_to_matplotlib()
        self.palette = self.theme_config.get_plot_palette()

        # Adjust figure size for horizontal colorbar layout
        # Using larger dimensions to reduce spacing issues while maintaining aspect ratio
        if self.horizontal_cbar:
            # Wider and taller for two maps + horizontal colorbar
            fig_width = 10.0   # Wider for two side-by-side maps
            fig_height = 8.6   # Taller by 15% (7.5 * 1.15) to accommodate colorbar label
        else:
            fig_width = self.fx
            fig_height = self.fy

        self.fig = plt.figure(figsize=(fig_width, fig_height), dpi=self.dpi)
        # Install a no-op layout engine so Shiny sees a truthy, adjust_compatible
        # engine and leaves it alone instead of replacing it with tight layout.
        self.fig.set_layout_engine(_NoOpLayoutEngine())
        self.fig.tight_layout = lambda *a, **kw: None  # belt-and-braces

        if self.horizontal_cbar:
            # Create GridSpec with 2 rows: plots on top, horizontal colorbar below
            self.gs = GridSpec(
                figure=self.fig,
                nrows=2,
                ncols=2,
                height_ratios=[1, 0.08],  # Plots tall, colorbar at 8% of plot height (increased from 6%)
                wspace=0.15,  # Horizontal space between plots
                hspace=0.0,  # No vertical space between plot row and colorbar row
                left=0.08,  # Left margin for y-axis labels
                right=0.92,  # Right margin for gridline labels
                top=0.98,  # Removed title, minimal top space
                bottom=0.12,  # Increased bottom margin to accommodate colorbar label
            )
        else:
            # Create GridSpec with 3 columns: plot1, plot2, colorbar
            self.gs = GridSpec(
                figure=self.fig,
                nrows=1,
                ncols=3,
                width_ratios=[1, 1, 0.08],  # Two equal plots, narrow colorbar
                wspace=0.26,  # Spacing between subplots
                left=0.01,  # Remove left margin
                right=0.91,  # Leave space for colorbar label
                top=0.98,  # Removed title, minimal top space
                bottom=0.04,  # Remove bottom margin
            )

        self.fig.patch.set_alpha(0.0)
        # Use theme text color instead of hardcoded white
        mpl.rcParams["text.color"] = self.palette["text"]

        self.fig.suptitle(
            "",  # No suptitle - info shown in caption below
            fontsize=self.fs_title + 2,
            x=0.5,
            y=0.98,
            fontfamily=self.theme_config.get_font_family("heading"),
            color=self.palette["text"],
        )

        # Prevent Shiny's fig.tight_layout() from corrupting GeoAxes layout
        self.fig.tight_layout = lambda *a, **kw: None

    def create(self):
        """Create the figure with maps and return figure, gridspec, and axes."""
        self.plot_projection = ccrs.PlateCarree()
        self.globe = ccrs.Globe(
            semimajor_axis=self.semmj_axis, semiminor_axis=self.semmn_axis
        )
        self.projection = ccrs.RotatedPole(
            pole_longitude=self.rotnpole_lon,
            pole_latitude=self.rotnpole_lat,
            globe=self.globe,
        )
        # Call create_axes which will create axes and add basemaps/gridlines
        return self.create_axes()

    def create_axes(self):
        # First, create the axes using the parent class
        super().create_axes()

        # Now add basemaps and gridlines to both axes
        for i, ax in enumerate([self.ax, self.ax2]):
            if not isinstance(ax, geoaxes.GeoAxesSubplot):
                raise TypeError("Expected a GeoAxesSubplot for the map axes.")

            _add_cached_basemap(
                ax,
                ocean_color=self.ocean_color,
                land_color=self.land_color,
                alpha_ocean=self.alpha_ocean,
                alpha_land=self.alpha_land,
                coastline_lw=self.coastline_lw,
            )

            proj_lon_extents, proj_lat_extents, _ = ax.projection.transform_points(
                self.plot_projection,
                np.array(self.lon_extents),
                np.array(self.lat_extents),
            ).T

            ax.set_extent([*proj_lon_extents, *proj_lat_extents])

            gl1 = ax.gridlines(
                crs=self.plot_projection,
                linewidth=self.grid_lw,
                color=self.grid_color,
                linestyle=self.grid_linestyle,
                draw_labels=True,
                x_inline=False,
                y_inline=False,
                zorder=5,
            )

            gl1.top_labels = False
            gl1.right_labels = (
                True if i == 1 else False
            )  # Right labels only on right plot
            gl1.left_labels = False
            gl1.bottom_labels = True
            gl1.ylabel_style = {
                "size": self.fs_map_label,
                "fontfamily": self.theme_config.get_font_family(
                    "mono"
                ),  # Monospace for tick labels
                "color": self.theme_config.colors["text"],  # Use theme text color
            }
            gl1.xlabel_style = {
                "size": self.fs_map_label,
                "fontfamily": self.theme_config.get_font_family(
                    "mono"
                ),  # Monospace for tick labels
                "color": self.theme_config.colors["text"],  # Use theme text color
            }

            # Apply body font to axis labels for the current axis
            ax.set_xlabel(
                ax.get_xlabel(),
                fontfamily=self.theme_config.get_font_family("body"),
                color=self.theme_config.colors["text"],
            )
            ax.set_ylabel(
                ax.get_ylabel(),
                fontfamily=self.theme_config.get_font_family("body"),
                color=self.theme_config.colors["text"],
            )

        return self.fig, self.gs, [self.ax, self.ax2]

    def pcolormesh(
        self,
        lon: np.ndarray,
        lat: np.ndarray,
        data: np.ndarray,
        ax_num: int = 0,
        cmap: str = "RdYlBu",
        vmin: float | None = None,
        vmax: float | None = None,
        **kwargs,
    ):
        """Create pcolormesh on specified axis (0 for ax, 1 for ax2)."""

        ax = self.ax if ax_num == 0 else self.ax2

        pcolormesh_obj = ax.pcolormesh(
            lon,
            lat,
            data,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            transform=self.plot_projection,
            rasterized=True,
            shading="nearest",
            antialiased=True,
            **kwargs,
        )

        # Store pcolormesh objects for both axes
        if ax_num == 0:
            self.pcolormesh_obj = pcolormesh_obj
        else:
            self.pcolormesh_obj2 = pcolormesh_obj

        return pcolormesh_obj

    def colorbar(self, colormesh, cbar_label: str = "", extend: str = "neither", horizontal: bool = None):
        """Add a styled colorbar.

        Args:
            colormesh: The mappable object
            cbar_label: Label for the colorbar
            extend: 'neither', 'both', 'min', or 'max' for colorbar ends
            horizontal: If True, create horizontal colorbar below plots.
                       If False, create vertical colorbar on right.
                       If None, use self.horizontal_cbar setting.
        """
        if self.pcolormesh_obj is None:
            raise ValueError("pcolormesh must be created before adding a colorbar.")

        # Use provided horizontal parameter or fall back to class setting
        if horizontal is None:
            horizontal = self.horizontal_cbar

        if horizontal:
            # Create horizontal colorbar below plots using GridSpec
            cbar_ax = self.fig.add_subplot(self.gs[1, :])  # Span both columns

            # Manually adjust colorbar axis to be close to plots
            # Use 85% of cell height and position at TOP of cell (closest to plots)
            pos = cbar_ax.get_position()
            new_height = pos.height * 0.85  # 85% of cell height
            new_width = pos.width * 1.0  # Full cell width
            # Center the colorbar in the cell horizontally
            new_left = pos.x0 + (pos.width - new_width) / 2
            # Position at TOP of cell (closest to plots)
            new_bottom = pos.y1 - new_height  # y1 is top of cell
            cbar_ax.set_position((new_left, new_bottom, new_width, new_height))

            self.cbar = self.fig.colorbar(
                colormesh, cax=cbar_ax, orientation="horizontal", extend=extend
            )

            # Style horizontal colorbar
            self.cbar.set_label(
                cbar_label,
                fontfamily=self.theme_config.get_font_family("mono"),
                fontsize=self.fs_map_label,
                color=self.theme_config.colors["text"],
                labelpad=10,  # Negative to place label BELOW colorbar
                rotation=0,  # Horizontal label for horizontal colorbar
            )

            # Show only labeled (white) tick labels - hide all others
            self.cbar.ax.tick_params(
                labelsize=self.fs_map_label - 2, colors=self.theme_config.colors["text"], pad=5  # Reduced pad to bring labels closer
            )

            for label in self.cbar.ax.get_xticklabels():
                label.set_fontfamily(self.theme_config.get_font_family("mono"))
                label.set_color(self.theme_config.colors["text"])
        else:
            # Create vertical colorbar on right (original behavior)
            cbar_ax = self.fig.add_subplot(self.gs[0, 2])
            pos = cbar_ax.get_position()
            shrink_factor = 0.8
            new_height = pos.height * shrink_factor
            new_bottom = pos.y0 + (pos.height - new_height) / 2
            cbar_ax.set_position((pos.x0, new_bottom, pos.width, new_height))

            self.cbar = self.fig.colorbar(
                colormesh, cax=cbar_ax, orientation="vertical", extend=extend
            )

            self.cbar.set_label(
                cbar_label,
                fontfamily=self.theme_config.get_font_family("mono"),
                fontsize=self.fs_map_label,
                color=self.theme_config.colors["text"],
                rotation=270,  # Vertical label (top to bottom)
                labelpad=20,  # Increased padding
            )

            self.cbar.ax.tick_params(
                labelsize=self.fs_map_label, colors=self.theme_config.colors["text"]
            )

            for label in self.cbar.ax.get_yticklabels():
                label.set_fontfamily(self.theme_config.get_font_family("mono"))
                label.set_color(self.theme_config.colors["text"])

        return self.cbar

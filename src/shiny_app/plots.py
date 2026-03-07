import numpy as np
import matplotlib as mpl
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
from dataclasses import dataclass, field
from matplotlib.gridspec import GridSpec
from cartopy.mpl import geoaxes
from typing import Literal, List, Optional
from theme_config import ThemeConfig

# FONT STRATEGY - Consistent with Shiny App:
# 1. BODY: Inter → axis labels, legend, tick labels
# 2. HEADING: Crimson Text → plot titles
# 3. MONO: IBM Plex Mono → grid labels, coordinate labels

@dataclass(kw_only=True)
class demo_fig:
    
    title: List[str] = field(default_factory=list)
    suptitle: str = ''
    description: str
        
    theme_config: ThemeConfig
    
    color_mode: Literal['light', 'dark'] = 'dark'
    
    dpi: int = 300
    
    fy: float = 6.7
    fx: float = 4
    
    fs_title: int = 10
    
    projection: None | ccrs.Projection = None


    def __post_init__(self):
        
        # Apply theme to matplotlib
        self.theme_config.apply_to_matplotlib()
        self.palette = self.theme_config.get_plot_palette()
        
        self.fig = plt.figure(
            figsize=(self.fx, self.fy),
            dpi=self.dpi
            )
        
        # Create GridSpec with 3 columns: plot1, plot2, colorbar
        self.gs = GridSpec(
            figure = self.fig, 
            nrows = 1,
            ncols = 3,
            width_ratios=[1, 1, 0.08],  # Two equal plots, narrow colorbar
            wspace=0.26,  # Spacing between subplots
            left=0.01,    # Remove left margin
            right=0.91,   # Leave space for colorbar label
            top=0.92,     # Remove top margin
            bottom=0.04   # Remove bottom margin
            )
        
        self.fig.patch.set_alpha(0.0)
        # Use theme text color instead of hardcoded white
        mpl.rcParams['text.color'] = self.palette['text']
        
        # Position suptitle centered over the two maps (columns 0 and 1), not including colorbar
        # With width_ratios [1, 1, 0.08] and margins (left=0.01, right=0.91):
        # Total available width = 0.91 - 0.01 = 0.90
        # Maps occupy (1+1)/(1+1+0.08) = 2/2.08 of the plotting area
        # Map width = 0.90 * (2.0/2.08) ≈ 0.865
        # Center of maps = 0.01 + 0.865/2 ≈ 0.44
        map_center_x = 0.44
        
        self.fig.suptitle(
            self.suptitle, 
            fontsize=self.fs_title + 2, 
            x=map_center_x,  # Center over maps only
            y=0.98, 
            fontfamily=self.theme_config.get_font_family('heading'), 
            color=self.palette['text'])
        
        # Disable automatic tight_layout
        #self.fig.set_tight_layout(False)
        
        
    def create_axes(self):

        
        self.ax = self.fig.add_subplot(
            self.gs[0, 0],
            projection=self.projection
            )
        
        self.ax2 = self.fig.add_subplot(
            self.gs[0, 1],
            projection=self.projection
            )
        
        for ax in [self.ax, self.ax2]:
        
            ax.spines.right.set_visible(False)
            ax.spines.top.set_visible(False)
            ax.spines.bottom.set_visible(False)
            ax.spines.left.set_visible(False)
        
        
        self.ax.set_title(
            self.title[0] if len(self.title) > 0 else '', 
            fontsize=self.fs_title, 
            y=1.01,
            fontfamily=self.theme_config.get_font_family('heading'),  # Elegant serif for titles
            fontweight=300,  # Match Shiny CSS font-weight: 400 (normal)
            color=self.theme_config.colors['text']  # Use theme text color
            )
        self.ax2.set_title(
            self.title[1] if len(self.title) > 1 else '', 
            fontsize=self.fs_title, 
            y=1.01,
            fontfamily=self.theme_config.get_font_family('heading'),  # Elegant serif for titles
            fontweight=300,  # Match Shiny CSS font-weight: 400 (normal)
            color=self.theme_config.colors['text']  # Use theme text color
            )
        # Apply text color to axis tick labels
        self.ax.tick_params(colors=self.theme_config.colors['text'])
        self.ax2.tick_params(colors=self.theme_config.colors['text'])
        
        return self.fig, self.gs, [self.ax, self.ax2]
    
    def save(self, path: str):
        self.fig.savefig(path, 
            dpi=self.dpi,
            bbox_inches='tight', 
            pad_inches=0.1
            )


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
    
    ocean_color: str = '#a6cee3'
    land_color: str = '#636363'
    alpha_ocean: float = 0.8
    alpha_land: float = 0.8
    
    coastline_lw: float = 0.8
    grid_lw: float = 0.8
    grid_color: str = 'grey'
    grid_linestyle: str = '--'
    
    fs_map_label: int = 4
    
    # For efficient pcolormesh updates
    pcolormesh_obj: Optional[object] = field(default=None, init=False, repr=False)
    pcolormesh_obj2: Optional[object] = field(default=None, init=False, repr=False)
    
    def create(self):
        
        self.plot_projection = ccrs.PlateCarree()

        self.globe = ccrs.Globe(
            semimajor_axis=self.semmj_axis,
            semiminor_axis=self.semmn_axis
            )

        self.projection = ccrs.RotatedPole(
            pole_longitude=self.rotnpole_lon,
            pole_latitude=self.rotnpole_lat,
            globe=self.globe
            )

        super().create_axes()
        
        for i, ax in enumerate([self.ax, self.ax2]):
        
            if not isinstance(ax, geoaxes.GeoAxesSubplot):
                raise TypeError("Expected a GeoAxesSubplot for the map axes.")
        

            ax.add_feature(
                cfeature.OCEAN,
                color=self.ocean_color, 
                alpha=self.alpha_ocean, 
                zorder=0
                )
    
            ax.add_feature(
                cfeature.LAND,
                color=self.land_color, 
                alpha=self.alpha_land, 
                zorder=0
                )
    
            ax.coastlines(linewidth=self.coastline_lw, zorder=2)
        
            proj_lon_extents, proj_lat_extents, _ = ax.projection.transform_points(
                self.plot_projection,
                np.array(self.lon_extents),
                np.array(self.lat_extents)
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
                zorder=5
                )
        
            gl1.top_labels = False
            gl1.right_labels = True if i == 1 else False  # Right labels only on right plot
            gl1.left_labels = False
            gl1.bottom_labels = True
            gl1.ylabel_style = {
                'size': self.fs_map_label,
                'fontfamily': self.theme_config.get_font_family('mono'),  # Monospace for tick labels
                'color': self.theme_config.colors['text']  # Use theme text color
            }
            gl1.xlabel_style = {
                'size': self.fs_map_label,
                'fontfamily': self.theme_config.get_font_family('mono'),  # Monospace for tick labels
                'color': self.theme_config.colors['text']  # Use theme text color
            }
        
            # Apply body font to axis labels
            self.ax.set_xlabel(
                self.ax.get_xlabel(),
                fontfamily=self.theme_config.get_font_family('body'),
                color=self.theme_config.colors['text']
            )
            self.ax.set_ylabel(
                self.ax.get_ylabel(),
                fontfamily=self.theme_config.get_font_family('body'),
                color=self.theme_config.colors['text']
            )

        return self.fig, self.gs, [self.ax, self.ax2]
        
    def pcolormesh(
        self, 
        lon: np.ndarray, 
        lat: np.ndarray, 
        data: np.ndarray, 
        ax_num: int = 0,
        cmap: str = 'RdYlBu', 
        vmin: float | None = None, 
        vmax: float | None = None,
        **kwargs):
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
            shading='nearest',
            antialiased=True,
            **kwargs
        )
        
        # Store pcolormesh objects for both axes
        if ax_num == 0:
            self.pcolormesh_obj = pcolormesh_obj
        else:
            self.pcolormesh_obj2 = pcolormesh_obj
            
        return pcolormesh_obj
        
    def colorbar(self, 
        colormesh,
        cbar_label: str = '',
        extend: str = 'neither'):
        """Add a styled colorbar on the right of both plots."""
        
        if self.pcolormesh_obj is None:
            raise ValueError("pcolormesh must be created before adding a colorbar.")
        
        # Create colorbar in the third GridSpec column (avoids Shiny layout issues)
        cbar_ax = self.fig.add_subplot(self.gs[0, 2])
        
        # Manually adjust colorbar axis height to match map plots
        # Get current position [left, bottom, width, height]
        pos = cbar_ax.get_position()
        shrink_factor = 0.8  # Reduce to 80% of current height
        new_height = pos.height * shrink_factor
        # Center vertically
        new_bottom = pos.y0 + (pos.height - new_height) / 2
        
        cbar_ax.set_position((pos.x0, new_bottom, pos.width, new_height))
        
        # Create colorbar in the dedicated axis
        self.cbar = self.fig.colorbar(
            colormesh, 
            cax=cbar_ax,
            orientation='vertical',
            extend=extend
        )
        
        # Style colorbar to match theme
        # Colorbar label font (mono font for data labels)
        self.cbar.set_label(
            cbar_label,
            fontfamily=self.theme_config.get_font_family('mono'),
            fontsize=self.fs_map_label,
            color=self.theme_config.colors['text']
        )
        
        # Colorbar tick labels font
        self.cbar.ax.tick_params(
            labelsize=self.fs_map_label,
            colors=self.theme_config.colors['text']
        )
        
        # Apply font family to tick labels
        for label in self.cbar.ax.get_yticklabels():
            label.set_fontfamily(self.theme_config.get_font_family('mono'))
            label.set_color(self.theme_config.colors['text'])
        
        return self.cbar

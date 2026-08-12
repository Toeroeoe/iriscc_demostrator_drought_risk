"""
Test app 2: Matches main app structure (no card wrapper, nav_panel style).
"""

from shiny import App, render, ui
import matplotlib.pyplot as plt

def server(input, output, session) -> None:
    
    @render.plot
    def test_map():
        fig, ax = plt.subplots(figsize=(10, 7.5))
        fig.patch.set_facecolor('#1a1a1a')
        ax.set_facecolor('#1a1a1a')
        
        # Horizontal colorbar layout (like SMI mean/min)
        gs = fig.add_gridspec(2, 2, height_ratios=[1, 0.06], hspace=0.0, bottom=0.05)
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])
        ax_cbar = fig.add_subplot(gs[1, :])
        
        # Two maps
        ax1.text(0.5, 0.5, 'CLM5', ha='center', va='center', fontsize=20, color='white')
        ax2.text(0.5, 0.5, 'mHM', ha='center', va='center', fontsize=20, color='white')
        ax1.axis('off')
        ax2.axis('off')
        
        # Horizontal colorbar
        ax_cbar.set_facecolor('#1a1a1a')
        ax_cbar.text(0.5, 0.5, 'Colorbar', ha='center', va='center', fontsize=14, color='white')
        ax_cbar.axis('off')
        
        return fig
    
    @render.ui
    def test_caption():
        return ui.div(
            "This is a caption test WITHOUT card wrapper.",
            style="color: #aaa; font-size: 12px; line-height: 1.5;"
        )

app_ui = ui.page_fluid(
    ui.h1("Layout Test App 2 - No Card Wrapper"),
    ui.navset_card_pill(
        ui.nav_panel(
            "Test Tab",
            ui.output_plot("test_map", height="800px"),
            ui.output_ui("test_caption"),
        ),
        id="test_tab"
    ),
    style="padding: 20px;"
)

app = App(app_ui, server)

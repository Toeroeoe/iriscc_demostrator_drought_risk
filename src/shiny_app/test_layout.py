"""
Minimal test app to debug matplotlib figure rendering and spacing in Shiny.
This isolates the layout issue from the full app complexity.
"""

from shiny import App, render, ui
import matplotlib.pyplot as plt
import tempfile
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
print(f"Temp directory: {tempfile.gettempdir()}")

def server(input, output, session) -> None:
    """Simple server with one plot and one caption."""
    
    @render.plot
    def test_map():
        """Create a simple map-like figure."""
        fig, ax = plt.subplots(figsize=(4, 6))
        fig.patch.set_facecolor('#1a1a1a')
        ax.set_facecolor('#1a1a1a')
        
        # Simple test content
        ax.text(0.5, 0.5, 'Test Map', ha='center', va='center', 
                fontsize=20, color='white')
        ax.axis('off')
        
        return fig
    
    @render.ui
    def test_caption():
        """Caption below the plot."""
        return ui.div(
            "This is a test caption. Notice the spacing above and below.",
            style="color: #aaa; font-size: 12px; line-height: 1.5;"
        )

app_ui = ui.page_fluid(
    ui.head_content(
        ui.tags.style("""
            /* Debug CSS to see element boundaries */
            .shiny-output-container {
                border: 1px dashed red !important;
            }
        """)
    ),
    ui.h1("Layout Test App - Step 1: Default Spacing"),
    ui.card(
        ui.output_plot("test_map", height="400px"),
        ui.output_ui("test_caption"),
        style="padding: 10px;"
    ),
    style="background-color: #f8f9fa; min-height: 100vh;"
)

app = App(app_ui, server)

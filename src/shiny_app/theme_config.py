"""Theme management for consistent styling across Shiny and Matplotlib.

FONT STRATEGY (Maximum 3 fonts - consistent across app and plots):
═════════════════════════════════════════════════════════════════

1. BODY FONT: Inter (Clean Sans-Serif)
   - Usage: Regular text, axis labels, form inputs, legend
   - Shiny: body, .form-label, .shiny-input-label
   - Matplotlib: axis labels, legend, tick labels (14px base)

2. HEADING FONT: Crimson Text (Elegant Serif)
   - Usage: Page titles, section headers, plot titles
   - Shiny: h1, h2, h3, h4, h5, h6
   - Matplotlib: plot titles (20px)

3. MONOSPACE FONT: IBM Plex Mono (Technical Data)
   - Usage: Code blocks, data values, coordinate labels
   - Shiny: code, pre blocks
   - Matplotlib: grid labels, coordinate labels (12px)

TEXT COLOR: Theme's text color (light gray #eeeeee for dark mode)
─────────────────────────────────────────────────────────────────
Applied to all text elements in both Shiny and Matplotlib.
"""

from shinyswatch import theme
from typing import Literal, Dict, Any
import matplotlib as mpl
from matplotlib import font_manager as fm
import matplotlib.pyplot as plt
from pathlib import Path

# Access theme objects
DARK_THEME = theme.darkly
LIGHT_THEME = theme.flatly

# Font registration
def _register_custom_fonts():
    """Register custom fonts with matplotlib font manager."""
    # Get path to fonts directory (relative to this file)
    fonts_dir = Path(__file__).parent.parent.parent / 'fonts'
    
    # Register Inter fonts (OTF and TTF)
    inter_dir = fonts_dir / 'Inter'
    for font_file in list(inter_dir.glob('*.ttf')) + list(inter_dir.glob('*.otf')):
        fm.fontManager.addfont(str(font_file))
    
    # Register Crimson Text fonts
    crimson_dir = fonts_dir / 'CrimsonText'
    for font_file in crimson_dir.glob('*.ttf'):
        fm.fontManager.addfont(str(font_file))
    
    # Register IBM Plex Mono fonts
    ibm_dir = fonts_dir / 'IBMPlexMono'
    for font_file in ibm_dir.glob('*.ttf'):
        fm.fontManager.addfont(str(font_file))

# Register fonts on module import
_register_custom_fonts()

# Google Fonts imports - add to HTML head
GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Inter:wght@300;400;500;600;700&"
    "family=Crimson+Text:ital,wght@0,400;0,600;1,400&"
    "family=IBM+Plex+Mono:wght@400;500;600&"
    "display=swap"
)


class ThemeConfig:
    """Extract and manage theme configuration for both Shiny and Matplotlib."""
    
    def __init__(self, theme_mode: Literal['dark', 'light'] = 'light'):
        self.mode = theme_mode
        self.theme_obj = DARK_THEME if theme_mode == 'dark' else LIGHT_THEME
        self._extract_theme_values()
    
    def _extract_theme_values(self):
        """Extract colors, fonts, and sizes from the shinyswatch theme object."""
        
        # Access theme attributes - shinyswatch themes have these CSS variables
        theme_data = self.theme_obj
        
        # Color extraction - use appropriate defaults for dark vs light mode
        if self.mode == 'dark':
            # Dark theme defaults (darkly)
            self.colors = {
                'primary': self._get_css_var('--bs-primary', '#375a7f'),  # Dark blue
                'secondary': self._get_css_var('--bs-secondary', '#444444'),  # Gray
                'text': self._get_css_var('--bs-body-color', '#eeeeee'),  # Light gray/white for dark mode
                'background': self._get_css_var('--bs-body-bg', '#222222'),  # Dark background
                'border': self._get_css_var('--bs-border-color', '#444444'),  # Medium gray
                'success': self._get_css_var('--bs-success', '#5cb85c'),
                'danger': self._get_css_var('--bs-danger', '#d9534f'),
                'warning': self._get_css_var('--bs-warning', '#f0ad4e'),
                'info': self._get_css_var('--bs-info', '#46b8da'),
            }
        else:
            # Light theme defaults (flatly)
            self.colors = {
                'primary': self._get_css_var('--bs-primary', '#2ecc71'),  # Green
                'secondary': self._get_css_var('--bs-secondary', '#95a5a6'),  # Gray
                'text': self._get_css_var('--bs-body-color', '#2c3e50'),  # Dark text for light mode
                'background': self._get_css_var('--bs-body-bg', '#ffffff'),  # White background
                'border': self._get_css_var('--bs-border-color', '#ecf0f1'),  # Light gray
                'success': self._get_css_var('--bs-success', '#27ae60'),
                'danger': self._get_css_var('--bs-danger', '#e74c3c'),
                'warning': self._get_css_var('--bs-warning', '#f39c12'),
                'info': self._get_css_var('--bs-info', '#3498db'),
            }
        
        # Font configuration - three custom fonts
        self.fonts = {
            'body': 'Inter, system-ui, -apple-system, sans-serif',  # Clean sans-serif for body text
            'heading': 'Crimson Text, serif',  # Elegant serif for headings/titles
            'mono': 'IBM Plex Mono, monospace',  # Professional monospace for data/labels
        }
        
        # Font sizes (Bootstrap defaults)
        self.font_sizes = {
            'small': 12,
            'base': 14,
            'large': 16,
            'title': 20,
            'heading': 24,
        }

    def _get_css_var(self, var_name: str, default: str) -> str:
        """Get CSS variable value from theme, with fallback to default."""
        if hasattr(self.theme_obj, f'get_{var_name}'):
            return getattr(self.theme_obj, f'get_{var_name}')()
        return default
    
    def apply_to_matplotlib(self):
        """Apply theme colors and fonts to matplotlib default settings."""
        
        # Set text color
        mpl.rcParams['text.color'] = self.colors['text']
        
        # Use our custom fonts with system fallbacks (only fonts that exist)
        mpl.rcParams['font.sans-serif'] = ['Inter', 'DejaVu Sans', 'sans-serif']
        mpl.rcParams['font.serif'] = ['Crimson Text', 'DejaVu Serif', 'serif']
        mpl.rcParams['font.monospace'] = ['IBM Plex Mono', 'DejaVu Sans Mono', 'monospace']
        mpl.rcParams['font.family'] = 'sans-serif'  # Body default to sans-serif
        
        # Set font sizes
        mpl.rcParams['font.size'] = self.font_sizes['base']
        mpl.rcParams['legend.fontsize'] = self.font_sizes['small']
        mpl.rcParams['xtick.labelsize'] = self.font_sizes['small']
        mpl.rcParams['ytick.labelsize'] = self.font_sizes['small']
        mpl.rcParams['axes.labelsize'] = self.font_sizes['base']
        mpl.rcParams['axes.titlesize'] = self.font_sizes['title']
        
        # Set axes/spines colors
        mpl.rcParams['axes.edgecolor'] = self.colors['border']
        mpl.rcParams['axes.labelcolor'] = self.colors['text']
        
        # Set grid
        mpl.rcParams['grid.color'] = self.colors['border']
        mpl.rcParams['grid.alpha'] = 0.3
        
        # Set figure background
        mpl.rcParams['figure.facecolor'] = self.colors['background']
        mpl.rcParams['axes.facecolor'] = self.colors['background']
    
    def _extract_font_family(self, font_string: str) -> list:
        """Parse font-family string and return list of fonts."""
        fonts = [f.strip().strip("'\"") for f in font_string.split(',')]
        return fonts
    
    def get_font_family(self, font_type: Literal['body', 'heading', 'mono'] = 'body') -> list:
        """Get font family as a list for matplotlib.
        
        Args:
            font_type: 'body' (clean sans-serif), 'heading' (elegant serif), 
                      'mono' (monospace for data)
        
        Returns:
            List of font families with fallbacks
        """
        if font_type == 'heading':
            # For headings/titles, use Crimson Text
            return ['Crimson Text', 'DejaVu Serif', 'serif']
        elif font_type == 'mono':
            # For code/monospace, use IBM Plex Mono
            return ['IBM Plex Mono', 'DejaVu Sans Mono', 'monospace']
        else:
            # For body/labels, use Inter
            return ['Inter', 'DejaVu Sans', 'sans-serif']
    
    def get_font_usage_guide(self) -> Dict[str, Dict[str, str]]:
        """Return a guide for consistent font usage across Shiny and Matplotlib.
        
        Returns:
            Dict with font usage rules for different elements
        """
        return {
            'body': {
                'font': self.fonts['body'],
                'size': str(self.font_sizes['base']),
                'usage': 'Body text, axis labels, legend',
                'shiny': 'body, input labels, cards text',
                'matplotlib': 'axis labels, legend, tick labels'
            },
            'heading': {
                'font': self.fonts['heading'],
                'size': str(self.font_sizes['title']),
                'usage': 'Page titles, plot titles, section headers',
                'shiny': 'h1, h2, h3, h4, h5, h6',
                'matplotlib': 'plot titles, set_title() calls'
            },
            'mono': {
                'font': self.fonts['mono'],
                'size': str(self.font_sizes['small']),
                'usage': 'Code, data values, numeric labels',
                'shiny': 'code, pre blocks',
                'matplotlib': 'grid labels, tick labels for data'
            }
        }
    
    def __repr__(self) -> str:
        return (
            f"ThemeConfig(mode='{self.mode}', "
            f"text_color='{self.colors['text']}', "
            f"bg_color='{self.colors['background']}')"
        )
    
    def get_plot_palette(self) -> Dict[str, str]:
        """Return a color palette suitable for plots."""
        if self.mode == 'dark':
            self.palette = {
                'background': self.colors['background'],
                'text': self.colors['text'],
                'grid': self.colors['border'],
                'primary': self.colors['primary'],
                'accent': self.colors['info'],
            }
            return self.palette
        else:
            self.palette = {
                'background': self.colors['background'],
                'text': self.colors['text'],
                'grid': self.colors['border'],
                'primary': self.colors['primary'],
                'accent': self.colors['success'],
            }
            return self.palette


def get_theme_config(theme_mode: Literal['dark', 'light'] = 'light') -> ThemeConfig:
    """Factory function to get theme configuration."""
    return ThemeConfig(theme_mode)

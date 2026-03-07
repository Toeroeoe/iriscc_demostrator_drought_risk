"""Test script to verify custom fonts are working in matplotlib."""

import matplotlib.pyplot as plt
from src.shiny_app.theme_config import ThemeConfig

# Create theme config and apply to matplotlib
theme = ThemeConfig('dark')
theme.apply_to_matplotlib()

# Create a test plot
fig, ax = plt.subplots(figsize=(10, 6))

# Set dark background
fig.patch.set_facecolor(theme.colors['background'])
ax.set_facecolor(theme.colors['background'])

# Add sample data
x = [1, 2, 3, 4, 5]
y = [2, 4, 3, 5, 4]
ax.plot(x, y, color=theme.colors['primary'], linewidth=2)

# Add title with heading font (Crimson Text)
ax.set_title('Test Plot with Custom Fonts', 
             fontfamily=theme.get_font_family('heading'),
             fontsize=theme.font_sizes['title'],
             fontweight=600,
             color=theme.colors['text'])

# Add labels with body font (Inter)
ax.set_xlabel('X Axis Label (Inter font)', 
              fontfamily=theme.get_font_family('body'),
              fontsize=theme.font_sizes['base'],
              color=theme.colors['text'])

ax.set_ylabel('Y Axis Label (Inter font)', 
              fontfamily=theme.get_font_family('body'),
              fontsize=theme.font_sizes['base'],
              color=theme.colors['text'])

# Add grid
ax.grid(True, alpha=0.3, color=theme.colors['border'])

# Customize spines
for spine in ax.spines.values():
    spine.set_edgecolor(theme.colors['border'])
    spine.set_linewidth(0.5)

# Add text annotation with mono font (IBM Plex Mono)
ax.text(3, 2.5, 'Data point: (3, 3)', 
        fontfamily=theme.get_font_family('mono'),
        fontsize=theme.font_sizes['small'],
        color=theme.colors['text'],
        bbox=dict(boxstyle='round', facecolor=theme.colors['background'], 
                  edgecolor=theme.colors['border'], alpha=0.8))

# Add legend
ax.legend(['Sample Data'], 
          fontsize=theme.font_sizes['small'],
          facecolor=theme.colors['background'],
          edgecolor=theme.colors['border'])

plt.tight_layout()
plt.savefig('test_fonts_output.png', dpi=150, facecolor=theme.colors['background'])
print(f"Test plot saved to test_fonts_output.png")
print(f"\nFont configuration:")
print(f"  Title (heading): {theme.get_font_family('heading')[0]}")
print(f"  Labels (body): {theme.get_font_family('body')[0]}")
print(f"  Data text (mono): {theme.get_font_family('mono')[0]}")

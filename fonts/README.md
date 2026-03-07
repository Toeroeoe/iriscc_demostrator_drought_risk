# Custom Fonts for IRISCC Demonstrator

This directory contains the custom fonts used throughout the application for consistent typography in both the Shiny UI and matplotlib visualizations.

## Fonts Included

### 1. Inter (Sans-Serif)
- **License**: SIL Open Font License 1.1
- **Source**: https://github.com/rsms/inter
- **Usage**: Body text, axis labels, form inputs, legend
- **Files**: `Inter/Inter-Regular.otf`, `Inter-Bold.otf`, `Inter-Italic.otf`, `Inter-BoldItalic.otf`

### 2. Crimson Text (Serif)
- **License**: SIL Open Font License 1.1
- **Source**: https://github.com/google/fonts/tree/main/ofl/crimsontext
- **Usage**: Page titles, section headers, plot titles
- **Files**: `CrimsonText/*.ttf`

### 3. IBM Plex Mono (Monospace)
- **License**: SIL Open Font License 1.1
- **Source**: https://github.com/IBM/plex
- **Usage**: Code blocks, data values, coordinate labels
- **Files**: `IBMPlexMono/*.ttf`

## Font Registration

The fonts are automatically registered with matplotlib's font manager when the `theme_config` module is imported. This ensures that both the Shiny UI (browser-rendered) and matplotlib plots (backend-rendered) use identical fonts.

## Adding New Fonts

To add a new font:
1. Download the font files (`.ttf` or `.otf`)
2. Place them in a subdirectory under `fonts/`
3. Update `src/shiny_app/theme_config.py` to register the new fonts
4. Update the font family lists in `ThemeConfig.get_font_family()`

## License

All fonts in this directory are released under the SIL Open Font License 1.1, which allows:
- Free commercial and non-commercial use
- Bundling with applications
- Modification and redistribution
- No separate license fees

See individual font directories for specific license files.

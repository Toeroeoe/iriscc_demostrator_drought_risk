# R Integration for Drought Hydrograph

## Overview

This directory contains the R script for generating drought hydrograph visualizations. The script has been adapted for integration with the IRISCC Shiny app.

## Files

- `drought_hydrograph.R` - Original R script (unchanged)
- `drought_hydrograph_shiny.R` - Modified version for Shiny integration
- `../src/shiny_app/drought_hydrograph_r.py` - Python helper for R integration
- `../src/shiny_app/app.py` - Updated with R integration

## Requirements

### R Installation

R must be installed on your system. Check with:
```bash
R --version
```

### Required R Packages

The following R packages must be installed:
```R
install.packages(c("ggplot2", "patchwork", "scales", "xts", "zoo"))
```

### Required Fonts

The app uses custom fonts that should be installed on your system:
- **Inter** (body text)
- **Crimson Text** (titles)
- **IBM Plex Mono** (numeric labels)

### Python Package

**rpy2** is required for R-Python integration:
```bash
pip install rpy2
```

If you're using the virtual environment in this project:
```bash
cd src/shiny_app
source .venv/bin/activate
pip install rpy2
```

> **Note**: If `rpy2` cannot be installed (e.g., network restrictions), the app will gracefully fall back to showing the standard discharge time series plot with a message explaining how to enable the R-based visualization.

## Installation Steps

1. **Install R packages** (run in R or RStudio):
   ```R
   install.packages(c("ggplot2", "patchwork", "scales", "xts", "zoo"))
   ```

2. **Install rpy2** (run in terminal):
   ```bash
   pip install rpy2
   ```

3. **Restart the Shiny app**

4. **Test**: Click on a gauge marker in the Hydrological tab. If installed correctly, you should see the three-panel drought hydrograph.

## Verification

Check if rpy2 is installed:
```bash
python -c "import rpy2; print('rpy2 version:', rpy2.__version__)"
```

Check if R packages are available:
```R
library(ggplot2)
library(patchwork)
library(scales)
library(xts)
library(zoo)
cat("All packages loaded successfully\n")
```

## Changes to R Script

The `drought_hydrograph_shiny.R` file includes these modifications:

1. **Fonts**: Changed to match the app's theme
   - Inter (body text)
   - Crimson Text (titles)
   - IBM Plex Mono (numeric labels)

2. **Colors**: Kept original but adjusted axis color to `#eeeeee` for dark theme compatibility

3. **New Helper Functions**:
   - `drought_hydrograph_shiny()` - Reads from NetCDF and creates plot
   - `drought_hydrograph_from_xts()` - Takes pre-loaded xts objects

## Python Integration

The `drought_hydrograph_r.py` module provides:

- `create_drought_hydrograph_image()` - Main function to generate plot and return image data
- `drought_hydrograph_r_available()` - Check if R integration is available

### Usage in Shiny App

The integration is automatically activated in `app.py` when `drought_hydrograph_r.py` is available:

1. When a user clicks on a gauge in the Hydrological tab:
   - If R is available: Shows the drought hydrograph (three-panel plot)
   - If R is not available: Falls back to the standard discharge time series plot with a message

2. The plot shows:
   - Main panel: Decadal monthly hydrograph with 10-yr and 50-yr return period drought bands
   - Left inset: Total drought event counts (decadal)
   - Right inset: Monthly drought event counts

3. Parameters:
   - `decade`: Selected via the app's decade slider
   - `persistence`: Fixed at 1 month (consecutive months below threshold)

## Customization

To modify the plot appearance:

1. Edit `drought_hydrograph_shiny.R`:
   - Change fonts in the `FONT`, `FONT_TITLE`, `FONT_MONO` variables
   - Adjust colors in `col_q`, `col_10yr`, `col_50yr`, `col_axis`
   - Modify font sizes in `FS_AXTEXT`, `FS_AXTITLE`, etc.

2. To add persistence control:
   - Add a UI input slider in the Hydrological panel
   - Pass `input.persistence()` to `create_drought_hydrograph_image()`

## Troubleshooting

### "R not available" message

If you see the discharge plot with a message about R not being available:

1. Check if rpy2 is installed: `python -c "import rpy2"`
2. Install it: `pip install rpy2`
3. Restart the app

### Font errors

If R cannot find the fonts, the plot will still render but with default fonts. Ensure the fonts are installed on the system:

```bash
# Check if fonts are available
fc-list | grep -i "inter"
fc-list | grep -i "crimson"
fc-list | grep -i "ibm plex"
```

### Missing R packages

Install missing R packages:
```R
install.packages("ggplot2")
install.packages("patchwork")
install.packages("scales")
install.packages("xts")
install.packages("zoo")
```

### R library path issues

If R cannot find packages, check the library path:
```R
.libPaths()
```

You may need to install packages to a specific library path.

### Python virtual environment

If using a virtual environment, ensure rpy2 is installed in the correct environment:
```bash
# Check which Python you're using
which python
python --version

# Activate the venv if needed
cd src/shiny_app
source .venv/bin/activate

# Install rpy2
pip install rpy2
```

## Testing

After installation, test the integration:

1. Start the app:
   ```bash
   cd src/shiny_app
   python -m shiny run app.py
   ```

2. Navigate to the **Hydrological** tab

3. Click on any gauge marker on the map

4. You should see the three-panel drought hydrograph above the simple discharge plot

## Current Limitations

1. **Persistence parameter**: Fixed at 1 month (no UI control yet)
2. **Observed data only**: Uses only observed discharge for drought analysis
3. **Decade selection**: Uses app's slider value

## Next Steps (Optional)

1. Add persistence slider to UI
2. Add both observed and simulated to drought analysis
3. Cache generated plots for faster subsequent loads
4. Add export functionality (PNG/PDF download)
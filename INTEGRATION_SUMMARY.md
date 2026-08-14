# Drought Hydrograph Integration - Summary

## What was implemented

### 1. R Script Modification
**File**: `data/streamflow/drought_hydrograph_shiny.R` (copy of original)

Changes made:
- Fonts updated to match app's theme (Inter, Crimson Text, IBM Plex Mono)
- Colors kept original for visual consistency
- Added two new helper functions:
  - `drought_hydrograph_shiny()` - Reads from NetCDF, generates plot
  - `drought_hydrograph_from_xts()` - Takes pre-loaded xts objects

### 2. Python Integration Module
**File**: `src/shiny_app/drought_hydrograph_r.py`

Provides:
- `create_drought_hydrograph_image()` - Main function to generate drought hydrograph
- `drought_hydrograph_r_available()` - Check R availability
- Automatic conversion from pandas to R xts objects
- Error handling with fallback to None

### 3. Shiny App Updates
**File**: `src/shiny_app/app.py`

Changes:
- Added R import with fallback for when rpy2 is not available
- Added `drought_hydrograph()` render function
- Added `drought_hydrograph_container()` to dynamically show either image or plot
- Updated Hydrological panel description

### 4. Documentation
**File**: `data/streamflow/README_R_INTEGRATION.md`

Comprehensive documentation for:
- Overview of integration
- Required packages
- Usage instructions
- Customization guide
- Troubleshooting

## How It Works

```
User clicks gauge → selected_gauge set → drought_hydrograph_container() renders
    ↓
If R_AVAILABLE:
    drought_hydrograph() → drought_hydrograph_r.py → R script
    ↓
R generates 3-panel plot (hydrograph + 2 insets) → saves PNG
    ↓
Python reads PNG → returns as ImgData to Shiny
    ↓
Image displayed in UI
```

## What the Plot Shows

1. **Main Panel**: Decadal monthly hydrograph with:
   - Blue line: Monthly mean discharge
   - Orange band: 10-yr return period drought (0.10 quantile)
   - Dark orange band: 50-yr return period drought (0.02 quantile)
   - Overlay: 22% of the decade was in drought

2. **Left Inset**: Total drought event counts
   - Q10 only: Months below 10-yr but not 50-yr threshold
   - Q50: Months below 50-yr threshold

3. **Right Inset**: Monthly drought counts
   - Jan-Dec distribution of drought events

## Dependencies

**Required Python packages:**
- `rpy2` (for R integration)

**Required R packages:**
- ggplot2
- patchwork
- scales
- xts
- zoo

**Required fonts (system):**
- Inter
- Crimson Text
- IBM Plex Mono

## Current Limitations

1. **Persistence parameter**: Fixed at 1 month (no UI control yet)
2. **Decade selection**: Uses app's slider value
3. **Fallback behavior**: Shows empty image when R unavailable (could show discharge_plot instead)
4. **Observed data only**: Uses only observed discharge for drought analysis

## Next Steps (Optional)

1. Add persistence slider to UI
2. Improve fallback to show discharge_plot when R unavailable
3. Add both observed and simulated to drought analysis
4. Cache generated plots for faster subsequent loads
5. Add export functionality (PNG/PDF download)

## Testing

To test the integration:

1. Install R dependencies:
```R
install.packages(c("ggplot2", "patchwork", "scales", "xts", "zoo"))
```

2. Install Python dependencies:
```bash
pip install rpy2
```

3. Run the app:
```bash
cd src/shiny_app
python -m shiny run app.py
```

4. Navigate to Hydrological tab and click on a gauge marker
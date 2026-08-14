"""Integration helpers for R-based drought hydrograph plotting.

This module provides Python wrappers around the R script `drought_hydrograph_shiny.R`
to generate drought hydrograph plots from discharge data.

Usage in app.py:
    from drought_hydrograph_r import create_drought_hydrograph_image
    
    @render.image
    def drought_hydrograph():
        try:
            gauge_id = input.selected_gauge()
        except Exception:
            return None
        if not gauge_id:
            return None
        
        return create_drought_hydrograph_image(gauge_id, input.dec().year)
"""

import os
import tempfile
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd
from matplotlib import image as mpimg

# R integration via rpy2
try:
    import rpy2.robjects as ro
    from rpy2.robjects.packages import importr
    from rpy2.robjects import conversion
    from rpy2.robjects.conversion import overlay_converter
    
    # Create a converter that handles pandas data frames
    import pandas as pd
    import numpy as np
    
    R_AVAILABLE = True
except ImportError:
    R_AVAILABLE = False
    print("Warning: rpy2 not installed. R integration will be disabled.")

# Path to the R script (go up from shiny_app to project root, then to data/streamflow)
R_SCRIPT_PATH = Path(__file__).parent.parent.parent / "data" / "streamflow" / "drought_hydrograph_shiny.R"


def _init_r():
    """Initialize R and load the drought hydrograph script.
    
    Returns:
        bool: True if R initialization succeeded, False otherwise
    """
    if not R_AVAILABLE:
        return False
    
    try:
        # Import required R packages
        # Note: Use on_conflict="warn" for packages with symbol conflicts (like xts)
        ggplot2 = importr('ggplot2', robject_translations={'plot_annotation': 'plot_annotation_'})
        patchwork = importr('patchwork', robject_translations={'plot_annotation': 'plot_annotation_'})
        scales_pkg = importr('scales')
        xts = importr('xts', on_conflict="warn")  # Handle symbol conflicts
        zoo_pkg = importr('zoo')
        
        # Source the R script
        if R_SCRIPT_PATH.exists():
            ro.r.source(str(R_SCRIPT_PATH))
        else:
            print(f"Warning: R script not found at {R_SCRIPT_PATH}")
            return False
        
        return True
    except Exception as e:
        print(f"Error initializing R: {e}")
        import traceback
        traceback.print_exc()
        return False


def _get_gauge_metadata(gauge_id: str):
    """Get metadata for a gauge from the gauge_meta DataFrame.
    
    Args:
        gauge_id: Zero-padded 10-digit gauge ID
        
    Returns:
        dict with station metadata or None if not found
    """
    from shared import gauge_meta
    
    row = gauge_meta.loc[gauge_meta["gauge_id"] == gauge_id]
    if row.empty:
        return None
    
    r = row.iloc[0]
    return {
        "name": str(r["station"]),
        "river": str(r["river"]),
        "country": str(r["country"]),
        "area": "N/A"  # Not available in current metadata
    }


def _load_monthly_discharge(gauge_id: str):
    """Load and aggregate daily discharge to monthly for a gauge.
    
    Args:
        gauge_id: Zero-padded 10-digit gauge ID
        
    Returns:
        tuple: (monthly_obs_xts, monthly_sim_xts) as xts objects, or (None, None)
    """
    from shared import get_gauge_discharge, discharge_time
    
    qobs, qsim = get_gauge_discharge(gauge_id)
    if qobs is None and qsim is None:
        return None, None
    
    # Aggregate daily → monthly means
    if qobs is not None:
        qobs_series = pd.Series(qobs, index=discharge_time)
        qobs_monthly = qobs_series.resample("ME").mean()
        qobs_monthly = qobs_monthly.dropna()
    else:
        qobs_monthly = None
    
    if qsim is not None:
        qsim_series = pd.Series(qsim, index=discharge_time)
        qsim_monthly = qsim_series.resample("ME").mean()
        qsim_monthly = qsim_monthly.dropna()
    else:
        qsim_monthly = None
    
    return qobs_monthly, qsim_monthly


def create_drought_hydrograph_image(gauge_id: str, decade_year: int, persistence: int = 1):
    """Create a drought hydrograph plot for a gauge and return as image data.
    
    Args:
        gauge_id: Zero-padded 10-digit gauge ID
        decade_year: Starting year of the decade (e.g., 1960 for 1960-1969)
        persistence: Minimum consecutive months below threshold (default: 1)
        
    Returns:
        dict: Image data for Shiny's render.image, or None if error
    """
    if not _init_r():
        # R not available, return placeholder
        return None
    
    try:
        # Get gauge metadata
        metadata = _get_gauge_metadata(gauge_id)
        if metadata is None:
            return None
        
        # Load monthly discharge data
        qobs_monthly, qsim_monthly = _load_monthly_discharge(gauge_id)
        if qobs_monthly is None or len(qobs_monthly) == 0:
            return None
        
        # Create decade range
        decade_years = list(range(decade_year, decade_year + 10))
        
        # Create temporary directory for output
        with tempfile.TemporaryDirectory() as tmpdir:
            # Convert dates to character vector and values to numeric vector
            dates_vec = ro.StrVector([str(d) for d in qobs_monthly.index])
            values_vec = ro.FloatVector(qobs_monthly.values)
            
            # Call the new R function that creates xts internally
            r_func = ro.r['drought_hydrograph_from_dates']
            
            # Prepare arguments
            output_file = os.path.join(tmpdir, f"drought_{gauge_id}_{decade_year}.png")
            
            # Call R function with dates and values as separate vectors
            result = r_func(
                dates_vec,
                values_vec,
                gauge_id,
                metadata["name"],
                metadata["river"],
                metadata["country"],
                metadata["area"],
                decade_years=ro.IntVector(decade_years),
                persistence=persistence,
                output_dir=tmpdir,
                filename=output_file
            )
            
            # Read the generated image
            if os.path.exists(output_file):
                img = mpimg.imread(output_file)
                
                # Convert to Shiny image format
                # Return as RGBA array with values 0-255
                if img.dtype == np.float32 or img.dtype == np.float64:
                    img = (img * 255).astype(np.uint8)
                
                # Create image dict for Shiny
                return {
                    "src": output_file,
                    "alt": f"Drought hydrograph for {gauge_id}",
                    "style": "width:100%; height:auto;"
                }
            else:
                print(f"R script did not create expected file: {output_file}")
                return None
                
    except Exception as e:
        print(f"Error creating drought hydrograph: {e}")
        import traceback
        traceback.print_exc()
        return None


def drought_hydrograph_r_available():
    """Check if R integration is available.
    
    Returns:
        bool: True if rpy2 and R script are available
    """
    return R_AVAILABLE and R_SCRIPT_PATH.exists()

#!/bin/bash
# Installation script for R drought hydrograph integration
# This script installs all required R packages and Python dependencies

set -e

echo "======================================================"
echo "Installing R Drought Hydrograph Integration"
echo "======================================================"
echo ""

# Check if R is installed
echo "Checking R installation..."
if command -v R &> /dev/null; then
    R_VERSION=$(R --version | head -1)
    echo "✓ R found: $R_VERSION"
else
    echo "✗ R not found. Please install R first."
    echo "  Ubuntu/Debian: sudo apt-get install r-base"
    echo "  macOS: brew install r"
    exit 1
fi
echo ""

# Install R packages
echo "Installing R packages (ggplot2, patchwork, scales, xts, zoo)..."
R --vanilla --quiet -e "
packages <- c('ggplot2', 'patchwork', 'scales', 'xts', 'zoo')
installed <- installed.packages()[, 'Package']
to_install <- setdiff(packages, installed)
if (length(to_install) > 0) {
    install.packages(to_install, repos = 'https://cloud.r-project.org')
    cat('Installed R packages successfully\n')
} else {
    cat('All R packages already installed\n')
}
"
echo ""

# Check for virtual environment
VENV_DIR="$(dirname "$0")/.venv"
if [ -d "$VENV_DIR" ]; then
    echo "Installing rpy2 in virtual environment..."
    "$VENV_DIR/bin/pip" install rpy2
    echo "✓ rpy2 installed in virtual environment"
else
    echo "Installing rpy2 in system Python..."
    pip install rpy2
    echo "✓ rpy2 installed"
fi
echo ""

# Verify installation
echo "Verifying installation..."
if python -c "import rpy2" 2>/dev/null; then
    echo "✓ rpy2 is importable"
else
    echo "✗ rpy2 not found in Python path"
    echo "  Make sure you're using the correct Python/virtual environment"
fi
echo ""

echo "======================================================"
echo "Installation complete!"
echo "======================================================"
echo ""
echo "To test the integration:"
echo "  1. Start the app: cd src/shiny_app && python -m shiny run app.py"
echo "  2. Navigate to the Hydrological tab"
echo "  3. Click on a gauge marker"
echo ""
echo "If you still see the simple discharge plot, check that:"
echo "  - You're using the Python environment where rpy2 was installed"
echo "  - R packages are installed correctly"
echo ""

#!/usr/bin/env bash
set -euo pipefail
cd /home/chris/projects/IRISCC/iriscc_demostrator_drought_risk
echo "=== build context size ==="
du -sh .
echo "=== docker build start: $(date) ==="
docker build -t iriscc-drought-risk:1.0 .
echo "=== docker build exit: $? $(date) ==="
docker images

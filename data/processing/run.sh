#!/usr/bin/env bash
# Generate the decadal drought-statistic files the app reads.
#
# Output filenames: <prefix>[_<agg>]_<thresh>_<decade>_<stat>.nc
#   --agg  optional temporal-aggregation label. Pass it for indices computed
#          over a window (e.g. a 92-day SPI -> 92D); omit it for variables with
#          no aggregation (e.g. SMI).
#   --thresh is encoded in the name, so looping over thresholds produces
#          independent file sets that the app can offer as a choice.
#
# On JSC, load the toolchain first:  source jsc_env.sh
set -euo pipefail
source ../../.venv/bin/activate

model=mHM

# ── Agricultural drought: SMI (no temporal aggregation -> no --agg) ──────────
SMI_IFILE=/p/scratch/cjibg31/jibg3105/data/HOLIDROUGHT/SMI_IRISCC/${model}_SMI_reference_1960_1999.nc
SMI_ODIR=/p/scratch/cjibg31/jibg3105/data/HOLIDROUGHT/SMI_IRISCC/decadal/

for thresh in 0.2 0.3 ; do
  echo "SMI (${model}), thresh=${thresh}"
  python decadal_statistics.py \
    --ifile "${SMI_IFILE}" \
    --odir  "${SMI_ODIR}" \
    --var SMI \
    --prefix "${model}" \
    --dec1 1960 --dec2 1990 \
    --thresh "${thresh}"
  # -> CLM5_0.2_1960_mean.nc, CLM5_0.2_1960_dfreq.nc, ...  (no agg token)
done

exit

# ── Meteorological drought: SPI over a 92-day window (--agg 92D) ─────────────
SPI_IFILE=/p/scratch/cjibg31/jibg3105/data/HOLIDROUGHT/SXI_DETECT/SXI_92D.nc
SPI_ODIR=/p/scratch/cjibg31/jibg3105/data/HOLIDROUGHT/SXI_DETECT/decadal/

for thresh in -1.0 -1.5 -2.0 ; do
  echo "SPI (SXI_P, 92D), thresh=${thresh}"
  python decadal_statistics.py \
    --ifile "${SPI_IFILE}" \
    --odir  "${SPI_ODIR}" \
    --var SXI_P \
    --prefix SXI_P \
    --agg 92D \
    --dec1 1960 --dec2 2010 \
    --thresh "${thresh}"
  # -> SXI_P_92D_-1_1960_mean.nc, SXI_P_92D_-1_1960_dfreq.nc, ...  (with agg)
done

source ../../.venv/bin/activate


for y in `seq 1960 10 2010`; do
  echo "Processing decade $y"
  python decadal_statistics.py \
    --ifile /p/scratch/cjibg31/jibg3105/data/HOLIDROUGHT/SMI_IRISCC/ \
    --odir /p/scratch/cjibg31/jibg3105/data/HOLIDROUGHT/SMI_IRISCC/decadal/ \
    --var SMI \
    --prefix CLM5 \
    --dec1 $y \
    --dec2 $((y+9)) \
    --thresh 0.2
done

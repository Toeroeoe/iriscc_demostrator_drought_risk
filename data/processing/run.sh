source ../../.venv/bin/activate

python decadal_statistics.py \
  --ifile /p/scratch/cjibg31/jibg3105/data/HOLIDROUGHT/SMI_IRISCC/  --odir /p/scratch/cjibg31/jibg3105/data/HOLIDROUGHT/SMI_IRISCC/decadal/ \
  --var SMI --prefix CLM5 --thresh 0.2

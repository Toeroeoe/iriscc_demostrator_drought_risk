
ifile=/p/scratch/cjibg31/jibg3105/data/HOLIDROUGHT/SXI_DETECT/SXI_92D.nc
odir=/p/scratch/cjibg31/jibg3105/data/HOLIDROUGHT/SXI_DETECT/decadal/
var=SXI_P
oprefix=${var}_92D_
osuffix=_dfreq
dec1=1960
dec2=2010
thresh=-1

for y0 in $(seq $dec1 10 $dec2); do
  y1=$((y0 + 9))
  cdo -timmean -lec,$thresh -selyear,${y0}/${y1} -selvar,$var $ifile \
  $odir/${oprefix}${y0}_${y1}${osuffix}.nc
done

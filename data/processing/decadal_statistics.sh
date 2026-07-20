
ifile=SXI_92D.nc
odir=decadal/
oprefix=SXI_P_92D_
dec1=1960
dec2=2010
thresh=-1

for y0 in $(seq $dec1 10 $dec2); do
  y1=$((y0 + 9))
  cdo -timmean -lec,$thresh -selyear,${y0}/${y1} $ifile \
  $odir/${oprefix}${y0}_${y1}_dfreq.nc
done

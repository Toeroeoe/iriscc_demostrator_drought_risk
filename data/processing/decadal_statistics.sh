
ifile=/p/scratch/cjibg31/jibg3105/data/HOLIDROUGHT/SXI_DETECT/SXI_92D.nc
odir=/p/scratch/cjibg31/jibg3105/data/HOLIDROUGHT/SXI_DETECT/decadal/
var=SXI_P
oprefix=${var}_92D_
osuffix=_dfreq
dec1=1960
dec2=2010
thresh=-1
tstep=8

for y0 in $(seq $dec1 10 $dec2); do
  y1=$((y0 + 9))
  tmp=$(mktemp --suffix=.nc)

  echo "Processing ${y0}-${y1}"
  cdo -selyear,${y0}/${y1} -selvar,$var $ifile $tmp   # read full file once
  echo "  - computing statistics: relative drought time"
  cdo -timmean -lec,$thresh $tmp  ${base}_dfreq.nc     # then operate on the
  echo "  - computing statistics: min drought index"
  cdo -timmin              $tmp  ${base}_min.nc         # small decade file
  echo "  - computing statistics: longest drought spell"
  cdo -mulc,$tstep -timmax -consecsum -lec,$thresh $tmp ${base}_maxspell.nc
  rm -f "$tmp"
done


ifile=/p/scratch/cjibg31/jibg3105/data/HOLIDROUGHT/SMI_IRISCC/CLM5_SMI_reference_1960_1999.nc
odir=/p/scratch/cjibg31/jibg3105/data/HOLIDROUGHT/SMI_IRISCC/decadal/
var=SMI
oprefix=${var}_CLM5_
dec1=1960
dec2=1990
thresh=-1
tstep=8

for y0 in $(seq $dec1 10 $dec2); do
  y1=$((y0 + 9))
  tmp=$(mktemp --suffix=.nc)

  echo "Processing ${y0}-${y1}"
  cdo -selyear,${y0}/${y1} -selvar,$var $ifile $tmp
  echo "  - computing statistics: relative drought time"
  cdo -timmean -lec,$thresh $tmp  ${odir}/${oprefix}${y0}_dfreq.nc
  echo "  - computing statistics: min drought index"
  cdo -timmin $tmp  ${odir}/${oprefix}${y0}_min.nc
  echo "  - computing statistics: longest drought spell"
  cdo -mulc,$tstep -timmax -consecsum -lec,$thresh $tmp ${odir}/${oprefix}${y0}_maxspell.nc
  rm -f "$tmp"
done

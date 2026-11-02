#!/usr/bin/env bash
# build_drought_app_full.sh — build a SELF-CONTAINED image with data/ baked in.
#
# Same Dockerfile as the slim image; the difference is only the build context:
# the repo's .dockerignore excludes data/ (the slim image expects it mounted),
# so we hardlink-stage the project into a temp dir, drop that one exclusion
# there, and build from the staged copy.
#
# cp -al = hardlinks: staging is instant and uses ~no extra disk (staging and
# the repo must be on the same filesystem). Unlinking the stage never touches
# the originals.
#
# Image:  iriscc-drought-risk:1.0-full  (data included, no -v at run time)
#         iriscc-drought-risk:1.0       (code only, data mounted  -> build_drought_app.sh)

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

STAGE="../.iriscc-stage-full"   # must live OUTSIDE the repo (cp -al . cannot copy into a subdir of itself)
IMAGE="iriscc-drought-risk:1.0-full"

if [ ! -d data ]; then
  echo "ERROR: no ./data to bake in — run ./fetch_data.sh first." >&2
  exit 1
fi

echo "=== staging (hardlink, outside repo) ==="
# Refuse to stage a dirty tree: a stale stage dir inside the repo would be
# hardlink-copied into the build context (.git/data inside it are NOT matched
# by the top-level .dockerignore rules) and baked into the image.
if [ -e ".stage-full" ] || [ -e "../.iriscc-stage-full" ]; then
  echo "ERROR: stale stage dir present (.stage-full or ../.iriscc-stage-full) — refusing." >&2
  exit 1
fi
rm -rf "$STAGE"
cp -al . "$STAGE"

# In the staged copy only: let data/ into the build context.
# (sed on the staged .dockerignore; the repo original is untouched.)
sed -i 's|^data$|# data  (RE-ENABLED for the full/self-contained build)|' "$STAGE/.dockerignore"
grep -n "data" "$STAGE/.dockerignore" || true

echo "=== build context size (should be ~1.5G) ==="
du -sh "$STAGE"

echo "=== docker build start: $(date) ==="
docker build -t "$IMAGE" "$STAGE"

echo "=== cleanup stage ==="
rm -rf "$STAGE"

echo "=== images ==="
docker images iriscc-drought-risk

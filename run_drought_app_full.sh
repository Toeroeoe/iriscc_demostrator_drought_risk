#!/usr/bin/env bash
# run_drought_app_full.sh — run the SELF-CONTAINED image (data baked in).
# No volume mount: the data lives inside the image.
#
# Requires: ./build_drought_app_full.sh
# (run_drought_app.sh is the slim variant that mounts ./data read-only)

set -uo pipefail
IMAGE="iriscc-drought-risk:1.0-full"

echo "=== image present ==="
docker images "$IMAGE"
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "ERROR: $IMAGE not found — run ./build_drought_app_full.sh first." >&2
  exit 1
fi

echo "=== starting container (no mounts; data baked in) ==="
docker rm -f drought-risk-full 2>/dev/null
docker run -d --name drought-risk-full -p 8080:8080 "$IMAGE"

echo "=== waiting for startup ==="
for i in $(seq 1 45); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/ 2>/dev/null || echo 000)
  echo "  t+${i}s  HTTP $code"
  if [ "$code" = "200" ]; then break; fi
  sleep 1
done

echo "=== container status ==="
docker ps -a --filter name=drought-risk-full

echo "=== data inside the image ==="
docker exec drought-risk-full sh -c "find /code/data -type f | wc -l"

echo "=== container logs (tail 20) ==="
docker logs --tail 20 drought-risk-full 2>&1

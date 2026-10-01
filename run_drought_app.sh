#!/usr/bin/env bash
set -uo pipefail
echo "=== image present ==="
docker images iriscc-drought-risk

echo "=== starting container ==="
docker rm -f drought-risk 2>/dev/null
docker run -d --name drought-risk -p 8080:8080 iriscc-drought-risk:1.0

echo "=== waiting for startup ==="
for i in $(seq 1 45); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/ 2>/dev/null || echo 000)
  echo "  t+${i}s  HTTP $code"
  if [ "$code" = "200" ]; then break; fi
  sleep 1
done

echo "=== curl root (first 400 chars) ==="
curl -s http://localhost:8080/ | head -c 400
echo
echo "=== container status ==="
docker ps -a --filter name=drought-risk

echo "=== container logs (tail 40) ==="
docker logs --tail 40 drought-risk 2>&1

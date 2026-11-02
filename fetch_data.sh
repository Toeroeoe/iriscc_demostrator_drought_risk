#!/usr/bin/env bash
# fetch_data.sh — populate ./data from a single frozen dataset tarball.
#
# Usage:
#   ./fetch_data.sh                  # download + verify + extract (skips if done)
#   ./fetch_data.sh --force          # re-download and replace ./data
#   DATA_URL=... DATA_SHA256=... ./fetch_data.sh
#
# Then start the app with:
#   docker run --rm -p 8000:8000 -v "$PWD/data:/code/data:ro" iriscc-drought-risk:1.0
#
# Building the tarball (one-time, from a machine that has the real data):
#   tar -czf data-v1.tar.gz data          # top-level 'data/' dir inside
#   sha256sum data-v1.tar.gz              # paste the hash into DATA_SHA256 / --sha256

set -euo pipefail

# ── Configuration (override via environment or flags) ───────────────────────
# EXAMPLE placeholder — replace with your real hosted tarball URL
# (a Zenodo DOI link is ideal: versioned, citable, stable).
DATA_URL="${DATA_URL:-https://example.org/iriscc-drought-risk/data-v1.tar.gz}"
# sha256 of the tarball. Empty string disables verification (NOT recommended).
DATA_SHA256="${DATA_SHA256:-0000000000000000000000000000000000000000000000000000000000000000}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${DATA_DIR:-$SCRIPT_DIR/data}"
SENTINEL="$DATA_DIR/.fetch_ok"

FORCE=0
for arg in "$@"; do
  case "$arg" in
    --force)   FORCE=1 ;;
    --url=*)   DATA_URL="${arg#*=}" ;;
    --sha256=*) DATA_SHA256="${arg#*=}" ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

log() { echo "=== $* ==="; }
die() { echo "ERROR: $*" >&2; exit 1; }

# ── Preflight ───────────────────────────────────────────────────────────────
for tool in curl tar sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || die "required tool '$tool' not found"
done

if [ -f "$SENTINEL" ] && [ "$FORCE" -eq 0 ]; then
  log "data already present ($SENTINEL) — nothing to do (use --force to refresh)"
  exit 0
fi

if [ -d "$DATA_DIR" ] && [ -n "$(ls -A "$DATA_DIR" 2>/dev/null)" ] && [ "$FORCE" -eq 0 ]; then
  die "$DATA_DIR is non-empty but has no .fetch_ok sentinel; refusing to overwrite. Re-run with --force."
fi

# ── Download + extract in a temp dir on the SAME filesystem ─────────────────
# (same-fs temp so the final move into place is instant, not a 1.4 GB copy)
TMP_DIR="$(mktemp -d "$SCRIPT_DIR/.fetch_tmp.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT
TARBALL="$TMP_DIR/data.tar.gz"

log "downloading $DATA_URL"
curl -fL --retry 3 --retry-delay 5 --progress-bar -o "$TARBALL" "$DATA_URL" \
  || die "download failed"
log "downloaded $(du -h "$TARBALL" | cut -f1)"

# ── Verify integrity BEFORE extracting ──────────────────────────────────────
if [ -n "$DATA_SHA256" ]; then
  log "verifying sha256"
  echo "${DATA_SHA256}  ${TARBALL}" | sha256sum -c - \
    || die "checksum mismatch — refusing to extract (corrupt or changed download)"
else
  log "WARNING: no sha256 provided — skipping integrity check"
fi

# ── Extract ─────────────────────────────────────────────────────────────────
log "extracting"
EXTRACT_DIR="$TMP_DIR/extract"
mkdir -p "$EXTRACT_DIR"
tar -xzf "$TARBALL" -C "$EXTRACT_DIR" || die "extraction failed"
[ -d "$EXTRACT_DIR/data" ] || die "tarball does not contain a top-level data/ directory"
[ -n "$(ls -A "$EXTRACT_DIR/data")" ] || die "extracted data/ is empty"

# ── Move into place (atomic swap on same filesystem) ────────────────────────
if [ "$FORCE" -eq 1 ] && [ -d "$DATA_DIR" ]; then
  rm -rf "${DATA_DIR:?}"
fi
mv "$EXTRACT_DIR/data" "$DATA_DIR"

# ── Sentinel (idempotency + provenance) ─────────────────────────────────────
{
  echo "fetched_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "url: $DATA_URL"
  echo "sha256: $DATA_SHA256"
} > "$SENTINEL"

log "done — $(du -sh "$DATA_DIR" | cut -f1) in $DATA_DIR"
log "start the app with:"
echo "  docker run --rm -p 8080:8080 -v \"$DATA_DIR:/code/data:ro\" iriscc-drought-risk:1.0"

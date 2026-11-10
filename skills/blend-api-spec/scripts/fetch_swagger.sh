#!/usr/bin/env bash
# Refresh assets/vendor from swagger-ui-dist at an EXACT version (never a range, never "latest").
# Usage: scripts/fetch_swagger.sh [5.34.1]      Needs network and npm. The repo already ships this version,
# so you only run this to upgrade; afterwards re-run validate_api.py on a built example.
set -euo pipefail
VER="${1:-5.34.1}"
[[ "$VER" =~ ^5\.[0-9]+\.[0-9]+$ ]] || { echo "version must be exact 5.x.y, got '$VER'" >&2; exit 2; }
DEST="$(cd "$(dirname "$0")/.." && pwd)/assets/vendor"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
( cd "$TMP" && npm pack "swagger-ui-dist@$VER" >/dev/null && tar xzf "swagger-ui-dist-$VER.tgz" )
P="$TMP/package"
[ "$(node -p "require('$P/package.json').version")" = "$VER" ] || { echo "version mismatch in package" >&2; exit 1; }
mkdir -p "$DEST"
cp "$P/swagger-ui-bundle.js" "$P/swagger-ui.css" "$P/LICENSE" "$P/NOTICE" "$DEST/"
echo "$VER" > "$DEST/VERSION"
grep -q "$VER" "$DEST/swagger-ui-bundle.js" || echo "warning: version string not found inside bundle" >&2
echo "vendor updated to swagger-ui-dist@$VER; index.html references vendor/swagger-ui-bundle.js (check with validate_api.py)"

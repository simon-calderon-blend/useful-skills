#!/usr/bin/env bash
# Render a .docx to PDF and per-page PNGs so the layout can be inspected.
# usage: render.sh <file.docx> [out-dir] [dpi]
# The PDF and PNGs are throwaway review files, never the deliverable (the deliverable is always the .docx),
# so the default out-dir is a temp folder, not the folder holding the .docx. dpi defaults to 80.
# Output: <out-dir>/<name>.pdf and <out-dir>/<name>-<page>.png
# Montserrat must be installed for faithful metrics; without it the render uses a fallback font.
set -euo pipefail

src="${1:?usage: render.sh <file.docx> [out-dir] [dpi]}"
out="${2:-${TMPDIR:-/tmp}/blend-render}"
dpi="${3:-80}"
name="$(basename "${src%.*}")"

command -v soffice >/dev/null || { echo "error: LibreOffice (soffice) not found" >&2; exit 1; }
command -v pdftoppm >/dev/null || { echo "error: pdftoppm (poppler) not found" >&2; exit 1; }

fonts="$(fc-list)"  # captured first: grep -q under pipefail can SIGPIPE fc-list
if ! grep -qi "montserrat" <<<"$fonts"; then
  echo "warn: Montserrat is not installed; fonts in this render are a fallback (Word on a machine with Montserrat will differ)" >&2
fi

mkdir -p "$out"
rm -f "$out/$name".pdf "$out/$name"-*.png
soffice --headless --convert-to pdf --outdir "$out" "$src" >/dev/null 2>&1
pdftoppm -png -r "$dpi" "$out/$name.pdf" "$out/$name"
pages="$(ls "$out/$name"-*.png | wc -l)"
echo "rendered $pages page(s) -> $out/$name.pdf, $out/$name-*.png"

#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${API_BASE_URL:-}" ]]; then
  echo "Erreur : définissez API_BASE_URL dans les variables Netlify (ex. https://api.votre-domaine.tld)." >&2
  exit 1
fi

python3 - <<'PY'
import json
import os
from pathlib import Path

api_url = os.environ["API_BASE_URL"].strip().rstrip("/")
if not api_url.startswith("https://"):
    raise SystemExit("API_BASE_URL doit commencer par https://")

source = Path("templates/campus-shop.html").read_text(encoding="utf-8")
needle = "    const API_BASE = window.CAMPUS_SHOP_API_BASE || '';"
replacement = f"    const API_BASE = window.CAMPUS_SHOP_API_BASE || {json.dumps(api_url)};"
if source.count(needle) != 1:
    raise SystemExit("Impossible de configurer l'URL API dans le frontend.")

dist = Path("dist")
dist.mkdir(exist_ok=True)
(dist / "index.html").write_text(source.replace(needle, replacement), encoding="utf-8")
PY

#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command -v python3 >/dev/null || { printf 'Python 3.12+ required.\n' >&2; exit 1; }
command -v npm >/dev/null || { printf 'Node 22.12+ and npm required.\n' >&2; exit 1; }
if [[ ! -x .venv/bin/python ]]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.lock
npm --prefix frontend ci --no-fund
npm --prefix frontend run build
if [[ "${1:-}" == '--verify' ]]; then
  .venv/bin/python -m pytest tests/ -q
  npm --prefix frontend test
  exit 0
fi
if [[ -n "${1:-}" ]]; then printf 'Usage: ./run-demo.sh [--verify]\n' >&2; exit 2; fi
printf '\nRFQ-to-Quote DEMO: http://127.0.0.1:%s/\nSynthetic operations; offline parser opt-in; local human approval, no real email. Ctrl+C stops.\n' "${RFQ_PORT:-8000}"
exec .venv/bin/python -m uvicorn backend.portfolio:application --factory --host 127.0.0.1 --port "${RFQ_PORT:-8000}"

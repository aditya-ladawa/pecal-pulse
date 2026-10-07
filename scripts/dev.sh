#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$project_dir"
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --reload --reload-dir backend &
backend_pid=$!
cleanup() {
  kill "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM
cd frontend
pnpm dev

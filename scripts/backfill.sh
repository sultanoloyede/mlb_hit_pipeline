#!/usr/bin/env bash
# Phase 1 backfill: 2021 → yesterday into MotherDuck (~5-6 h total).
#
# Resumable: statcast reads max(game_date) from the warehouse and skips
# completed seasons automatically. If interrupted mid-run, just re-run
# this script — already-loaded statsapi seasons are re-fetched (slow but
# harmless, staging dedupes), so optionally comment out finished years.
#
# Token: export MOTHERDUCK_TOKEN, or put `MOTHERDUCK_TOKEN=...` in a
# .env file at the repo root (gitignored).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a; source .env; set +a
fi
: "${MOTHERDUCK_TOKEN:?MOTHERDUCK_TOKEN not set (export it or put it in .env)}"

YESTERDAY=$(date -v-1d +%F 2>/dev/null || date -d yesterday +%F)

for yr in 2021 2022 2023 2024 2025; do
  echo "=== season $yr: statcast (resumes from warehouse max) ==="
  python ingestion/pipelines.py statcast --end "$yr-11-05"
  echo "=== season $yr: statsapi ==="
  python ingestion/pipelines.py statsapi --start "$yr-03-15" --end "$yr-11-05"
done

echo "=== 2026 season to yesterday ==="
python ingestion/pipelines.py statcast --end "$YESTERDAY"
python ingestion/pipelines.py statsapi --start 2026-03-15 --end "$YESTERDAY"

echo "=== WAR seasons + coaches ==="
python ingestion/pipelines.py war     --seasons 2021 2025
python ingestion/pipelines.py coaches --seasons 2021 2026

echo "=== Phase 1 gate: reconcile vs prototype ==="
python ingestion/reconcile.py
echo "backfill complete"

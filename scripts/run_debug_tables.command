#!/bin/bash
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
source .venv/bin/activate
python scripts/debug_tables.py 2>&1 | tee logs/debug_tables.log

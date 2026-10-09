#!/bin/bash
# Same single unsigned workflow; the shared deadline includes every native phase.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 Scripts/run_swiftui_acceptance.py

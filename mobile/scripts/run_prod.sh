#!/usr/bin/env bash
# Достаточно .env в корне проекта.
set -euo pipefail
cd "$(dirname "$0")/.."
exec flutter run "$@"

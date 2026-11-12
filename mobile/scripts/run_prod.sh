#!/usr/bin/env bash
# Запуск с API из локального .env (не в assets/git).
set -euo pipefail
cd "$(dirname "$0")/.."
exec flutter run --dart-define-from-file=.env "$@"

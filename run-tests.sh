#!/usr/bin/env bash
set -euo pipefail

COMPOSE=(docker compose --profile tests)

cleanup() {
    "${COMPOSE[@]}" stop test_db >/dev/null 2>&1 || true
}
trap cleanup EXIT

"${COMPOSE[@]}" build web_server_tests
"${COMPOSE[@]}" up -d test_db

"${COMPOSE[@]}" run --rm web_server_tests bash -o pipefail -c \
    "pytest -v --ignore tests/test_oval --cov --cov-report=term $*"

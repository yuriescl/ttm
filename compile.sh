#!/usr/bin/env bash
CURRENT_DIR="$( cd "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
cd "$CURRENT_DIR"

set -e
cython -3 --embed -o startstop.c startstop.py
gcc -Os -I /usr/include/python3.9 -o startstop startstop.c -lpython3.9 -lpthread -lm -lutil -ldl
strip -s -R .comment -R .gnu.version --strip-unneeded startstop
set +e


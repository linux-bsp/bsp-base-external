#!/bin/sh
# Buildroot post-image entry point. All firmware definitions are in firmware.json.
set -eu
exec "${HOST_DIR}/bin/python3" "$(dirname -- "$0")/../firmware/image.py" "$@"

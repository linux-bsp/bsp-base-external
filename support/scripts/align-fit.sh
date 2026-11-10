#!/bin/bash
# Deployed U-Boot requires the inline DTB's address to be eight-byte aligned.
set -euo pipefail
fit=$1
dtb=$2
tool="$HOST_DIR/bin/fw-build-tool"
offset=$("$tool" dtb-offset "$fit" "$dtb")
if ((offset%8 == 4)); then
    "$HOST_DIR/bin/fdtput" -t x "$fit" / fw,dtb-alignment-padding
    offset=$("$tool" dtb-offset "$fit" "$dtb")
    if ((offset%8 == 4)); then "$HOST_DIR/bin/fdtput" -t x "$fit" / fw,dtb-alignment-padding 0; fi
fi
offset=$("$tool" dtb-offset "$fit" "$dtb")
((offset%8 == 0)) || { echo 'Kernel FIT DTB alignment failed' >&2; exit 1; }

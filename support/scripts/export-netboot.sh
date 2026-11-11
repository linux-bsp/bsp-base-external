#!/bin/bash
# Publish paired TFTP/NFS inputs after Buildroot has produced rootfs.tar.
set -euo pipefail
images=$(realpath "$1")
kernel=$2
dtb=$3
compression=$4
jq="$HOST_DIR/bin/jq"
netboot="$images/netboot"
mkdir -p "$netboot"
case "$compression" in
    gzip) gzip -dc "$images/$kernel" > "$netboot/Image" ;;
    none) cp "$images/$kernel" "$netboot/Image" ;;
    *) echo "Unsupported network kernel compression: $compression" >&2; exit 1 ;;
esac
dtb=${dtb##*/}
cp "$images/$3" "$netboot/$dtb"
cp "$TARGET_DIR/etc/bsp/netboot.conf" "$netboot/build.conf"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
for name in netboot/Image "netboot/$dtb" netboot/build.conf rootfs.tar; do
    "$jq" -cn --arg name "$name" --arg hash "$(sha256sum "$images/$name" | cut -d ' ' -f 1)" '{($name):$hash}'
done | "$jq" -s add > "$work/hashes.json"
"$jq" -n --arg dtb "$dtb" --arg reference "$(cat "$netboot/build.conf")" --slurpfile sha "$work/hashes.json" \
    '{format:"BSP-NETBOOT-1",dtb:$dtb,reference_build:$reference,sha256:$sha[0]}' > "$netboot/manifest.json"

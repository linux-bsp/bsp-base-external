#!/bin/bash
# Called by a board's native post-build hook with explicit image/version inputs.
set -euo pipefail
target=$(realpath "$1")
kernel=$(realpath "$2")
dtb=$(realpath "$3")
version_file=$(realpath "$4")
destination="$target/etc/bsp/netboot.conf"
mkdir -p "$(dirname "$destination")"
IFS=. read -r major minor patch < "$version_file"
for part in "$major" "$minor" "$patch"; do
    [[ $part =~ ^[0-9]+$ ]] && ((10#$part<=255))
done
version=$((10#$major*65536+10#$minor*256+10#$patch))
digest=$({
    printf 'BSP network build v1\000kernel\000'
    cat "$kernel"
    printf '\000dtb\000'
    cat "$dtb"
    tar -C "$target" --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
        --exclude=./etc/bsp/netboot.conf -cf - .
} | sha256sum | cut -d ' ' -f 1)
printf 'BSPNET1 %s %s\n' "$version" "$digest" > "$destination"
chmod 0644 "$destination"
printf 'BSP reference network build: %.8s\n' "$digest"

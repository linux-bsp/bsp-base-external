#!/bin/bash
# Linux's native gen_init_cpio supplies root ownership and device nodes without root.
set -euo pipefail
[ "$#" -eq 2 ] || { echo "Usage: $0 ROOT OUTPUT.cpio.gz" >&2; exit 2; }
root=$(realpath "$1")
output=$(realpath -m "$2")
generator="$BUILD_DIR/linux-custom/usr/gen_init_cpio"
[ -x "$generator" ] || { echo 'Build Linux usr/gen_init_cpio first' >&2; exit 1; }
list=$(mktemp)
trap 'rm -f "$list" "$output.tmp"' EXIT HUP INT TERM
printf 'dir . 0755 0 0\n' > "$list"
find "$root" -mindepth 1 -print | LC_ALL=C sort | while IFS= read -r file; do
    name=${file#"$root"/}
    case "$name" in *[[:space:]]*) echo 'Whitespace in initramfs path' >&2; exit 1;; esac
    mode=$(stat -c %a "$file")
    if [ -L "$file" ]; then
        printf 'slink /%s %s 0777 0 0\n' "$name" "$(readlink "$file")"
    elif [ -d "$file" ]; then
        printf 'dir /%s 0%s 0 0\n' "$name" "$mode"
    elif [ -f "$file" ]; then
        printf 'file /%s %s 0%s 0 0\n' "$name" "$file" "$mode"
    else
        echo "Unsupported initramfs file: $file" >&2; exit 1
    fi
done >> "$list"
printf 'nod /dev/console 0600 0 0 c 5 1\nnod /dev/null 0666 0 0 c 1 3\n' >> "$list"
mkdir -p "$(dirname "$output")"
# Avoid a pipeline hiding a failed archive generator.
"$generator" -t 0 "$list" > "$output.tmp"
gzip -n -c "$output.tmp" > "$output"

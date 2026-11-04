#!/bin/sh
# Generate a self-contained data+hash-tree image and bind its parameters into
# the DTB that is subsequently hashed inside kernel.itb. No target-side helper.
set -eu
[ "$#" -eq 4 ] || { echo "Usage: $0 HOST_DIR ROOTFS OUTPUT DTB" >&2; exit 2; }
host_dir=$1
source_image=$2
verity_image=$3
dtb=$4
veritysetup="$host_dir/sbin/veritysetup"
[ -x "$veritysetup" ] || veritysetup="$host_dir/bin/veritysetup"
[ -x "$veritysetup" ] || { echo "Build host-cryptsetup first" >&2; exit 1; }
[ "$source_image" != "$verity_image" ] || exit 1
size=$(stat -c %s "$source_image")
[ "$size" -gt 0 ] || exit 1
blocks=$(((size + 4095) / 4096))
bytes=$((blocks * 4096))
# A content-derived salt makes repeated generation deterministic.
salt=$(sha256sum "$source_image" | cut -d ' ' -f 1)
record="$verity_image.info"
cp "$source_image" "$verity_image"
truncate -s "$bytes" "$verity_image"
LC_ALL=C "$veritysetup" format --format=1 --hash=sha256 --no-superblock     --data-block-size=4096 --hash-block-size=4096 --data-blocks="$blocks"     --hash-offset="$bytes" --salt="$salt" "$verity_image" "$verity_image" > "$record"
root_hash=$(sed -n 's/^Root hash:[[:space:]]*//p' "$record")
[ "${#root_hash}" -eq 64 ] || exit 1
LC_ALL=C "$veritysetup" verify --format=1 --hash=sha256 --no-superblock     --data-block-size=4096 --hash-block-size=4096 --data-blocks="$blocks"     --hash-offset="$bytes" --salt="$salt" "$verity_image" "$verity_image" "$root_hash"
total=$(stat -c %s "$verity_image")
hash_blocks=$(((total - bytes) / 4096))
[ "$hash_blocks" -gt 0 ] || exit 1
fdtput="$host_dir/bin/fdtput"
"$fdtput" -p -t s "$dtb" /chosen/fw-verity algorithm sha256
"$fdtput" -t s "$dtb" /chosen/fw-verity root-hash "$root_hash"
"$fdtput" -t s "$dtb" /chosen/fw-verity salt "$salt"
"$fdtput" -t u "$dtb" /chosen/fw-verity version 1
"$fdtput" -t u "$dtb" /chosen/fw-verity data-blocks "$blocks"
"$fdtput" -t u "$dtb" /chosen/fw-verity hash-start-block "$blocks"
"$fdtput" -t u "$dtb" /chosen/fw-verity hash-blocks "$hash_blocks"
payload_sha=$(sha256sum "$verity_image" | cut -d ' ' -f 1)
"$fdtput" -t s "$dtb" /chosen/fw-verity payload-sha256 "$payload_sha"
"$fdtput" -t u "$dtb" /chosen/fw-verity payload-bytes "$total"
echo "Rootfs verity: $blocks data blocks, $hash_blocks hash blocks, root=$root_hash"

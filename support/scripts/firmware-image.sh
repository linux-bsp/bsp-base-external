#!/bin/bash
# Native Buildroot post-image hook. fw-tools handles binary formats, jq the JSON.
set -euo pipefail
images=$(realpath -m "$1")
shift
config=
while (($#)); do
    case "$1" in -c|--config) config=$(realpath "$2"); shift 2;; *) echo "Unknown argument: $1" >&2; exit 2;; esac
 done
[[ -n $config ]]
scripts=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
firmware="$scripts/../firmware"
board=$(dirname "$config")
export PATH="$HOST_DIR/bin:$HOST_DIR/sbin:$PATH"
jq="$HOST_DIR/bin/jq"
tool="$HOST_DIR/bin/fw-build-tool"
"$tool" check-json "$config"
version_file=$("$jq" -r '.version|if type=="object" then .file else empty end' "$config")
version=
if [[ -n $version_file ]]; then
    [[ $version_file != /* && $version_file != *[!A-Za-z0-9_./-]* ]] || exit 1
    version_file=$(realpath "$board/$version_file")
    version=$(sed 's/^[[:space:]]*//;s/[[:space:]]*$//' "$version_file")
fi
work=$(mktemp -d "$(dirname "$images")/.firmware-XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
stage="$work/images"
mkdir -p "$stage/release" "$images"
"$jq" --arg version "$version" -f "$firmware/config.jq" "$config" > "$stage/firmware.json"
declaration="$stage/firmware.json"
get() { "$jq" -r "$1" "$declaration"; }
size_limit() {
    local size
    [[ -f $1 ]] || { echo "Missing firmware input: $1" >&2; return 1; }
    size=$(stat -c %s "$1")
    ((size>0)) || { echo "Empty firmware input: $1" >&2; return 1; }
    [[ $2 == null ]] || ((size <= $2)) || { echo "Firmware input exceeds max_size: $1" >&2; return 1; }
}
get '.components[].images[]|select(has("generate")|not)|.file' > "$work/inputs"
while IFS= read -r file; do
    mkdir -p "$stage/$(dirname "$file")"
    cp --reflink=auto "$images/$file" "$stage/$file"
done < "$work/inputs"
"$jq" --arg stage "$stage" '.components|map_values(.images|map({key:.name,value:($stage+"/"+.file)})|from_entries)' "$declaration" > "$work/files.json"
if [[ $(get 'has("validation")') == true ]]; then
    "$HOST_DIR/bin/cmake" -DCONFIG="$declaration" -DDECLARATION="$config" \
        -DHOST_DIR="$HOST_DIR" -DTARGET_DIR="$TARGET_DIR" -DBUILD_DIR="$BUILD_DIR" \
        -DOUTPUT="$stage/layout-validation.json" -P "$firmware/layout.cmake"
fi
file_for() { "$jq" -r --arg component "$1" --arg name "$2" '.[$component][$name]' "$work/files.json"; }
set_file() {
    "$jq" --arg component "$1" --arg name "$2" --arg path "$3" '.[$component][$name]=$path' "$work/files.json" > "$work/files.new"
    mv "$work/files.new" "$work/files.json"
}
fdt_name=$(get '.components.kernel.fdt // empty')
dtb=
[[ -z $fdt_name ]] || dtb=$(file_for kernel "$fdt_name")
if [[ $(get '.components.rootfs.verity // false') == true ]]; then
    root_name=$(get '.components.rootfs.firmware')
    root=$(file_for rootfs "$root_name")
    verified="${root%.*}-verity.${root##*.}"
    verified_dtb="${dtb%/*}/verity-${dtb##*/}"
    for file in "$verified" "$verified_dtb"; do
        ! grep -Fxq "${file#"$stage"/}" "$work/inputs" || { echo 'Verity output collides with input' >&2; exit 1; }
    done
    cp "$dtb" "$verified_dtb"
    "$scripts/rootfs-verity.sh" "$HOST_DIR" "$root" "$verified" "$verified_dtb"
    set_file rootfs "$root_name" "$verified"
    set_file kernel "$fdt_name" "$verified_dtb"
    dtb=$verified_dtb
fi
while IFS=$'\t' read -r name file; do
    "$scripts/build-initramfs.sh" --target "$TARGET_DIR" --board "$board" --host "$HOST_DIR" --output "$stage/$file"
done < <(get '.components.kernel.images[]|select(.generate=="initramfs")|[.name,.file]|@tsv')
epoch=${SOURCE_DATE_EPOCH:-0}
[[ $epoch =~ ^[0-9]+$ ]] && ((epoch / 60 <= 4294967295))
export SOURCE_DATE_EPOCH=$epoch
minutes=$((epoch/60))
for component in bootloader kernel rootfs; do
    while IFS=$'\t' read -r name limit; do
        size_limit "$(file_for "$component" "$name")" "$limit"
    done < <(get ".components.$component.images[]|[.name,(.max_size // null)]|@tsv" | sed 's/\t$/\tnull/')
    "$jq" -r --arg component "$component" --argjson minutes "$minutes" --slurpfile files "$work/files.json" \
        --slurpfile identity /dev/null --slurpfile sha /dev/null -f "$firmware/fit.jq" "$declaration" > "$stage/release/$component.its"
    "$HOST_DIR/bin/mkimage" -f "$stage/release/$component.its" "$stage/release/$component.itb"
    size_limit "$stage/release/$component.itb" "$(get ".components.$component.max_size // null")"
done
kernel="$stage/release/kernel.itb"
if [[ -n $dtb ]]; then
    "$scripts/align-fit.sh" "$kernel" "$dtb"
    size_limit "$kernel" "$(get '.components.kernel.max_size // null')"
fi
kernel_bytes=$(od -An -N4 -j4 -tu4 --endian=big "$kernel" | tr -d ' ')
((kernel_bytes>=40 && kernel_bytes <= $(stat -c %s "$kernel")))
kernel_sha=$(head -c "$kernel_bytes" "$kernel" | sha256sum | cut -d ' ' -f 1)
"$HOST_DIR/bin/dumpimage" -T flat_dt -p 0 -o "$work/rootfs.payload" "$stage/release/rootfs.itb"
rootfs_bytes=$(stat -c %s "$work/rootfs.payload")
rootfs_sha=$(sha256sum "$work/rootfs.payload" | cut -d ' ' -f 1)
identity=$(printf 'BSPFWCONTENT1\nkernel %s %s\nrootfs %s %s\n' "$kernel_bytes" "$kernel_sha" "$rootfs_bytes" "$rootfs_sha" | sha256sum | cut -d ' ' -f 1)
version=$(get '.version')
IFS=. read -r major minor patch <<< "$version"
number=$((major*65536+minor*256+patch))
for component in bootloader kernel rootfs; do
    actual=$("$HOST_DIR/bin/fdtget" -t u "$stage/release/$component.itb" /configurations/conf-1 fw,version)
    ((actual==number)) || { echo 'FIT version differs from declaration' >&2; exit 1; }
done
"$jq" -n --arg tag "v$version" --arg id "$identity" --argjson version "$number" --argjson kb "$kernel_bytes" \
    --arg kh "$kernel_sha" --argjson rb "$rootfs_bytes" --arg rh "$rootfs_sha" \
    '{tag:$tag,firmware_id:$id,version:$version,kernel_bytes:$kb,kernel_sha256:$kh,rootfs_bytes:$rb,rootfs_sha256:$rh}' > "$stage/firmware-identity.json"
for component in bootloader kernel rootfs; do
    hash=$(sha256sum "$stage/release/$component.itb" | cut -d ' ' -f 1)
    "$jq" -cn --arg name "$component" --arg hash "$hash" '{($name):$hash}'
done | "$jq" -s add > "$work/hashes.json"
"$jq" -r --arg component release --argjson minutes "$minutes" --slurpfile files "$work/files.json" \
    --slurpfile identity "$stage/firmware-identity.json" --slurpfile sha "$work/hashes.json" \
    -f "$firmware/fit.jq" "$declaration" > "$stage/release/release.its"
"$HOST_DIR/bin/mkimage" -f "$stage/release/release.its" "$stage/release/release.itb"
"$tool" metadata "$stage/firmware-identity.json" "$stage/release/bootloader.itb" "$stage/release/kernel.itb" "$stage/release/rootfs.itb" "$stage"
"$HOST_DIR/bin/cmake" -DIMAGES="$stage" -DDECLARATION="$config" -DVERSION_FILE="$version_file" \
    -DBUILD_DIR="${BUILD_DIR:-/missing}" -DHOST_DIR="$HOST_DIR" -DEPOCH="$epoch" -P "$firmware/manifest.cmake"
if [[ $(get 'has("factory")') == true ]]; then
    if [[ $(get '.factory|has("environment")') == true ]]; then
        env_file="$TARGET_DIR/$(get '.factory.environment')"
        awk 'NF && $0 !~ /^#/ { key=$0; sub(/=.*/,"",key); if (!index($0,"=") || !length(key)) exit 1; if (!(key in values)) order[++n]=key; values[key]=$0 } END { for(i=1;i<=n;i++) print values[order[i]] }' "$env_file" > "$work/environment"
        grep -Eq '^hwid=1[0-9a-f]{12}000$' "$work/environment"
        "$HOST_DIR/bin/mkenvimage" -r -p 0 -s 0x10000 -o "$stage/uboot-env0.bin" "$work/environment"
        cp "$stage/uboot-env0.bin" "$stage/uboot-env1.bin"
        printf '\000' | dd of="$stage/uboot-env1.bin" bs=1 seek=4 conv=notrunc status=none
    fi
    export FW_ROOTFS_IMAGE="$(file_for rootfs "$(get '.components.rootfs.firmware')")"
    FW_ROOTFS_IMAGE=${FW_ROOTFS_IMAGE#"$stage"/}
    while IFS= read -r name; do
        variable="FW_BOOTLOADER_${name^^}_IMAGE"
        variable=${variable//-/_}
        file=$(file_for bootloader "$name")
        export "$variable=${file#"$stage"/}"
    done < <(get '.components.bootloader.images[].name')
    BINARIES_DIR="$stage" support/scripts/genimage.sh -c "$board/$(get '.factory.layout')"
fi
sidecars=(firmware.json firmware-identity.json layout-validation.json build-manifest.json meta0.bin meta1.bin)
for name in "${sidecars[@]}"; do [[ ! -f "$stage/$name" ]] || mv "$stage/$name" "$stage/release/"; done
while IFS= read -r file; do
    relative=${file#"$stage"/}
    [[ $relative != release/* ]] || continue
    grep -Fxq "$relative" "$work/inputs" && continue
    mkdir -p "$images/$(dirname "$relative")"
    mv "$file" "$images/$relative"
done < <(find "$stage" -type f -print | LC_ALL=C sort)
"$tool" exchange "$stage/release" "$images/release"
for name in "${sidecars[@]}"; do
    [[ -f "$images/release/$name" ]] || continue
    ln -s "release/$name" "$images/.$name.link"
    mv -Tf "$images/.$name.link" "$images/$name"
done
if [[ -f $TARGET_DIR/etc/bsp/netboot.conf ]]; then
    declaration="$images/firmware.json"
    kernel_name=$(get '.components.kernel.kernel')
    kernel_file=$(get ".components.kernel.images[]|select(.name==\"$kernel_name\")|.file")
    dtb_file=$(get ".components.kernel.images[]|select(.name==\"$fdt_name\")|.file")
    compression=$(get ".components.kernel.images[]|select(.name==\"$kernel_name\")|.compression // \"none\"")
    "$scripts/export-netboot.sh" "$images" "$kernel_file" "$dtb_file" "$compression"
fi
printf 'Firmware: v%s / %.8s\n' "$version" "$identity"

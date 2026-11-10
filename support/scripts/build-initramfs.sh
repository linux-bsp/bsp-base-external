#!/bin/bash
# Stage the complete target ELF dependency closure, then use Linux gen_init_cpio.
set -euo pipefail
while (($#)); do
    case "$1" in
        --target) target=$(realpath "$2");;
        --board) board=$(realpath "$2");;
        --host) host=$(realpath "$2");;
        --output) output=$(realpath -m "$2");;
        *) echo "Unknown initramfs argument: $1" >&2; exit 2;;
    esac
    shift 2
done
scripts=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
root="$work/root"
mkdir -p "$root"/{bin,sbin,usr/bin,usr/sbin,lib,usr/lib,dev,proc,sys,run,tmp,newroot,etc/network,var}
mkdir -p "$root/etc/network"/{if-pre-up.d,if-up.d,if-down.d,if-post-down.d}
chmod 1777 "$root/tmp"
ln -s ../run "$root/var/run"
ln -s ../run/lock "$root/var/lock"
ln -s lib "$root/lib64"
ln -s lib "$root/usr/lib64"
readelf=$(find "$host/bin" -maxdepth 1 -name '*-linux-*-readelf' -print -quit)
readelf=${readelf:-$(command -v readelf)}

resolve_target()
{
    local pending=${1#/} resolved= part link candidate links=0
    while [[ -n $pending ]]; do
        part=${pending%%/*}
        if [[ $pending == */* ]]; then pending=${pending#*/}; else pending=; fi
        case "$part" in
            ''|.) continue;;
            ..)
                [[ -n $resolved ]] || { echo 'Target symlink escapes root' >&2; return 1; }
                if [[ $resolved == */* ]]; then resolved=${resolved%/*}; else resolved=; fi
                continue;;
        esac
        candidate="$target/${resolved:+$resolved/}$part"
        if [[ -L $candidate ]]; then
            links=$((links+1))
            ((links<=40)) || { echo 'Target symlink loop' >&2; return 1; }
            link=$(readlink "$candidate")
            if [[ $link == /* ]]; then resolved=; link=${link#/}; fi
            pending="$link${pending:+/$pending}"
        else
            resolved="${resolved:+$resolved/}$part"
        fi
    done
    printf '%s/%s\n' "$target" "$resolved"
}

declare -A copied=()
copy_dependency()
{
    local name=${1#/} source destination magic metadata interpreter library prefix found
    [[ -z ${copied[$name]:-} ]] || return 0
    source=$(resolve_target "$name")
    [[ -f $source ]] || { echo "Missing initramfs dependency: $name" >&2; return 1; }
    destination="$root/$name"
    mkdir -p "$(dirname "$destination")"
    cp --preserve=mode "$source" "$destination"
    copied[$name]=1
    magic=$(od -An -tx1 -N4 "$source" | tr -d ' \n')
    [[ $magic == 7f454c46 ]] || return 0
    metadata=$("$readelf" -lW -dW "$source")
    interpreter=$(sed -n 's/.*Requesting program interpreter: \([^]]*\)].*/\1/p' <<< "$metadata")
    [[ -z $interpreter ]] || copy_dependency "$interpreter"
    while IFS= read -r library; do
        [[ -n $library ]] || continue
        found=false
        for prefix in lib usr/lib lib64 usr/lib64; do
            source=$(resolve_target "$prefix/$library")
            if [[ -f $source ]]; then copy_dependency "$prefix/$library"; found=true; break; fi
        done
        $found || { echo "Missing ELF library: $library" >&2; return 1; }
    done < <(sed -n 's/.*(NEEDED).*\[\([^]]*\)\].*/\1/p' <<< "$metadata")
}

for name in bin/busybox usr/sbin/fwctl etc/device-manager/firmware.conf usr/share/udhcpc/default.script; do
    copy_dependency "$name"
done
[[ ! -f "$target/etc/fw_env.config" ]] || copy_dependency etc/fw_env.config
config="$root/etc/device-manager/firmware.conf"
signature=$(sed -n 's/^require-signature=//p' "$config")
if [[ $signature == true ]]; then
    key=$(sed -n 's/^signature-key=//p' "$config")
    [[ $key == /* ]] || { echo 'Signature key must be absolute' >&2; exit 1; }
    copy_dependency "$key"
    copy_dependency usr/bin/fit_check_sign
fi
busybox=$(resolve_target bin/busybox)
for folder in bin sbin usr/bin usr/sbin; do
    for entry in "$target/$folder"/*; do
        [[ -L $entry ]] || continue
        resolved=$(resolve_target "$folder/${entry##*/}")
        if [[ $resolved == "$busybox" && ! -e "$root/$folder/${entry##*/}" && ! -L "$root/$folder/${entry##*/}" ]]; then
            ln -s /bin/busybox "$root/$folder/${entry##*/}"
        fi
    done
done
for name in sbin/ip sbin/ifconfig sbin/route sbin/udhcpc; do
    [[ -e "$root/$name" || -L "$root/$name" ]] || ln -s /bin/busybox "$root/$name"
done
for name in etc/ssl/certs/ca-certificates.crt etc/ssl/cert.pem; do
    source=$(resolve_target "$name")
    [[ ! -f $source ]] || copy_dependency "$name"
done
cp "$board/recovery.interfaces" "$root/etc/network/interfaces"
cp "$board/recovery.conf" "$root/etc/fw-recovery.conf"
chmod 0644 "$root/etc/fw-recovery.conf"
: > "$root/etc/resolv.conf"
cp "$scripts/initramfs-init" "$root/init"
chmod 0755 "$root/init"
for name in bin/sh sbin/switch_root sbin/ifup sbin/ifdown; do
    [[ -L "$root/$name" ]] || { echo "Required BusyBox applet missing: $name" >&2; exit 1; }
done
"$scripts/archive-initramfs.sh" "$root" "$output"
printf 'initramfs: %s (%s bytes, %s dependencies)\n' "$output" "$(stat -c %s "$output")" "${#copied[@]}"

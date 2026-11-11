#!/bin/bash
# Development-host deployment only; never write the board's local partitions.
set -euo pipefail
images=$(realpath "$1"); shift
root=/srv/nfs/am625
tftp=/srv/tftp/am625
client=192.168.10.211
check_only=0
sync_existing=0
preserve=()
while (($#)); do
    case "$1" in
        --check) check_only=1; shift; continue;;
        --sync) sync_existing=1; shift; continue;;
        --preserve) preserve+=("$2"); shift 2; continue;;
        --nfs-root) root=$2;; --tftp-root) tftp=$2;; --client) client=$2;;
        *) echo "Unknown deployment option: $1" >&2; exit 2;;
    esac
    shift 2
done
for relative in "${preserve[@]}"; do
    [[ -n $relative && $relative != /* && $relative != . && /$relative/ != */../* &&
       $relative != *[!A-Za-z0-9_./-]* ]] || { echo 'Invalid preserved relative path' >&2; exit 1; }
done
[[ $client =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
IFS=. read -r -a octets <<< "$client"
for octet in "${octets[@]}"; do ((${#octet}<=3 && 10#$octet<=255)); done
for path in "$root" "$tftp"; do
    [[ $path == /* && $path != *[[:space:],]* ]] || { echo 'Use absolute export paths without whitespace or commas' >&2; exit 1; }
done
[[ ! -L $root ]] || { echo 'NFS root must not be a symlink' >&2; exit 1; }
root=$(realpath -m "$root")
tftp=$(realpath -m "$tftp")
[[ $root != / && $tftp != / && $images != "$root" && $images != "$root/"* &&
   $tftp != "$root" && $tftp != "$root/"* && $root != "$tftp/"* ]] || {
    echo 'NFS root, TFTP directory and build inputs must be separate' >&2; exit 1;
}
jq="$images/../host/bin/jq"
[[ -x $jq ]] || jq=$(command -v jq)
manifest="$images/netboot/manifest.json"
# Buildroot deliberately builds host-jq without Oniguruma. Use jq for JSON
# structure only; Bash validates identifiers and hashes without that dependency.
"$jq" -e '.format=="BSP-NETBOOT-1" and (.dtb|type=="string") and
    (.reference_build|type=="string") and (.sha256|type=="object") and
    ((.sha256|keys|sort)==(["netboot/Image",("netboot/"+.dtb),"netboot/build.conf","rootfs.tar"]|sort)) and
    (.sha256|all(.[];type=="string"))' "$manifest" >/dev/null
dtb=$("$jq" -r .dtb "$manifest")
[[ $dtb =~ ^[A-Za-z0-9_-][A-Za-z0-9_.-]*\.dtb$ ]] || { echo 'Invalid DTB filename' >&2; exit 1; }
reference=$("$jq" -r .reference_build "$manifest")
[[ $reference =~ ^BSPNET1\ [0-9]+\ [0-9a-f]{64}$ ]] || { echo 'Invalid network reference record' >&2; exit 1; }
while IFS=$'\t' read -r name expected; do
    [[ $expected =~ ^[0-9a-f]{64}$ ]] || { echo "Invalid artifact checksum: $name" >&2; exit 1; }
    actual=$(sha256sum "$images/$name" | cut -d ' ' -f 1)
    [[ $actual == "$expected" ]] || { echo "Artifact checksum mismatch: $name" >&2; exit 1; }
done < <("$jq" -r '.sha256|to_entries[]|[.key,.value]|@tsv' "$manifest")
[[ $(cat "$images/netboot/build.conf") == "$reference" ]] || { echo 'Network reference file differs from manifest' >&2; exit 1; }
[[ $(tar -xOf "$images/rootfs.tar" ./etc/bsp/netboot.conf) == "$reference" ]] || { echo 'Rootfs reference differs from manifest' >&2; exit 1; }
if ((check_only)); then
    printf 'Verified TFTP/NFS artifacts: %s\n' "$reference"
    exit 0
fi
((EUID==0)) || { echo 'Run as root to preserve numeric rootfs ownership' >&2; exit 1; }
[[ ! -e $root || ( -d $root && ( $sync_existing == 1 || -z $(find "$root" -mindepth 1 -maxdepth 1 -print -quit) ) ) ]] || {
    echo 'NFS destination must be empty; stop the board and archive the previous root first' >&2; exit 1;
}
[[ -x /usr/sbin/exportfs ]] || { echo 'Install nfs-kernel-server first' >&2; exit 1; }
command -v flock >/dev/null || { echo 'Install util-linux first' >&2; exit 1; }
if ((sync_existing)); then
    command -v rsync >/dev/null || { echo 'Install rsync first' >&2; exit 1; }
fi
mkdir -p "$root" "$tftp"
exec {lock_fd}>"${root}.sync.lock"
flock -n "$lock_fd" || { echo 'Another deployment owns this NFS root' >&2; exit 1; }
if ((sync_existing)); then
    stage=$(mktemp -d "$(dirname "$root")/.netboot-sync.XXXXXXXX")
    trap 'rm -rf -- "$stage"' EXIT HUP INT TERM
    tar --numeric-owner -xpf "$images/rootfs.tar" -C "$stage"
    options=(-aH --numeric-ids --checksum --delete)
    for relative in "${preserve[@]}"; do options+=("--exclude=/$relative"); done
    rsync "${options[@]}" "$stage/" "$root/"
else
    tar --numeric-owner -xpf "$images/rootfs.tar" -C "$root"
fi
[[ $(cat "$root/etc/bsp/netboot.conf") == "$reference" ]]
for name in Image "$dtb"; do
    install -m 0644 "$images/netboot/$name" "$tftp/$name.new"
    mv "$tftp/$name.new" "$tftp/$name"
done
mkdir -p /etc/exports.d
printf '%s %s(rw,sync,no_root_squash,no_subtree_check)\n' "$root" "$client" > "/etc/exports.d/bsp-netboot-${client//./-}.exports"
systemctl enable --now nfs-server.service
/usr/sbin/exportfs -ra
printf 'TFTP: %s\nNFS: %s; allowed client: %s\n' "$tftp" "$root" "$client"

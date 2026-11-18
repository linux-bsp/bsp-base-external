#!/bin/sh
set -eu

board=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT HUP INT TERM
export CAN_TEST_LOG="$fixture/ip.log"
cat > "$fixture/ip" <<'IP'
#!/bin/sh
printf '%s\n' "$*" >> "$CAN_TEST_LOG"
IP
chmod +x "$fixture/ip"
cat > "$fixture/classic.conf" <<CONFIG
[can]
interfaces=lo
classic-interfaces=lo
bitrate=500000
data-bitrate=2000000
ip=$fixture/ip
CONFIG
sh "$board/rootfs-overlay/usr/libexec/bsp/can" start "$fixture/classic.conf"
grep -Fxq 'link set dev lo type can bitrate 500000 restart-ms 100 fd off' "$CAN_TEST_LOG"
: > "$CAN_TEST_LOG"
sed 's/classic-interfaces=lo/classic-interfaces=/' "$fixture/classic.conf" > "$fixture/fd.conf"
sh "$board/rootfs-overlay/usr/libexec/bsp/can" start "$fixture/fd.conf"
grep -Fxq 'link set dev lo type can bitrate 500000 restart-ms 100 dbitrate 2000000 fd on' "$CAN_TEST_LOG"
: > "$CAN_TEST_LOG"
sed 's/classic-interfaces=lo/classic-interfaces=not-managed/' "$fixture/classic.conf" > "$fixture/invalid.conf"
if sh "$board/rootfs-overlay/usr/libexec/bsp/can" start "$fixture/invalid.conf"; then
    exit 1
fi
test ! -s "$CAN_TEST_LOG"

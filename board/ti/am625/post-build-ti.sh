#!/bin/sh -x

dtb_file=""

while [ $# -gt 0 ]; do
	case "$1" in
		-d)
			# Check if the next argument exists and is not another flag
			if [ -n "$2" ] && [ "${2#-}" = "$2" ]; then
				dtb_file="$2"
				shift
			else
				echo "Error: Missing or invalid filename after -d flag"
				exit 1
			fi
			;;
		*)
			;;
	esac
	shift
done

if [ -n "$dtb_file" ]; then
	echo "dtb file provided : $dtb_file"
else
	echo "No dtb file provided with -d flag"
	exit 1
fi

# For raw format, firmware files still need to be in rootfs
mkdir -p $TARGET_DIR/lib/firmware/ti-connectivity

cp $BUILD_DIR/ti-k3-boot-firmware-*/ti-ipc/am62xx/am62-mcu-m4f0_0-fw $TARGET_DIR/lib/firmware/
cp $BUILD_DIR/ti-k3-boot-firmware-*/ti-connectivity/* $TARGET_DIR/lib/firmware/ti-connectivity/

ln -snf /run/dropbear "$TARGET_DIR/etc/dropbear"

# Optional upstream Python frontends are not part of this native-only target.
# Keep the C/C++ GDB and Valgrind tools; omit their unconfigured Python helpers.
rm -f "$TARGET_DIR"/usr/lib/libstdc++.so.*-gdb.py \
    "$TARGET_DIR/usr/libexec/valgrind/valgrind-monitor.py" \
    "$TARGET_DIR/usr/libexec/valgrind/valgrind-monitor-def.py" \
    "$TARGET_DIR/usr/bin/valgrind-monitor"

# Incremental Buildroot overlays retain files deleted from the board source.
rm -f "$TARGET_DIR/usr/bin/debugctl" || exit 1
board_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
for old in device-manager/firmware.conf device-manager/health.conf \
    device-manager/recovery.conf device-manager/sol.conf device-manager/storage.conf \
    device-manager/time.conf default/fwctl default/fwctld default/can \
    edk/psatellited.conf edk/ptelemetryd.conf edk/bmc.password edk/bmc.password.example \
    edk/supermicro-bmc.password edk/supermicro-bmc.password.example \
    libbmc/devices.conf libbmc/xfusion.password.example libbmc/supermicro.password.example \
    libbmc/xfusion.password libbmc/supermicro.password; do
    [ ! -e "$TARGET_DIR/etc/$old" ] || unlink "$TARGET_DIR/etc/$old" || exit 1
done
rmdir "$TARGET_DIR/etc/libbmc" 2>/dev/null || :
rmdir "$TARGET_DIR/etc/device-manager" 2>/dev/null || :

# Real device credentials are provisioned after image installation.
for name in xfusion supermicro; do
    secret="$TARGET_DIR/etc/edk/credentials/$name.password"
    [ ! -e "$secret" ] || unlink "$secret" || exit 1
done

# Reject malformed service scripts before creating any rootfs image.
for init_script in "$TARGET_DIR"/etc/init.d/* \
    "$TARGET_DIR"/usr/libexec/bsp/* "$TARGET_DIR"/usr/libexec/device-manager/*; do
    [ -f "$init_script" ] || continue
    IFS= read -r first_line < "$init_script" || continue
    case "$first_line" in
        '#!/bin/sh'*)
            sh -n "$init_script" || {
                echo "Invalid init script: $init_script" >&2
                exit 1
            }
            ;;
    esac
done

# Validate actual installed service entry points, including target-root symlinks.
"$HOST_DIR/bin/cmake" -DROOTFS="$TARGET_DIR" \
    -P "$board_dir/../../../../edk/scripts/cmake/check_install.cmake" || exit 1

"$board_dir/../../../support/scripts/netboot-build.sh" "$TARGET_DIR" \
    "$BINARIES_DIR/Image.gz" "$BINARIES_DIR/$dtb_file" \
    "$board_dir/../../../../edk/VERSION" || exit 1

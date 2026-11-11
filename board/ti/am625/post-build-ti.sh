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

# The initramfs and rootfs maintenance tool use the same board recovery settings.
board_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
install -D -m 0644 "$board_dir/recovery.conf" \
    "$TARGET_DIR/etc/device-manager/recovery.conf" || exit 1

# Remove paths used before BMC configuration was consolidated under
# /etc/libbmc. Buildroot overlays do not remove deleted source files from an
# incremental target directory.
rm -f \
	"$TARGET_DIR/etc/edk/bmc.password" \
	"$TARGET_DIR/etc/edk/bmc.password.example" \
	"$TARGET_DIR/etc/edk/supermicro-bmc.password" \
	"$TARGET_DIR/etc/edk/supermicro-bmc.password.example"

# Credentials are local overlay inputs. Force safe permissions in the image
# even when the developer's source file was created with a permissive umask.
for password_file in \
	"$TARGET_DIR/etc/libbmc/xfusion.password" \
	"$TARGET_DIR/etc/libbmc/supermicro.password"
do
	[ ! -f "$password_file" ] || chmod 0600 "$password_file"
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

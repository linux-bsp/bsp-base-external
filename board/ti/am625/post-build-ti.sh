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

# S10pdm owns CAN-dependent PDM lifecycle. Clean the obsolete incremental overlay.
rm -f "$TARGET_DIR/etc/modules-load.d/pdm.conf"

# Reject malformed service scripts before creating any rootfs image.
for init_script in "$TARGET_DIR"/etc/init.d/*; do
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

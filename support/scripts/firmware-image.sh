#!/bin/sh

set -eu

die()
{
	echo "firmware-image: $*" >&2
	exit 1
}

usage()
{
	echo "Usage: $0 <binaries-dir> -c <genimage-config>" >&2
	exit 2
}

[ "$#" -eq 3 ] || usage
BINARIES_DIR="$1"
[ "$2" = "-c" ] || usage
GENIMAGE_CFG="$3"

[ -d "${BINARIES_DIR}" ] || die "missing binaries directory: ${BINARIES_DIR}"
[ -f "${GENIMAGE_CFG}" ] || die "missing genimage config: ${GENIMAGE_CFG}"

CONFIG_DIR="$(CDPATH= cd -- "$(dirname -- "${GENIMAGE_CFG}")" && pwd)"
GENIMAGE_CFG="${CONFIG_DIR}/$(basename -- "${GENIMAGE_CFG}")"
MKIMAGE="${HOST_DIR}/bin/mkimage"
PATH="${HOST_DIR}/bin:${HOST_DIR}/sbin:${PATH}"
export PATH
RELEASE_TEMPLATE="${CONFIG_DIR}/release.its.in"
MEDIA_CFG="${CONFIG_DIR}/genimage_sdcard.cfg"

[ -x "${MKIMAGE}" ] || die "mkimage is not available"

if [ -z "${FW_DTB_FILE:-}" ] && [ -n "${BR2_CONFIG:-}" ]; then
	DTB_LIST="$(sed -n "s#^BR2_LINUX_KERNEL_INTREE_DTS_NAME=\"\(.*\)\"\$#\1#p" "${BR2_CONFIG}")"
	set -- ${DTB_LIST}
	if [ "$#" -gt 0 ]; then
		FW_DTB_FILE="$(basename -- "$1").dtb"
		export FW_DTB_FILE
	fi
fi

# Keep the original kernel DTB intact for network/debug boots.
if grep -q '"rootfs-verity.squashfs"' "${GENIMAGE_CFG}"; then
    [ -n "${FW_DTB_FILE:-}" ] || die "FW_DTB_FILE is required for verity"
    cp "${BINARIES_DIR}/${FW_DTB_FILE}" "${BINARIES_DIR}/verity-${FW_DTB_FILE}"
    FW_DTB_FILE="verity-${FW_DTB_FILE}"
    export FW_DTB_FILE
    "$(dirname -- "$0")/rootfs-verity.sh" "${HOST_DIR}"         "${BINARIES_DIR}/rootfs.squashfs" "${BINARIES_DIR}/rootfs-verity.squashfs"         "${BINARIES_DIR}/${FW_DTB_FILE}"
fi

# Independent PID 1, tools and ELF dependencies are built from finalized TARGET_DIR.
if grep -q '"recovery.cpio.gz"' "${GENIMAGE_CFG}"; then
    "${HOST_DIR}/bin/python3" "$(dirname -- "$0")/build-recovery-initramfs.py" \
        --target "${TARGET_DIR}" --host "${HOST_DIR}" \
        --board "${CONFIG_DIR}/.." --output "${BINARIES_DIR}/recovery.cpio.gz"
fi

ITS_LIST="$(sed -n "s#^[[:space:]]*its[[:space:]]*=[[:space:]]*\"\([^\"]*\)\".*#\1#p" "${GENIMAGE_CFG}" | sort -u)"
FW_BUILD_TIME_MINUTES="$(($(date +%s) / 60))"

for ITS_PATH in ${ITS_LIST}; do
	ITS_SOURCE="${CONFIG_DIR}/$(basename -- "${ITS_PATH}")"
	ITS_OUTPUT="${BINARIES_DIR}/${ITS_PATH}"
	[ -f "${ITS_SOURCE}" ] || die "missing ITS file: ${ITS_SOURCE}"
	mkdir -p "$(dirname -- "${ITS_OUTPUT}")"
	sed "s/@FW_BUILD_TIME_MINUTES@/${FW_BUILD_TIME_MINUTES}/g" \
		"${ITS_SOURCE}" >"${ITS_OUTPUT}"
done

PATH="${HOST_DIR}/bin:${HOST_DIR}/sbin:${PATH}" GENIMAGE_MKIMAGE="${MKIMAGE}" support/scripts/genimage.sh -c "${GENIMAGE_CFG}"

# A recovery ramdisk must still fit in the fixed kernel slot.
if [ -f "${BINARIES_DIR}/recovery.cpio.gz" ]; then
    [ "$(stat -c %s "${BINARIES_DIR}/release/kernel.itb")" -le 25165824 ] || die "kernel FIT exceeds 24 MiB slot"
fi

if [ -f "${RELEASE_TEMPLATE}" ]; then
    RELEASE_ITS="${BINARIES_DIR}/release/release.its"
    "${HOST_DIR}/bin/python3" "$(dirname -- "$0")/firmware-identity.py"         --host "${HOST_DIR}" --images "${BINARIES_DIR}"         --template "${RELEASE_TEMPLATE}" --output "${RELEASE_ITS}"
	if ! "${MKIMAGE}" -f "${RELEASE_ITS}" \
		"${BINARIES_DIR}/release/release.itb"; then
		rm -f "${RELEASE_ITS}"
		die "failed to create release.itb"
	fi
	rm -f "${RELEASE_ITS}"
fi

if [ -f "${MEDIA_CFG}" ]; then
    if grep -q '"uboot-env0.bin"' "${MEDIA_CFG}"; then
        "${HOST_DIR}/bin/python3" "$(dirname -- "$0")/hwid-env-factory.py" \
            --input "${TARGET_DIR}/etc/u-boot-initial-env" --output "${BINARIES_DIR}"
    fi
	PATH="${HOST_DIR}/bin:${HOST_DIR}/sbin:${PATH}" support/scripts/genimage.sh -c "${MEDIA_CFG}"
fi

for ITS_PATH in ${ITS_LIST}; do
	rm -f "${BINARIES_DIR}/${ITS_PATH}"
done

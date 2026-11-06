# BSP Base External

This repository provides the reusable BSP base external tree.
Its Buildroot identifier remains `LINUX_BSP`, so existing
`BR2_EXTERNAL_LINUX_BSP_PATH` references remain valid.

The external tree contains the Alientek AM62x board configuration, image
layout, root filesystem files, and the EDK and libbmc packages.

From the BSP workspace root:

```sh
make -C buildroot BR2_EXTERNAL=../bsp-base-external alientek_am62x_defconfig
make -C buildroot
```

The board defconfig is `configs/alientek_am62x_defconfig`. Board files are under
`board/ti/am625/`; its `local.mk` selects workspace copies of Linux, U-Boot,
EDK, and libbmc. The post-image script in
`support/scripts/firmware-image.sh` creates the RAW A/B firmware components
and SD card image from `board/ti/am625/layout/`.

The board defconfig builds its own GCC 15/glibc toolchain. It does not
require a preinstalled SDK.

## Standalone AM62x SDK

`configs/am62x_sdk_defconfig` builds an AArch64 GCC 15/glibc SDK with Linux
7.0 headers, C++ support, cross GDB with Python, and `environment-setup`.
It does not enable a kernel, bootloader, board applications, or rootfs images.
Use a separate output tree so the board configuration is preserved:

```sh
export BR2_DL_DIR="$HOME/workspaces/dl"
make -C buildroot O="$PWD/output/am62x-sdk" \
  BR2_EXTERNAL=../bsp-base-external am62x_sdk_defconfig
make -C output/am62x-sdk sdk
```

Buildroot writes `aarch64-buildroot-linux-gnu_sdk-buildroot.tar.gz` under
`output/am62x-sdk/images/`. Extract it manually into `$HOME/workspaces/toolchain/`
and run the extracted `relocate-sdk.sh` before using the SDK. Keep each SDK
version in a separate directory; do not overlay an existing installation.
The original `make sdk` target is used without an additional install target.
Linux 7.0 headers match this workspace's kernel; older target kernels need
a separately configured SDK with suitable headers. This is not an i.MX6ULL SDK.

## OTA publication, automatic updates and recovery

The C `device-server` in the `edk/user/apps/device-manager/` module provides a web interface to upload,
review, and publish firmware releases. The standalone C `ota-cli` provides
HTTP upload, publication, and status queries from an SSH terminal. Devices poll, download, and verify the
published release, install it with `fwctl`, reboot, and report the result after
boot health confirmation when automatic installation is enabled. U-Boot can
request the exact kernel version from the same server to repair a damaged slot.
See [the Device Manager guide](../edk/user/apps/device-manager/README.md) for build, publication, device
configuration, and test commands. The AM62x configuration includes `fwctld`.
Package defaults leave it disabled; the AM625 board overlay supplies the development
server and enables polling. Review `/etc/default/fwctld` and persistent overrides
before deployment.

## AM625 独立恢复环境

板级构建已接入 [initramfs + rootfs A/B](board/ti/am625/verified-boot.md)，包含完整性检查、备用 deployment 回退和按内容哈希恢复 rootfs。

Build host tools with `make -C buildroot O="$PWD/output/am625" host-edk` from the workspace. The package installs `device-server` and `ota-cli` under `output/am625/host/bin/`. Target-side firmware, logging and time tools are selectable outputs of the edk package. Host tools are selected through host-edk.

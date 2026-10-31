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
export BR2_DL_DIR="$HOME/workspace/dl"
make -C buildroot O="$PWD/output/am62x-sdk" \
  BR2_EXTERNAL=../bsp-base-external am62x_sdk_defconfig
make -C output/am62x-sdk sdk
```

Buildroot writes `aarch64-buildroot-linux-gnu_sdk-buildroot.tar.gz` under
`output/am62x-sdk/images/`. Extract it manually into `$HOME/workspace/toolchain/`
and run the extracted `relocate-sdk.sh` before using the SDK. Keep each SDK
version in a separate directory; do not overlay an existing installation.
The original `make sdk` target is used without an additional install target.
Linux 7.0 headers match this workspace's kernel; older target kernels need
a separately configured SDK with suitable headers. This is not an i.MX6ULL SDK.

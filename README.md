# TI AM62x Buildroot External Tree

This external tree contains the Alientek AM62x board configuration, image
layout, root filesystem files, and the EDK and bmctool packages.

From the BSP workspace root:

```sh
make -C buildroot BR2_EXTERNAL=../br2-external alientek_am62x_defconfig
make -C buildroot
```

The board defconfig is `configs/alientek_am62x_defconfig`. Board files are under
`board/ti/am625/`; its `local.mk` selects workspace copies of Linux, U-Boot,
EDK, and bmctool. The post-image script in
`support/scripts/firmware-image.sh` creates the RAW A/B firmware components
and SD card image from `board/ti/am625/layout/`.

The defconfig expects an AArch64 GCC 14 Buildroot SDK at
`/opt/buildroot/aarch64-ca53-linux-gnu_sdk-buildroot`. Change the toolchain
path in the defconfig or install that SDK before building.

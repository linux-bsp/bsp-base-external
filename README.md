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

## Shared TFTP/NFS boot support

Network boot is a BSP capability, available without `sadboard-external`.
AM625 U-Boot exposes independent `CONFIG_AM62X_BOOT_TFTP_KERNEL` and
`CONFIG_AM62X_BOOT_NFS_ROOT` options. The base defconfig disables both;
`board/ti/am625/uboot/netboot.config` enables both and can be supplied through
`BR2_TARGET_UBOOT_CONFIG_FRAGMENT_FILES` by any product profile.

| `tftp_kernel` | `nfs_root` | Kernel / root filesystem |
| --- | --- | --- |
| 0 | 0 | Verified local A/B FIT, initramfs and rootfs |
| 1 | 0 | TFTP Image/DTB and directly mounted local SquashFS |
| 0 | 1 | Verified local FIT, skipping initramfs, and NFS root |
| 1 | 1 | TFTP Image/DTB and NFS root |

In U-Boot set `ipaddr`, `serverip`, `gatewayip`, `netmask`,
`tftp_kernel_file`, `tftp_fdt_file`, `nfsroot`, `nfsopts`, `netdev` and
`net_hostname` for the site. The default export is `/srv/nfs/am625`.
Use `run fw_boot` after selecting the switches; `saveenv` is optional for
temporary tests. Installing a newly built U-Boot is required to change its
compiled defaults. Saved network addresses and paths survive schema migration.

The standard board post-build hook calls `support/scripts/netboot-build.sh`.
The firmware post-image hook exports the uncompressed kernel, DTB, reference
record and checksum manifest into `images/netboot/`, paired with `rootfs.tar`.
Check the candidate without changing files or needing root:

```sh
bsp-base-external/support/scripts/deploy-netboot.sh output/am625/images --check
```

This also verifies the reference record inside `rootfs.tar`. Only after this
passes, stop use of the previous NFS root, archive it and deploy to an empty,
dedicated host directory:

```sh
sudo bsp-base-external/support/scripts/deploy-netboot.sh \
  output/am625/images --nfs-root /srv/nfs/am625 \
  --tftp-root /srv/tftp/am625 --client 192.168.10.211
```

Add `--sync` to update an existing NFS root with staged extraction and
`rsync --checksum --delete`, retaining the root directory itself. Repeat
`--preserve RELATIVE_PATH` for runtime data that must survive synchronization.
Keep the board on its local rootfs or powered off during a full sync. The host
needs rsync and util-linux; a per-root lock prevents simultaneous deployments.
SadBoard's `scripts/sync-artifacts.sh` supplies its default paths, preserved
experiment results, optional laboratory payloads and local sudo authentication.

The shared `board/common/rootfs-overlay` must precede the board/product
overlays. It supplies `/usr/libexec/bsp/boot-context` and systemd policy for
`bsp.netboot=1`. Network boots skip production OTA and local A/B confirmation;
readiness checks persistent `/data` and units in `/etc/bsp/netboot-health.conf`
plus optional `netboot-health.d/*.conf`. Local boots delegate to the normal
firmware confirmation service. `/etc/bsp/netboot.conf` contains
`BSPNET1 <numeric-version> <full-SHA256>`; it identifies the reference build,
not an immutable NFS tree or the local flash contents. This is a development
boot path, with different integrity guarantees from the production boot path.

To port this support, provide the new board's boot commands, overlays and
kernel/DTB/version inputs to the same native hooks. The AM625 commands use
ARM64 `booti`; other architectures need their corresponding boot command.

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

The C `dmserver` in the `edk/user/apps/device-manager/` module provides a web interface to upload,
review, and publish firmware releases. The C `dmcli ota` subcommands provide
HTTP upload, publication, and status queries from a terminal. Devices poll, download, and verify the
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

Build host tools with `make -C buildroot O="$PWD/output/am625" host-edk` from the workspace. The package installs `dmserver` and `dmcli` under `output/am625/host/bin/`. Target-side firmware, logging and time tools are selectable outputs of the edk package. Host tools are selected through host-edk.

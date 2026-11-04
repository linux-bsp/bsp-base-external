# Alientek AM62x Board Files

`configs/alientek_am62x_defconfig` selects the Alientek AM62x device tree,
kernel and U-Boot configurations, BusyBox configuration, root filesystem
overlay, and local source overrides in this directory.

[firmware.json](firmware.json) 是固件打包的统一板级配置，包含版本、HWID、架构、
各组件输入文件、加载地址、initramfs、verity 和默认升级组件。
构建器自动生成四份 ITS，并调用 mkimage 生成 bootloader、kernel、rootfs 和 release ITB。
ITS 保存在构建输出中供检查，不需要维护板级 ITS 或组件 genimage 配置。

## 配置与构建

- 调整版本、HWID、输入镜像及加载地址：修改 `firmware.json`。
- 软件版本默认保持 `0.0.1`；内容 ID 和组件 SHA256 在构建时自动计算。
- `images` 描述实际输入；架构默认继承顶层 `architecture`，R5 镜像可单独指定 `arm`。
- `release.components` 当前为 kernel/rootfs；上传后服务端按包内全部 HWID 发布。
- `factory.layout` 指定独立的物理存储布局，当前为 `layout/genimage_sdcard.cfg`。

在已配置的 workspace 输出目录执行：

```sh
make -C buildroot O="$PWD/output/am625" all
```

首次配置使用 `alientek_am62x_defconfig`。旧输出目录升级构建流程时，将 `.config` 中
`BR2_ROOTFS_POST_IMAGE_SCRIPT_ARGS` 更新为
`-c $(BR2_EXTERNAL_LINUX_BSP_PATH)/board/ti/am625/firmware.json`，保留其余工具链配置。

构建产物包括 `images/firmware.json`（已解析配置）、`firmware-identity.json`、
`release/*.its`、`release/*.itb` 和工厂镜像。设备自身 HWID 由 U-Boot 环境保存。

字段、模块和测试命令见 [统一固件生成器](../../../support/firmware/README.md)。

The image contains two 64 KiB metadata copies, two 24 MiB kernel slots, and
two 128 MiB root filesystem slots. The first stage bootloader occupies the
start of the SD card, so interrupted updates to slot A can require reflashing.

The Redfish endpoint `192.168.10.201` is configured in
`rootfs-overlay/etc/edk/ptelemetryd.conf`. Set its `username`, create
`/etc/libbmc/xfusion.password` on the target with the password on the first line
(mode 0600), then set `[daemon] enabled = true` to start telemetry collection.
Keep credentials out of the repository.

The pdebug web debugger is enabled through `BR2_PACKAGE_EDK_WEB`, using lighttpd
at port 8080. Open `http://192.168.10.211:8080/` and enter the board's runtime
access key from `cat /run/pdebug-web/token`. The key changes after reboot unless
a private root-owned mode-0600 `/etc/edk/pdebug-web.token` is supplied. The CGI
executes the installed pdebug with bounded arguments/output/time and reads fixed
log sources; it does not execute shell command lines. Configuration/startup is
in `rootfs-overlay/etc/lighttpd/lighttpd.conf` and `etc/init.d/S50lighttpd`.
Use this endpoint on the development network. Select a device from the actual
PDM inventory to display MCU, LED, Satellite or Power controls. Selection does
not execute peripheral commands; power outputs are never enabled automatically.

`bmc-test` reads its multi-device inventory from
`rootfs-overlay/etc/libbmc/devices.conf`. The image currently contains xFusion
and Supermicro profiles with independent Redfish/IPMI endpoints, usernames,
password-file paths, timeouts, and protocol flags. Select one with
`bmc-test --device-id <id>`. Local password files under
`rootfs-overlay/etc/libbmc/` are ignored by Git; the corresponding `.example`
files document their expected names.

## 分阶段固件验证

正常 eMMC 启动的 FIT 校验、dm-verity 镜像生成和上板验证见 [分阶段完整性验证](verified-boot.md)。

- [v1.0.16 OTA 验证记录](releases/v1.0.16.md)
- [v0.0.1 / 4a7e87c2 OTA 验证记录](releases/v0.0.1-4a7e87c2.md)
- [v0.0.1 / e993e58c OTA 验证记录](releases/v0.0.1-e993e58c.md)
- [v0.0.1 / 6cee5c9d OTA 验证记录](releases/v0.0.1-6cee5c9d.md)
- [v0.0.1 / 5ad4aa1e OTA 验证记录](releases/v0.0.1-5ad4aa1e.md)
- [v0.0.1 / 64373f72 公共 HWID 配置验证](releases/v0.0.1-64373f72.md)
- [v0.0.1 / 07071f2d 统一 JSON 生成固件验证](releases/v0.0.1-07071f2d.md)

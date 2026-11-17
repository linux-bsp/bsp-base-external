# Alientek AM62x Board Files

`configs/alientek_am62x_defconfig` selects the Alientek AM62x device tree,
kernel and U-Boot configurations, BusyBox configuration, root filesystem
overlay, and local source overrides in this directory.

[firmware.json](firmware.json) 是固件打包的统一板级配置，包含版本、HWID、架构、
各组件输入文件、加载地址、initramfs、verity 和默认升级组件。
构建器自动生成四份 ITS，并调用 mkimage 生成 bootloader、kernel、rootfs 和 release ITB。
ITS 保存在构建输出中供检查，不需要维护板级 ITS 或组件 genimage 配置。

## 配置与构建

- 调整 HWID、输入镜像及加载地址：修改 `firmware.json`。
- EDK 与设备固件共用 `edk/VERSION`，当前为 `0.0.1`；JSON 引用此文件，
  Buildroot 的 target/host EDK 包也读取同一来源。内容 ID 和组件 SHA256
  在构建时自动计算，同版本的不同内容使用 hash ID 区分。
- `images` 描述实际输入；架构默认继承顶层 `architecture`，R5 镜像可单独指定 `arm`。
- `release.components` 当前为 kernel/rootfs；上传后服务端按包内全部 HWID 发布。
- `factory.layout` 指定独立的物理存储布局，当前为 `layout/genimage_sdcard.cfg`。

在已配置的 workspace 输出目录执行：

```sh
make -C buildroot O="$PWD/output/am625" all
```

首次配置选择 alientek_am62x_defconfig；已有定制工具链输出目录直接构建，保留其配置。

构建产物包括 `images/firmware.json`（已解析配置）、`firmware-identity.json`、
`release/*.its`、`release/*.itb` 和工厂镜像。设备自身 HWID 由 U-Boot 环境保存。

字段、模块和测试命令见 [统一固件生成器](../../../support/firmware/README.md)。

The image contains two 64 KiB metadata copies, two 24 MiB kernel slots, and
two 128 MiB root filesystem slots. The first stage bootloader occupies the
start of the SD card, so interrupted updates to slot A can require reflashing.

Device Manager diagnostics use `BR2_PACKAGE_EDK_DEBUG` and `dm-debug.socket`
on port 8080. Open the management server on port 8090 and select Device Debug.
The device endpoint calls PDI operations through `dmcli`; it serves no web pages
and requires no lighttpd. Use `dmcli debug --local help` for local validation.
Hardware controls require explicit confirmation in the web form. See
`edk/docs/device-manager/debug.md` for API, timeout and deployment boundaries.

`bmc-test` reads its multi-device inventory from
`rootfs-overlay/etc/libbmc/devices.conf`. The image currently contains xFusion
and Supermicro profiles with independent Redfish/IPMI endpoints, usernames,
password-file paths, timeouts, and protocol flags. The xFusion endpoint is
`192.168.50.201`; Supermicro is `192.168.10.252`. Redfish uses HTTPS.
Select one with
`bmc-test --device-id <id>`. Local password files under
`rootfs-overlay/etc/libbmc/` are ignored by Git; the corresponding `.example`
files document their expected names.

## 固件验证与历史

启动完整性、独立 initramfs 和 rootfs A/B 见 [恢复说明](verified-boot.md)。
当前基线以 workspace 的 docs/am62x/edk-module-refactoring-validation.md 为准，
旧版本身份与验收边界集中在 [历史发布记录](releases/README.md)。

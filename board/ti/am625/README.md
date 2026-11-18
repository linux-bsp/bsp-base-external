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

`rootfs-overlay/etc/edk/bmc.conf` lists xFusion and Supermicro BMC profiles.
Provision password files under `/data/edk/credentials/` on the device.
The board installs `bmc.conf`, `satellite.conf` and `system.conf` in `/etc/edk/`.
The initramfs uses the firmware and recovery sections from the same system configuration.

## 固件验证与历史

启动完整性、独立 initramfs 和 rootfs A/B 见 [恢复说明](verified-boot.md)。
当前基线以 workspace 的 docs/am62x/edk-module-refactoring-validation.md 为准，
旧版本身份与验收边界集中在 [历史发布记录](releases/README.md)。

## 切换星务协议

AM625 固件编入 T5000 和 021，出厂配置使用 T5000，systemd 按 CAN、EDK
执行器、星务入口的依赖启动。切换 021 时在同一个 `/etc/edk/satellite.conf`
中设置 `[link] protocol = 021-rk3588-v3.0.2`、两个独立的
`interface` / `interface_b`、交付的 12 位十六进制 `oid` 和
`session_file`。会话文件由部署初始化为一行 `0`，放在持久文件系统。
`[can] interfaces` 列出本服务管理的总线，`classic-interfaces` 列出其中
用 Classic CAN 的总线。对 021 的两条总线配置 500 kbit/s 并加入该列表。
通用镜像默认使用 OS 遥测。接入经确认的本地 MCU 后按项目设置
`[telemetry] mcu_enabled = true`。采用原 T5000 MCU 遥测载荷的项目可设置
`os_enabled = false` 保持原有慢遥测容量。

Alientek 设备树中的 `main_mcu` 使用第一个板载 CAN 控制器的 CAN FD。
如果两个板载控制器均用于 021 Classic CAN，配置
`[telemetry] mcu_enabled = false` 并停用这条本地 MCU 的诊断或控制。
如需同时使用 CAN FD MCU 和 021，BSP 应提供与 MCU 总线独立的两条
Classic CAN 链路，或将本地 MCU 部署在不同的外设后端。

# Alientek AM62x Board Files

`configs/alientek_am62x_defconfig` selects the Alientek AM62x device tree,
kernel and U-Boot configurations, BusyBox configuration, root filesystem
overlay, and local source overrides in this directory.

`layout/genimage_ti.cfg` builds the bootloader, kernel, and root filesystem
FIT components. `support/scripts/firmware-image.sh` then creates a release
manifest and uses `layout/genimage_sdcard.cfg` for the RAW A/B SD image.

## 固件支持的 HWID

统一修改板级 [firmware.json](firmware.json)：

```json
{
    "hwids": ["1010001000110000"]
}
```

支持多个硬件时，在同一个 `hwids` 数组中增加完整的 16 字符小写 HWID。
构建脚本一次读取配置，统一生成 release、bootloader、kernel、rootfs 的
`fw,hwids` 属性。四份 ITS 模板只保留 `@FW_HWIDS@` 占位符，无需逐份修改。
缺失、空白、重复、无效 HWID 或模板遗漏占位符都会使构建失败。

重新运行现有输出目录的 `make all` 即可重新打包，不需要重新应用 defconfig。
构建产物中的 `images/firmware.json` 保存本次实际使用的配置，供追溯。
OTA server 上传后解析 FIT 的声明，自动按整份列表发布。
设备自身的 HWID 由 U-Boot 环境提供，普通 OTA 保持该身份。

配置与模板测试：

```sh
python3 support/scripts/tests/test-firmware-templates.py
```

测试环境需要 PATH 中提供 `dtc`、`fdtget`，可使用 Buildroot 的 host/bin。

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

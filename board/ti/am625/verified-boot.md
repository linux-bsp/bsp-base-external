# AM625 initramfs 与 rootfs A/B 恢复

## 启动与恢复流程

正常 eMMC 启动采用 `U-Boot → kernel FIT → /init 脚本 → fwctl init → dm-verity → switch_root → 正式系统`。
恢复环境在 RAM 中运行，PDM、业务服务和磁盘上的 rootfs 都不是它的前提。

1. U-Boot 按 deployment 读取 kernel FIT，验证 kernel、设备树和 recovery ramdisk 的哈希。
2. `fw verity-args` 验证参数并确认 FIT 包含 ramdisk，设置 `rdinit=/init`。
   环境 schema 为 7；正常启动不再通过 `dm-mod.create` 提前创建根映射。
3. initramfs 中的 脚本 `/init` 执行 `/usr/sbin/fwctl init` 挂载运行时文件系统，维护看门狗，
   从 `fwctl recovery status` 获取本次启动的 deployment 与 rootfs 槽。
4. 完整读取当前 rootfs 的有效 payload（SquashFS 数据、对齐填充、verity 哈希树），
   比较 kernel FIT 设备树中绑定的 SHA256。分区尾部未使用空间不参与比较。
5. 校验通过后，fwctl 通过 device-mapper ioctl 建立只读 verity 设备，挂载到 `/newroot`，
   移交 `/dev`、`/proc`、`/sys`、`/run`，使用 BusyBox `switch_root` 启动正式 `/sbin/init`。
   后续读取仍由 dm-verity 检查；读错误或损坏会重启，下一次启动重新完整检查。
6. 校验失败时先调用 `fwctl recovery fallback`。只有另一 deployment 已确认、内核完整、
   且包含恢复 ramdisk 和 rootfs 身份信息时才切换，并重启加载另一套内核/rootfs。
   当前故障 deployment 标为 failed，避免两槽之间不断往返。
7. 没有合格备用 deployment 时，配置网络，向 OTA server 请求**准确内容**的 rootfs FIT，
   校验后修复当前未挂载的损坏 rootfs 槽。修复完成再次全量校验，然后正常挂载与切根。

恢复不自动初始化丢失或损坏的 A/B metadata，也不将“写入完成”当作业务健康。
待确认升级仍由正式系统的健康检查与 S99fw-mark-good 确认；PDM 和其他业务服务在切根后启动。
工厂镜像虽然写了两个 rootfs 分区，未在 metadata 中注册为已确认 deployment 的槽不会直接作为回退目标。

## 镜像与构建

- `recovery.cpio.gz`：fwctl、BusyBox、curl、必要 ELF 依赖和恢复配置。
  不包含 PDM 模块、业务进程或完整 rootfs。
- `rootfs-verity.squashfs`：4096 字节对齐的 rootfs 数据，后接 SHA256 哈希树，无 verity superblock。
- `verity-<原DTB>`：保存 root hash、salt、数据/哈希块数，以及完整 payload 的长度和 SHA256。
  它作为 kernel FIT 中的 fdt image 受到哈希校验。原始 DTB 保留用于调试。
- `release/kernel.itb`：包含 kernel、设备树和 recovery ramdisk，必须小于固定 24 MiB 内核槽。
- `release/rootfs.itb`：封装完整 verity payload，写入现有 128 MiB rootfs 槽。
- `sdcard.img`：包含配套 bootloader、kernel A/B 和 rootfs A/B 的工厂镜像。

构建流程没有 rootfs 包含 initramfs 的循环依赖：先生成 rootfs，再生成 RAM 恢复包与 FIT。
打包器解析 ELF 动态依赖，不执行目标架构程序；cpio 采用 root 所有者、固定时间戳并直接描述设备节点，无需宿主 root 权限。
若 firmware.conf 配置签名校验，恢复包同时包含验证工具与配置的公钥文件。

```sh
# workspace 根目录；首次配置使用标准板级 defconfig
make -C buildroot O="$PWD/output/am625" alientek_am62x_defconfig
make -C buildroot O="$PWD/output/am625" all
```

恢复入口已纳入 `BR2_PACKAGE_DEVICE_MANAGER_FWCTL=y`；initramfs 仍需 BusyBox、curl 和 OpenSSL。
内核内置 initrd/gzip、device-mapper、dm-verity、SHA256；不依赖磁盘模块来挂载根文件系统。
已有自定义 `.config` 应保留其设置，启用新选项后重新配置 linux、device-manager 和 U-Boot。
生成文件默认位于 `output/am625/images/`。

## 恢复配置与服务器

编辑板级 `recovery.conf` 设置服务器、产品、布局、网卡和 A/B 根设备。
当前开发默认服务器为 `http://192.168.10.246:8090`，网卡为 eth0；网络地址来自板级
`rootfs-overlay/etc/network/interfaces`，随 initramfs 一起打包，无法依赖损坏 rootfs 中的新配置。
修改这些配置需要重新生成 kernel FIT。普通 rootfs 中 fwctld 的启用配置与 initramfs 恢复配置独立。

恢复请求为：

```text
GET /recovery/<product>/<layout>/rootfs/<payload-sha256>/rootfs.itb
```

服务器仅从已发布历史中选择产品、布局和实际 payload 哈希匹配的包；找不到返回 404，
不会拿最新版本代替。发布历史应保留仍在运行的固件。服务端需要部署本次包含 rootfs 恢复接口的版本。
上传草稿但不发布，不会使该包进入恢复候选集。

设备恢复时继续验证包格式、产品、布局、组件类型、rollback index、payload 长度与哈希，
写入后逐块读回比较。此处是 initramfs 中对未挂载损坏槽的原位修复，不改变 kernel、另一槽或 metadata。
断电后 kernel/initramfs 仍可启动，再次检查并重试。常规 OTA 仍通过备用 deployment 安装完整版本。

网络或恢复包暂不可用时每 30 秒重试，下载有超时和大小限制；不会挂载损坏 rootfs。
配置、metadata 或已校验镜像本身不可用时停止自动启动并提供串口恢复 shell。
硬件存储永久故障无法靠重写修复。网络重试期间没有新增后台登录服务。

## 运行与验证

正常串口日志应包含独立 initramfs 启动、rootfs 完整校验，以及 `switch_root` 提示。
进入正式系统后查看：

```sh
cat /proc/cmdline
cat /proc/mounts
cat /run/fw-init.verified
fwctl version
```

启动参数应包含 `rdinit=/init` 和 `fw.verity=1`；实际 `/` 挂载自 verity 映射，不能仅依据
启动参数中的 `root=/dev/ram0` 判断切根是否成功。`/run/fw-init.verified` 仅表示启动完整性检查通过，
不表示业务健康确认或 OTA 成功。看门狗在切根后交由 system_manager；nowayout 平台关闭恢复阶段句柄时可能打印未停止提示。

```sh
python3 bsp-base-external/support/fw-recovery/tests/test-recovery.py
python3 bsp-base-external/support/fw-recovery/tests/test-fit-integrity.py
python3 uboot/u-boot-2026.04/test/py/tests/test_am62x_boot_env.py
HOST_DIR="$PWD/output/am625/host" python3 uboot/u-boot-2026.04/test/py/tests/test_fw_verity.py
make -C bsp-base-external/support/ota-server test
```

主机测试覆盖：真实 FIT 的 ramdisk 损坏与缺失、真实 rootfs FIT 在临时存储中的精确修复、
其他槽与 metadata 保留、全量数据/哈希树校验、短读、错误哈希、PID 1 保护和 initramfs 依赖与确定性。
EDK 12 项、U-Boot 环境 11 项、verity 3 项、恢复程序 5 项、真实 FIT/修复 2 项、
U-Boot sandbox 固件命令及 8 项 metadata 测试已通过；临时 OTA 服务的真实包上传/发布/恢复下载测试通过。

AM625 内核、U-Boot/SPL 和完整镜像已构建。尚未在实体板执行 PID 1、device-mapper ioctl、
切根、看门狗交接和断电恢复验证；这也是下一步验收重点。只在可恢复的测试槽中注入损坏。
本次是开发构建，未给当前在线设备发布，默认 FIT 版本字段未自动递增。

## 调试入口与信任边界

TFTP 原始 kernel/DTB 和 NFS 是显式调试入口。使用 FIT 内核搭配 NFS 时，U-Boot 用
`bootm <地址> -` 跳过恢复 ramdisk，避免生产恢复流程抢占网络根文件系统。
生产升级需把 kernel FIT 和 rootfs 作为配套产物更新，并使用配套 U-Boot。

当前未完成硬件信任根、生产签名密钥和防篡改启动环境部署；内容哈希不能替代完整安全启动。
PDM 只在正式系统内参与设备监测，不负责从不可挂载的 rootfs 中恢复自身。

## 内容身份与版本标签设计

当前使用 kernel FIT 和 rootfs 有效载荷的长度、SHA-256 组成规范化清单，再计算
SHA-256 作为 firmware ID。产品和布局作为独立字段校验；发布编号、tar 包装和压缩
参数不参与内容 ID。组件自身内嵌的时间戳改变仍属于固件内容改变。

`v1.0.0` 等 tag 用于展示，firmware ID 用于内容识别。同 tag 但内容不同仍视为不同
固件；不同发布编号可以指向同一内容。实际 flash 校验必须重算内容哈希，不能只读
保存的 ID。显式强制恢复可重装完全相同的固件。数字 FIT 版本和 rollback index
继续保留，内容哈希不承担版本排序。

参考：[Linux initramfs](https://docs.kernel.org/filesystems/ramfs-rootfs-initramfs.html)、
[Linux dm-verity](https://docs.kernel.org/admin-guide/device-mapper/verity.html)、
[U-Boot Verified Boot](https://docs.u-boot-project.org/en/latest/usage/fit/verified-boot.html)。

## 1.0.11 实机启动故障与修复验证

1.0.11 的 FIT 哈希校验成功，但 `/init` 在动态加载阶段找不到 `libcrypto.so.3`，
PID 1 以 127 退出，触发 `Attempted to kill init`。库实际位于 `/usr/lib`，打包器遗漏
Buildroot 的 `/lib64 -> lib` 和 `/usr/lib64 -> lib`，而 ARM64 加载器默认搜索这些别名。
修复保留这两个目录链接；仅检查 ELF `NEEDED` 对应文件存在不足以验证启动。

新增真实 ARM64 加载器测试（QEMU user，无需设备写入）：

```sh
python3 bsp-base-external/support/fw-recovery/tests/test-loader.py \
  --qemu /path/to/qemu-aarch64 \
  --image output/am625/images/recovery.cpio.gz
```

测试禁止依赖主机库路径或 ld.so.cache，执行 fwctl init、curl 和 BusyBox
完整依赖。移除库目录别名必须复现 exit 127；原始 1.0.11 包可加 `--expect-broken`。
这验证动态加载与入口程序，不替代 AM625 上 PID 1、watchdog、dm-verity 和 switch_root 的完整启动验证。

本次实机已确认失败版本在启动重试耗尽后回到 1.0.10，随后设备上报 `rolled-back`。
全局异常固件停发、正常版本重新发布及审计策略见 [OTA 服务说明](../../../support/ota-server/README.md#异常停发回退发布与审计)。


## 固件身份跨阶段传递与元数据扩展

最终 kernel FIT 和 rootfs 分区有效载荷生成后，打包器计算内容 ID，写入
`release.itb` 和 `images/firmware-identity.json`。tag 从 FIT 版本值生成，格式为
`v<major>.<minor>.<patch>`；ID 是内容 SHA-256，不是 Git 源码提交号。它覆盖 kernel
FIT（含内核、设备树、恢复 initramfs）和 rootfs 有效载荷，不包含 bootloader。
ID 不嵌入被计算的镜像本体，避免自引用；FIT 时间戳变化也会使内容 ID 改变。

完整 release 安装会验证声明的 ID、tag、各组件长度与哈希，在写入读回验证成功后，
将身份与目标 deployment 一起提交。单独替换 kernel/rootfs 会使整机身份失效；
单独升级 bootloader 保留原 kernel/rootfs 身份。工厂 `sdcard.img` 同时写入
`meta0.bin`、`meta1.bin`，因此首次启动不依赖空白元数据自动初始化。

U-Boot 校验所选 kernel 的实际内容，向运行时设备树 `/chosen` 写入 `fw,tag`、
`fw,id`、`fw,deployment`，并打印版本。Kernel、恢复 initramfs、rootfs 的
`fwctl version` 和 PDM 使用同一身份。PDM 的 EDK 版本仍单独展示。
`fwctl` 根据本次启动的 deployment 读取身份，核对设备树快照，避免下载新固件后
把 pending deployment 误报成当前运行版本。网络启动或缺少身份的旧记录不猜测版本。

```sh
fwctl identity                  # 当前运行固件的 tag、ID 前 8 位、deployment
fwctl identity initramfs        # 相同身份，标注为恢复阶段
fwctl version                   # 固件身份及各组件状态
```

元数据分区仍为双 64 KiB，偏移保持不变；记录从 128 B 扩展到 4096 B。
前 128 B 保留启动头和 CRC，扩展区保存两套部署身份，末尾 CRC 覆盖整个记录。
头部扩展标记防止只写入前 128 B 的断电记录被当作合法旧记录。读写仍使用双副本、
序列号及写后读回验证，新增哈希字段也受 CRC 保护。

旧记录可读取，但显示 `identity=unknown`。旧 SPL 只写旧格式，会丢失扩展信息；
启用本功能需要同步更新 R5 SPL、A53 SPL 和 U-Boot，不能仅升级 kernel/rootfs。
升级 bootloader 不替代固件身份的建立，旧部署仍须安装包含身份的完整 release。

本地验证命令：

```sh
cmake --build output/edk-shutdown-tests
ctest --test-dir output/edk-shutdown-tests --output-on-failure
python3 bsp-base-external/support/fw-recovery/tests/test-identity.py
python3 bsp-base-external/support/fw-recovery/tests/test-fit-integrity.py
python3 uboot/u-boot-2026.04/test/py/tests/test_fw_verity.py
```

`test-identity.py` 需要当前 AM625 镜像、host 工具及 `output/uboot-ota-sandbox/u-boot`，
在临时模拟介质中验证工厂记录及 EDK → U-Boot → EDK 互读，不写开发板。
FIT 内嵌设备树可能只有 4 字节对齐，解析前复制到满足 libfdt 要求的地址；测试覆盖
两种对齐，避免 ramdisk 大小变化导致正常固件被拒绝。
这些本地测试不替代 AM625 实机的首次启动、A/B 升级、掉电与回滚验证。

启动日志中的固件 ID 与 FIT 哈希仅显示前 8 位；元数据、设备树、OTA 协议和内容比较仍使用完整 SHA-256。initramfs 在根分区设备节点出现前等待探测，不提前调用 `fwctl recovery status`。合法旧元数据缺少身份时输出 identity=unknown (legacy metadata) 并正常返回；元数据不可读、损坏或身份不一致仍报错。

# AM625 固件校验与 rootfs A/B 恢复

## 启动链

当前 AM625 SD 启动使用 U-Boot → kernel FIT → /init → fwctl init → dm-verity →
switch_root → systemd。恢复环境在 RAM 中运行，不以 PDM、业务服务或磁盘 rootfs 为前提。
initramfs 是 FIT 内的 ramdisk，不是独立物理分区。

1. U-Boot 根据 deployment 选择 kernel 槽，校验 FIT、组件和已记录内容身份。
2. FIT 包含 kernel、DTB 与恢复 initramfs；/init 脚本执行 /usr/sbin/fwctl init。
3. fwctl 等待存储探测，读取本次启动的 deployment 和 rootfs 槽，维护看门狗。
4. 完整读取 rootfs 有效 payload（SquashFS、填充与 verity 树），核对 kernel DTB
   绑定的长度和 SHA256；分区尾部未使用空间不参与比较。
5. 校验通过后建立只读 dm-verity 映射，挂载 /newroot、移交运行目录并 switch_root。
6. 校验失败时检查可回退的已确认 deployment；没有有效备用时联网请求精确恢复包，
   修复未挂载的损坏 rootfs，读回并再次校验后启动。

恢复不自动初始化丢失的 metadata，也不将写入完成当作业务健康。正式系统由
fw-health/fw-confirm 完成本地确认，fwctld 上报 OTA 结果。备用 rootfs 检查和必要修复
在健康确认后执行。网络不可用不阻断已有有效部署的本地启动与回退。

## 镜像和配置

- initramfs.cpio.gz：fwctl、BusyBox、动态库依赖及恢复配置；HTTP 下载调用共享传输库。
- rootfs-verity.squashfs：4096 字节对齐的根文件系统和 SHA256 哈希树。
- verity-<DTB>：保存 root hash、salt、块数和 payload 长度/SHA256。
- release/kernel.itb：kernel、DTB、initramfs，受当前 24 MiB 槽大小约束。
- release/rootfs.itb：完整 verity payload，受当前 128 MiB 槽大小约束。
- sdcard.img：配套引导程序、A/B 组件和初始 metadata 的工厂镜像。

firmware.json 是打包配置来源；构建先生成 rootfs，再生成 initramfs 和 FIT，避免循环依赖。
JSON 与启动侧物理布局独立维护，打包门禁核对它们的一致性，不在线迁移已部署分区。
恢复功能由 BR2_PACKAGE_EDK_FWCTL 选择，内核必须内置所需存储、initrd、dm-verity 和摘要支持。

recovery.conf 保存恢复服务器、网卡和 root-a/root-b。设备 HWID 从环境读取；
网卡初始配置随 initramfs 打包，不依赖损坏 rootfs。修改这些板级输入需要重建 kernel FIT。
构建命令与配置字段见 [板级说明](README.md)、[固件生成器](../../../support/firmware/README.md)。

## 精确恢复与身份

```text
/recovery/<HWID>/kernel/<version>/<firmware-id>/kernel.itb
/recovery/<HWID>/rootfs/<version>/<firmware-id>/<payload-sha256>/rootfs.itb
```

恢复源必须匹配 HWID、版本与完整内容 ID；rootfs 还匹配有效载荷摘要。服务器只从
可用的已发布内容选包；草稿、已删除、隔离或缺失内容不能充当恢复源。找不到不使用
最新版替代。设备继续校验 FIT、组件、长度、哈希与写后读回结果。

firmware ID 由 kernel FIT 和 rootfs 有效 payload 的规范化长度/摘要生成，不是 Git
提交号，不包含 bootloader。tag 用于展示，默认 v0.0.1；同 tag 内容变化仍是不同固件。
ID 不嵌入被计算的负载本体，避免自引用。元数据、DTB、下载与审计保留完整 SHA256，
普通日志只显示前八位。CRC 保护 metadata 记录，不能替代内容哈希或签名。

当前冗余 metadata 分区各 64 KiB，记录为 4096 B，包含头部、部署身份和 CRC。
SPL/U-Boot 与 Linux 必须使用匹配的格式。工厂镜像写初始 metadata，正常 OTA 不做工厂初始化。
运行身份来自实际启动 deployment，不把刚暂存的 pending 误当成当前系统。

## 板端检查

```sh
cat /proc/1/comm
cat /proc/cmdline
cat /proc/mounts
cat /run/fw-init.verified
fwctl identity
fwctl version
fwctl health-check
systemctl --failed
```

/run/fw-init.verified 证明早期完整性校验通过，不表示 OTA 已成功。正常 rootfs 使用
verity 映射，不能只根据启动参数中的 root= 判断切根结果。切根后由 systemd 接管看门狗。
AM625 当前实机记录以 SD 为准；eMMC/NOR、真实断电和硬件信任根需各自验证。
ROM 固定从 tiboot3 A 进入，kernel/rootfs OTA 不升级或验证 SPL/U-Boot。

## 依赖与恢复验证

实际 ARM64 动态加载器验证用于发现库目录链接遗漏，避免 PID 1 因缺库退出：

```sh
python3 bsp-base-external/support/fw-recovery/tests/test-loader.py \
  --qemu /path/to/qemu-aarch64 --image output/am625/images/initramfs.cpio.gz
```

测试执行 fwctl 与 BusyBox 并验证 ELF 依赖；保留 /lib64、/usr/lib64 等所需链接。
仅检查文件存在不能证明加载成功。该测试不替代板上 PID 1、watchdog 和切根验证。
BSP 的 test-recovery.py、test-fit-integrity.py、test-storage-identity.py 与 test-identity.py
验证临时介质、包身份和元数据互读；参数和构建产物需指向本次镜像。

操作命令见 workspace 的 [固件升级指南](../../../../docs/am62x/firmware-upgrade-guide.md)，
当前验收见 [EDK 重构验收](../../../../docs/am62x/edk-module-refactoring-validation.md)。
早期发布证据集中在 [历史发布](releases/README.md)。

# 历史固件发布记录

以下保留原发布身份、验证结果和证据位置，属于历史记录。原文中的目录、
命令和阶段限制反映当时状态；当前构建与操作以仓库 README 和现行指南为准。


## 记录索引

- [v0.0.1-07071f2d](#v0.0.1-07071f2d)
- [v0.0.1-2596cdd9](#v0.0.1-2596cdd9)
- [v0.0.1-2b6b68fc](#v0.0.1-2b6b68fc)
- [v0.0.1-3a94b4a0](#v0.0.1-3a94b4a0)
- [v0.0.1-3c9f1f8b](#v0.0.1-3c9f1f8b)
- [v0.0.1-4a7e87c2](#v0.0.1-4a7e87c2)
- [v0.0.1-5ad4aa1e](#v0.0.1-5ad4aa1e)
- [v0.0.1-5fa96eb8](#v0.0.1-5fa96eb8)
- [v0.0.1-64373f72](#v0.0.1-64373f72)
- [v0.0.1-6aa757f6](#v0.0.1-6aa757f6)
- [v0.0.1-6cee5c9d](#v0.0.1-6cee5c9d)
- [v0.0.1-b0ff0766](#v0.0.1-b0ff0766)
- [v0.0.1-b4304330](#v0.0.1-b4304330)
- [v0.0.1-e993e58c](#v0.0.1-e993e58c)
- [v1.0.16](#v1.0.16)


<a id="v0.0.1-07071f2d"></a>

## v0.0.1 / 07071f2d 统一固件生成验证

原记录：`bsp-base-external/board/ti/am625/releases/v0.0.1-07071f2d.md`。


验证日期：2026-11-04。AM625 SD 实机：`192.168.10.211`，HWID `1010001000110000`。

### 变更

[firmware.json](../firmware.json) 统一描述版本、HWID、架构、镜像输入、加载地址、
恢复 initramfs、verity、升级组件和工厂布局入口。板级四份手写 ITS、组件 genimage
配置和占位符展开器已移除；`support/firmware/` 直接生成标准 ITS，再调用 mkimage 生成 ITB。

版本保持 `v0.0.1`；完整内容 ID：

```text
07071f2d8b2d48d9a70ba299eb16ec4a7737d38d7c28e0cb0c59101f987d8cd9
```

### 验证

- 10 项生成器测试通过：真实 mkimage 输出、公共版本/HWID/回滚索引、引用关系、
  64 位地址、ARMv7 描述省略 ATF/initramfs、大小限制、错误配置与输入拒绝。
- 完整工厂镜像构建通过；14 处引导程序、元数据、环境、kernel/rootfs 双槽映射逐字节比对一致。
- 4 项实际 FIT 测试通过：设备端 C 引擎解析 release 和全部组件，验证内容 ID、组件哈希、
  根文件系统恢复、initramfs 哈希及错误 HWID 拒绝。
- 8 项 OTA CLI 测试通过，包含本次真实固件的上传、发布、下载和恢复地址验证。
- 设备自动下载安装 kernel/rootfs A 槽，重启后 rootfs 全量校验、dm-verity、启动健康检查通过，
  OTA server 收到发布记录 52 的 `success`。
- B 槽保留上一健康固件；bootloader 未重新烧写。ARMv7 测试只验证生成格式，不代表其他板卡已实测。

构建、工厂映射、测试、成功快照、串口日志和源码审计产物位于 workspace 的
`output/ota-validation/0.0.1-json-firmware/`。生成的四份 ITS 与 ITB 保留在该目录的 `images/release/`。


<a id="v0.0.1-2596cdd9"></a>

## v0.0.1 / 2596cdd9 SOL 与持久化支持验证

原记录：`bsp-base-external/board/ti/am625/releases/v0.0.1-2596cdd9.md`。


- 完整内容 ID：`2596cdd993fa874338ff4c0d8d21fcf23a9fe0af7290e93bf31cdd9e4c07cfd2`，tag 固定 `v0.0.1`，服务端发布记录 21。
- 设备 `1c-63-49-22-c4-f7` 已安装 kernel/rootfs、重启、通过健康检查并上报 success，deployment 1。对应源码在该结果之后提交。
- 日志转发由独立子进程执行，带设备凭据校验、服务器持久化游标、重试去重、启动及阶段回放。Web 支持实时查看、筛选、导出；这是只读日志通道，不提供远程 shell。
- 每台设备最近 4 次启动、2048 个上传块（最多约 8 MiB 原始日志）；本地和服务器均有限额。长期断网超过本地保留范围的数据可能丢失。
- 设备密钥不在固件包中，需要单独配置。缺少密钥时后台等待，不阻塞本地采集或健康确认。本次没有完成实机 SOL 上传验收。
- 按用户随后要求，实验服务临时启用 `--sol-open-view`，浏览器免凭据查看；设备上传仍验证凭据。此项只改主机服务，不改变已发布固件。
- `logctl verify-storage` 同步当前启动标记并检查先前启动标记；`logctl verify-boot` 检查 R5 SPL、A53 SPL、U-Boot 经内核验证后的快照。
- 新工厂镜像在 320 MiB data 起点增加 256 MiB 空 ext4；A/B 偏移不变。OTA 不写 data，不格式化已有设备。
- 测试：SOL HTTP/上传器 9 项（含凭据隔离、免查看凭据模式、去重、重启/断网续传、容量限制、独立凭据就绪等待）；日志 7 项；引导记录协议 3 项；既有 OTA 回归通过，真实包项单独执行。ARM64 CLI、initramfs ELF 加载、存储身份、FIT/恢复/元数据对齐、真实包上传下载均通过。
- Chromium 验证带凭据和免凭据查看、日志文字安全渲染、筛选、移动布局及 OTA 原有流程；data.ext4 的 e2fsck -fn 和工厂镜像超块偏移检查通过。
- **实机范围仅 kernel/rootfs OTA。** 当前服务器未连接 AM625 串口；新引导程序未刷写，SPL/U-Boot 交接及 /data 跨重启/断电可靠性均未判为通过。
- TFTP：`/srv/tftp/am625/sol-2596cdd9/`，含引导升级包、原始引导文件、kernel/rootfs/release 和 SHA256SUMS。完整工厂镜像在本次输出目录的 `images/sdcard.img`。
- 产物、源码快照、校验与审计：`output/ota-validation/0.0.1-sol-r2/`。首次未发布构建因独立打包 PATH 缺少 host/sbin 失败，修正后使用新的目录重建；未将失败候选发布。

```text
1793622771 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 21 1 bf3814bf-10b6-411d-b308-e160e72ba6ae installing 1 1 none
1793622775 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 21 1 bf3814bf-10b6-411d-b308-e160e72ba6ae rebooting 1 1 none
1793622810 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 21 1 bf3814bf-10b6-411d-b308-e160e72ba6ae boot-testing 1 1 none
1793622840 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 21 1 bf3814bf-10b6-411d-b308-e160e72ba6ae success 1 1 none
```


<a id="v0.0.1-2b6b68fc"></a>

## v0.0.1 / 2b6b68fc initramfs 命名统一

原记录：`bsp-base-external/board/ti/am625/releases/v0.0.1-2b6b68fc.md`。


验证日期：2026-11-04。AM625 SD 实机：`192.168.10.211`，HWID `1010001000110000`。

### 变更

Kernel FIT 的 ramdisk 节点、说明和配置引用统一使用 `initramfs`，镜像文件使用
`initramfs.cpio.gz`。JSON 的生成类型改为 `initramfs`，对应脚本改为
`support/scripts/build-initramfs.py`，入口模板改为 `support/scripts/initramfs-init`。
入口安装为 `/init`，继续执行 `fwctl init`；恢复功能及 `fwctl recovery` 命令保持原有用途。

initramfs 随 kernel FIT 存放，没有增加物理分区，也没有修改设备的分区布局或启动环境。
配置校验、生成器、测试和现行文档已同步更新；历史发布记录保留原始内容。

版本保持 `v0.0.1`，完整内容 ID：

```text
2b6b68fcac8e5d9e5e0b7ad0fc9902c4b6904de93c2522194933e57518b966cf
```

### 验证

- 10 项 JSON/FIT 生成器测试、6 项 initramfs/恢复逻辑测试、4 项实际 FIT 校验测试通过。
- QEMU user 执行实际 ARM64 fwctl、curl、BusyBox，通过动态库依赖及缺失别名回归检查。
- 工厂镜像生成成功；15 个区域与对应引导程序、元数据、环境、Kernel/Rootfs 及 data 镜像逐字节一致。
- OTA 发布记录 53：设备自动安装到 Kernel/Rootfs B 槽，重启后服务器收到 `success`。
- 串口确认 `Trying 'initramfs' ramdisk subimage`，Rootfs SHA256、dm-verity、switch_root
  和启动健康检查通过；A 槽保留此前健康固件。
- 本次未烧写 Bootloader，实机验证范围为现有 Bootloader 加载新 FIT 及系统正常启动。

构建、测试、固件、源码快照、工厂区域映射、成功上报和串口证据位于 workspace 的
`output/ota-validation/0.0.1-initramfs-naming/`。


<a id="v0.0.1-3a94b4a0"></a>

## v0.0.1 / 3a94b4a0 Device Manager 验证记录

原记录：`bsp-base-external/board/ti/am625/releases/v0.0.1-3a94b4a0.md`。


### 版本和设备

- Tag：`v0.0.1`（数值 1）。完整内容 ID：`3a94b4a08254fbb16abc05406f84146ff53294dd3167ff8deb357faab5fee393`。
- 服务端发布记录：20；设备 `1c-63-49-22-c4-f7`，IP `192.168.10.211`，MAC `1c:63:49:22:c4:f7`，hostname `am625`。
- 安装事务启动 ID：`62a57dee-6a57-4c51-aeff-d53b67e9f21a`；重启后的启动 ID：`bf3814bf-10b6-411d-b308-e160e72ba6ae`。
- 设备在 2026-11-02 19:17:33 +08:00 上报 success，deployment 0、running version 1。服务端目录和 SQLite 将发布记录 20 绑定到上述完整内容 ID。对应源码在此成功结果后提交。

### 改动

- 独立 device-manager 仓库接管 device-server、ota-cli、fwctl、fwctld、logctl、logctld；EDK 仅保留外设管理，不再提供固件库。
- bsp-base-external 提供独立设备包及 host-device-server 包；配置迁移到 `/etc/device-manager/firmware.conf`。
- 管理页面增加 OTA/SOL 侧栏；SOL 入口明确标注尚未接入。当前固件按钮改为“当前版本使用中”。
- logctld 按启动归档内核、服务、initramfs 与已接入的引导程序日志，限制容量并保留 pstore。
- SPL/U-Boot 使用独立保留内存交接，Linux 校验记录后导出 sysfs 快照；引导程序已编译并完成主机协议测试。

### 验证与边界

- 完整 AM625 镜像及 R5 SPL/A53 SPL/U-Boot 编译通过。
- 日志生命周期 6 项、引导缓存协议 3 项、独立固件引擎 5 项、EDK 外设 8 项测试通过。
- OTA 回归 88 项（通用测试跳过真实包项，随后使用本次包单独验证通过）；另有 ARM64 存储身份 7 项、initramfs ELF 加载、FIT/恢复/对齐、工厂元数据与真实上传下载验证。
- Chromium 验证 OTA 操作、详情、筛选、标签页保持、SOL 导航及移动布局。
- 实机已验证 kernel/rootfs OTA、重启和健康确认。**未安装新 SPL/U-Boot，未验证引导日志接力，也未验证 /data 跨重启持久化。** 不将这两项记为通过。
- 工厂镜像未格式化 data 分区；启动只尝试挂载现有 ext4，失败则日志落到 RAM 并告警。不会自动格式化。
- 无 SSH 依赖；网络 SOL 传输尚未实现。ROM/TIFS/ATF、任意交互 shell 和未接入服务的输出不承诺收集。
- 原始产物、源码 SHA256 快照、测试日志及设备审计位于 `output/ota-validation/0.0.1-device-manager-bootlog/`。原始快照保留不覆盖；补充记录说明文档清理和旧生成文件删除，固件生产源码未改变。

### 服务端接收的设备历史

```text
1793618186 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 20 1 62a57dee-6a57-4c51-aeff-d53b67e9f21a installing 0 1 none
1793618191 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 20 1 62a57dee-6a57-4c51-aeff-d53b67e9f21a rebooting 0 1 none
1793618223 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 20 1 62a57dee-6a57-4c51-aeff-d53b67e9f21a boot-testing 0 1 none
1793618253 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 20 1 62a57dee-6a57-4c51-aeff-d53b67e9f21a success 0 1 none
```


<a id="v0.0.1-3c9f1f8b"></a>

## v0.0.1 / 3c9f1f8b 串口格式 SOL 验证

原记录：`bsp-base-external/board/ti/am625/releases/v0.0.1-3c9f1f8b.md`。


- 完整固件 ID：`3c9f1f8b00819adcd9dcd16cb70bb46a040942f835804a10e263731cb1931382`；tag 保持 `v0.0.1`，发布记录 23。
- 设备 `1c-63-49-22-c4-f7` 已完成 kernel/rootfs OTA、重启及健康确认，deployment 1；启动 ID `08e25a95-78fd-4884-bd1d-23e8b66130fc`。收到 success 后提交代码。
- 日志采集改为带字节长度的记录，保留半行、原始空白和程序自己的前缀，不给网络分块额外补换行；归档仍包含序号和采集时间。
- SOL 正文去除阶段、seq/mono/wall、source 标签，内核记录显示原生秒/微秒时间戳。内部 events 可单独筛选，长行横向滚动，导出与当前视图一致。
- 旧归档兼容读取；其已补入的换行无法可靠撤销。initramfs 缓存按阶段放在 rcS 之前；跨来源排序只尽力还原，不能替代物理 UART 逐字节记录。
- 日志采集 8 项、格式回归 9 项、SOL HTTP/续传 10 项测试通过。Chromium 临时环境桌面/移动端和真实设备网页验证通过；实机确认 `Starting CAN: OK` 同行且没有传输前缀。
- ARM64 initramfs 加载、固件身份/恢复/FIT、真实 OTA 包传输、工厂元数据和 DTB 对齐检查通过。
- 服务器仍以免凭据调试模式运行；本次未刷写 SPL/U-Boot，旧引导阶段缓存仍不可用。设备 data 未配置，存储仍为 volatile，不计为持久化通过。
- 产物、测试、截图、正文导出、源码快照与设备事务保存在 `output/ota-validation/0.0.1-sol-console/`。发布后的最后调整仅涉及主机页面 initramfs 排序及测试/说明，设备固件源码没有变化。

```text
1793625966 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 23 1 ea0359d4-f55b-4dc6-94fa-87589ad2f83f installing 1 1 none
1793625970 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 23 1 ea0359d4-f55b-4dc6-94fa-87589ad2f83f rebooting 1 1 none
1793626010 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 23 1 ea0359d4-f55b-4dc6-94fa-87589ad2f83f boot-testing 1 1 none
1793626025 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 23 1 ea0359d4-f55b-4dc6-94fa-87589ad2f83f success 1 1 none
```


<a id="v0.0.1-4a7e87c2"></a>

## v0.0.1 / 4a7e87c2 OTA 验证记录

原记录：`bsp-base-external/board/ti/am625/releases/v0.0.1-4a7e87c2.md`。


- 发布编号：#14；固件版本固定为 `v0.0.1`（数值 1），后续仅在用户明确要求时修改 tag。
- 设备：`1c-63-49-22-c4-f7`；目标 deployment：0；服务器已接受重启后的 `success`。
- 修改：fwctld 在后台等待 eth0 链路和 IP 就绪后再检查 OTA，运行中掉线时恢复等待；不阻塞 rcS。真实 HTTP 错误继续报告。
- 修复：fwctl 与 OTA Server 统一解码版本数值，1 显示为 0.0.1，256 显示为 0.1.0；相同 tag 下以完整内容哈希区分固件。
- 验证：3 项网络状态模拟测试（含断开恢复和退出）、10 项启动脚本测试、22 项 OTA 自动升级测试、7 项服务端管理测试、12 项固件原生测试通过；AM625 构建和实际发布包的 FIT/rootfs 恢复、ARM64 加载器、元数据互操作及上传下载验证通过。
- 板端范围：kernel/rootfs 自动升级和健康确认通过；未更新 SPL/U-Boot，未进行实物拔线测试。
- 发布前发现服务端旧版本格式显示不一致，校验阻止发布；服务端修复、验证、重启后发布同一草稿，保留原服务数据。
- v1.0.17 构建未发布。本次产物与完整审计保存在 `output/ota-validation/0.0.1-network-ready/`。

完整内容 ID：`4a7e87c208009157035991874c257c7ed14c6565bdfb020b5448a47c81c83645`。

```text
1793599377 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 14 1 7fedb04c-c032-4be0-a0f4-5faf93d69686 installing 0 65552 none
1793599381 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 14 1 7fedb04c-c032-4be0-a0f4-5faf93d69686 rebooting 0 65552 none
1793599409 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 14 1 7fedb04c-c032-4be0-a0f4-5faf93d69686 boot-testing 0 1 none
1793599440 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 14 1 7fedb04c-c032-4be0-a0f4-5faf93d69686 success 0 1 none
```


<a id="v0.0.1-5ad4aa1e"></a>

## v0.0.1 / 5ad4aa1e OTA 验证记录

原记录：`bsp-base-external/board/ti/am625/releases/v0.0.1-5ad4aa1e.md`。


- Tag 保持 `v0.0.1`（数值 1），完整内容 ID：`5ad4aa1e46750afa8b08b0e954d074dcdabf802b8377b0cfaa6b0dcf9b6077ed`。
- 服务端发布记录：19；设备 `1c-63-49-22-c4-f7` 安装 kernel/rootfs、重启并通过健康检查后上报 `success`，deployment 1。源码在收到该成功结果后提交。
- 设备日志去掉正常流程中的发布序号，使用版本与前 8 位内容 ID；完整哈希和事务序号仍保留在协议及审计记录中。
- 网页支持四个标签页独立刷新、刷新页面和浏览器前进后退保持当前标签，筛选输入在会话中保留。可按完整/短哈希、版本、产品、状态、设备地址等筛选，多个空格分隔条件同时匹配。
- 固件列表为产品、固件版本、固件 ID、大小、操作、详情；下载入口只在固件详情。灰色禁用按钮“当前版本发布中”、红色禁用按钮“无效固件，禁止发布”和蓝色“发布到设备”区分操作状态，删除单独发布状态列；布局保留在详情。
- 设备请求携带接口 IP/MAC、hostname 和启动 ID，SQLite 按设备/发布/升级事务/阶段保存网络快照；相同上下文累计请求次数，变化时保留新旧值。服务端另外保存实际连接来源 IP。旧客户端未上报的数据不回填。
- 本次新客户端成功上报：IP `192.168.10.211`、MAC `1c:63:49:22:c4:f7`、hostname `am625`、连接来源 IP `192.168.10.211`。安装前运行的是旧客户端，该阶段没有网络快照；新客户端重启后的健康阶段已实机验证。
- 测试：OTA 主机回归 88 项（通用运行跳过 1 项真实包测试，随后对本次真实固件包单独执行并通过），另含 shell 端到端检查。ARM64/QEMU 存储身份 7 项、initramfs 加载器、FIT/恢复/对齐、元数据互操作、真实包上传下载、工厂元数据及最终 SquashFS 中 19 个启动脚本通过。
- Chromium 验证上传不发布、发布按钮、六列表格、灰色/红色禁用按钮、详情下载、标签页刷新及返回、完整哈希和网络字段筛选、桌面/手机无页面横向溢出。部署后 `/api/state` 实测约 21 ms（本机一次采样）。
- 硬件范围：kernel/rootfs OTA 与健康确认。没有更新 SPL/U-Boot；不将它们的版本显示和恢复能力算作本次实机验证。
- 完整产物、源码文件 SHA256 快照、测试日志及设备网络审计：`output/ota-validation/0.0.1-ui-device-audit/`。

```text
1793607884 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 19 1 d1163070-159a-41a8-af83-33e5d9570633 installing 1 1 none
1793607887 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 19 1 d1163070-159a-41a8-af83-33e5d9570633 rebooting 1 1 none
1793607918 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 19 1 d1163070-159a-41a8-af83-33e5d9570633 boot-testing 1 1 none
1793607948 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 19 1 d1163070-159a-41a8-af83-33e5d9570633 success 1 1 none
```


<a id="v0.0.1-5fa96eb8"></a>

## v0.0.1 / 5fa96eb8：布局一致性检查

原记录：`bsp-base-external/board/ti/am625/releases/v0.0.1-5fa96eb8.md`。


固件生成前核对独立维护的配置，不生成或迁移分区：板级与已安装 Linux 布局、
A53/R5 实际 U-Boot DTB、对应构建 .config 的环境偏移、blkdevparts、工厂 genimage、
Linux 环境访问配置、HWID 和 JSON 容量上限。12 个区域偏移/容量必须一致，
环境副本必须落在预留区内。缺少依赖、冲突或容量越界会拒绝打包。

images/layout-validation.json 保留区域表及九份配置/工件的完整 SHA256。
检查不更改板卡现有布局，同 HWID 的已部署布局仍应固定；配置一致不能视为在线迁移支持。

验证：11 项真实 DTB/配置差异注入测试、10 项固件生成测试、4 项 FIT 测试及
实际 ARM64 initramfs 加载。新固件发布 62，AM625 重启并上报 success，串口确认
deployment 1 / kernel-rootfs A，v0.0.1，id=5fa96eb8，confirmed=1。
data 保持 persistent，可用空间约 152 MiB，当前与备用 rootfs 校验正常。
本阶段没有更新 bootloader，不把新 R5 的构建检查视作 R5 实机执行验收。

完整内容 ID：
5fa96eb8b40a406835cbfb5698f239ecbfdb3c72fab1f540832aa3ba08799f16

证据：output/ota-validation/0.0.1-upgrade-07-layout-validation/。


<a id="v0.0.1-64373f72"></a>

## v0.0.1 / 64373f72 公共 HWID 配置验证

原记录：`bsp-base-external/board/ti/am625/releases/v0.0.1-64373f72.md`。


验证日期：2026-11-04。AM625 SD 实机：`192.168.10.211`，HWID `1010001000110000`。

### 配置与生成

固件兼容列表集中于板级 [firmware.json](../firmware.json)，当前包含 `1010001000110000`。
release、bootloader、kernel、rootfs 四份模板统一使用 `@FW_HWIDS@`。
镜像脚本一次读取公共配置，生成全部模板，再进行 FIT 打包和内容 ID 计算。
构建产物中的 `firmware.json` 保存本次实际使用的配置。

配置错误、重复或无效 HWID、缺失模板及遗漏占位符会中止构建；无需逐份维护 HWID。
设备自身的 HWID 继续由 U-Boot 环境保存。

### 验证结果

- 公共配置测试 5 项通过：修改一个配置即可更新四份可编译 FIT 声明；无效输入不覆盖已有生成文件。
- 完整板卡镜像构建通过，四份实际 FIT 的 `fw,hwids` 均与公共配置一致。
- 实际生成镜像的 FIT 完整性/恢复测试 3 项通过。
- OTA CLI 测试 8 项通过，包括本次真实固件的上传、发布、下载和恢复路径验证。
- OTA 服务发布后，设备自动下载、安装到 kernel/rootfs B 槽、重启、通过健康检查并上报 `success`。
- 引导程序保持已验证版本，本次没有重新写入 bootloader。A 槽保留上一健康固件。

软件 tag 保持 `v0.0.1`，完整内容 ID：

```text
64373f72dacaf8ca14adf92f9c858de4174819909da9ae589d1f582785ba88d2
```

服务端发布审计编号为 51。构建、测试、成功快照、源码快照及完整串口日志位于 workspace 的 `output/ota-validation/0.0.1-shared-hwid/`。


<a id="v0.0.1-6aa757f6"></a>

## v0.0.1 / 6aa757f6 统一 fwctl init 验证

原记录：`bsp-base-external/board/ti/am625/releases/v0.0.1-6aa757f6.md`。


- 固件完整 ID：`6aa757f6834861ecc79286b42783f029ec202de39ef84e20d1b85440efea7a35`；tag 保持 `v0.0.1`，OTA 发布记录 24。
- initramfs 的独立 `/init` 脚本执行 `exec /usr/sbin/fwctl init`。恢复逻辑编入 `fwctl`，镜像不再安装 `fw-init` 可执行程序；恢复子命令统一为 `fwctl recovery ...`。
- Buildroot 使用一个 `device-manager` package，分别选择 host 的 `device-server`、`ota-cli` 和 target 的 `fwctl`、`fwctld`、`logctl`、`logctld`。旧独立 package 与 `fw-recovery` package 已移除。
- 完整 AM625 镜像构建、ARM64 initramfs 加载、FIT/固件身份、存储校验、真实 OTA 传输和恢复测试通过。`fwctl init` 相关 12 项与恢复相关 6 项测试通过；源码快照 185 个文件与发布时完全一致。
- 设备 `1c-63-49-22-c4-f7` 于 2026-11-02 13:57:45 UTC 上报 `success`，deployment 0、kernel/rootfs slot b，运行的 tag 和 ID 为 `v0.0.1 / 6aa757f6`。服务器记录了下载、安装、重启、boot-testing、健康确认及成功上报。
- 新启动 ID 为 `482cc831-78dd-47be-817c-3beb1c43091d`。SOL 中可见 initramfs 执行 rootfs 全量校验，随后 `switch_root`；rcS 完成后 `fwctl` 标记 deployment good。
- 本次没有刷写 SPL/U-Boot，因此硬件确认只覆盖新 kernel/rootfs 和 initramfs。设备 data 未配置，日志仍为 volatile；不能据此宣称跨重启本地日志持久化已通过。
- 固件、测试日志、源码快照、设备事务与 SOL 证据保存在 `output/ota-validation/0.0.1-fwctl-unified/`。


<a id="v0.0.1-6cee5c9d"></a>

## v0.0.1 / 6cee5c9d OTA 验证记录

原记录：`bsp-base-external/board/ti/am625/releases/v0.0.1-6cee5c9d.md`。


- 发布编号：#18；tag 保持 `v0.0.1`（数值 1）。设备 `1c-63-49-22-c4-f7` 在 deployment 0 重启、通过健康检查并上报 `success`。
- 哈希读取：`edk_fw_get_identity` 在旧启动器丢失元数据身份扩展时，按当前 deployment 的实际组件槽位读取 kernel FIT，校验包及 DTB 绑定的 rootfs 实际字节，然后按照相同规范重建完整固件 ID。版本日志显示前 8 位；不使用服务器 latest 推测，不修改元数据，不标记健康。
- 日志：正常启动确认阶段由 fwctl 保留一条 `current deployment marked good`；fwctld 不再重复打印网络就绪、boot-testing、success、无需升级，后台上报和审计仍完整保存。等待网络、实际升级操作及错误日志保留。
- 页面：顶部“上传固件”内嵌当前版本小侧栏，下方“发布固件”占整页宽度；移除 01/02 前缀；保留上传与发布、升级历史、发布记录、异常审计四个顶层标签页。
- 打包：发布前发现候选包的内嵌 DTB 未对齐，未发布该候选包。新增生成内容 ID 之前的 8 字节对齐校正及重复执行验证，不改变镜像子数据和子数据哈希。最终完整包及内容 ID 重新验证。
- 测试：实际固件身份读取 7 项原生与 7 项 ARM64/QEMU 测试通过，覆盖旧元数据、现有身份、混合槽位、kernel/rootfs 损坏、非法长度、分区填充排除、元数据只读和临时文件清理；12 项 EDK 原生测试、22 项 OTA 自动升级测试、3 项网络状态测试、3 项 FIT/恢复/对齐测试通过。
- 最终包：ARM64 initramfs 加载器、EDK/U-Boot 元数据互操作、实际上传下载、工厂元数据、SquashFS 内 19 个启动脚本及嵌入 DTB 对齐全部通过。浏览器验证桌面侧栏、整页发布列表、四个标签页、详情/下载入口和手机无横向溢出。
- 硬件范围：kernel/rootfs 自动升级与健康确认；未安装新 SPL/U-Boot，早期 U-Boot/kernel 的身份传递不纳入本次完成范围。fwctl/initramfs 使用已验证的离线身份重建路径。
- 产物、完整源码快照与设备上报位于 `output/ota-validation/0.0.1-storage-identity-aligned/`。

完整内容 ID：`6cee5c9d9fe2e4d3e8f6f920088452b0c4567ab30f3cd2a3864d93119ab075ee`。

```text
1793606136 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 18 1 c8b5d54c-27d9-4d1b-ad83-b36bea259b75 installing 0 1 none
1793606140 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 18 1 c8b5d54c-27d9-4d1b-ad83-b36bea259b75 rebooting 0 1 none
1793606172 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 18 1 c8b5d54c-27d9-4d1b-ad83-b36bea259b75 boot-testing 0 1 none
1793606203 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 18 1 c8b5d54c-27d9-4d1b-ad83-b36bea259b75 success 0 1 none
```


<a id="v0.0.1-b0ff0766"></a>

## v0.0.1 / b0ff0766 免凭据调试验证

原记录：`bsp-base-external/board/ti/am625/releases/v0.0.1-b0ff0766.md`。


- 完整固件 ID：`b0ff0766ad8fed840da7fb11f00e62490904da0bb15663d44d25794f855ac382`。tag 保持 `v0.0.1`；服务端发布记录 22。
- 设备 `1c-63-49-22-c4-f7` 已完成 kernel/rootfs OTA、重启和健康确认，deployment 0；收到 success 后提交代码。
- 根据用户要求，当前服务使用 `--sol-debug-no-auth`，同时放开 Web 查看和设备日志上传；设备 `auth=none` 不读取密钥文件、不发送 Authorization。原有凭据模式仍可显式恢复。
- 首页和 SOL 凭据输入框隐藏，页面自动连接。板级 overlay 提供免凭据调试配置，使用 eth0 MAC 自动生成设备 ID。
- SOL 10 项回归通过，包含没有任何凭据文件的服务端/上传器真实 HTTP 测试、原有鉴权模式、续传、重试、轮转和数据限额。
- Chromium 临时环境验证通过；生产页面只读验证也通过：未输入凭据，自动选中真实 AM625，显示内核、initramfs、服务和事件日志，无 JavaScript 异常。
- ARM64/存储身份、FIT/恢复、initramfs ELF 加载、真实 OTA 包传输、工厂元数据与对齐检查通过。
- 实机日志元数据显示 `/run/logctl/boots`、`storage=volatile`；旧板卡 data 尚未持久化，设备 RAM 日志不保证重启保存。日志已同步至主机 SQLite。SPL/U-Boot 仍报告 unavailable，本次没有刷写新引导程序，不将阶段日志交接计为通过。
- 完整产物、源码快照、设备审计、真实日志计数和网页截图位于 `output/ota-validation/0.0.1-sol-no-auth/`。

```text
1793623977 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 22 1 a2dfcb6f-e4e2-4db5-8a86-4dc0cecb2134 installing 0 1 none
1793623981 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 22 1 a2dfcb6f-e4e2-4db5-8a86-4dc0cecb2134 rebooting 0 1 none
1793624013 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 22 1 a2dfcb6f-e4e2-4db5-8a86-4dc0cecb2134 boot-testing 0 1 none
1793624043 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 22 1 a2dfcb6f-e4e2-4db5-8a86-4dc0cecb2134 success 0 1 none
```


<a id="v0.0.1-b4304330"></a>

## v0.0.1 / b4304330

原记录：`bsp-base-external/board/ti/am625/releases/v0.0.1-b4304330.md`。


EDK 接管 Device Manager 源码，路径为 `edk/device-manager/`。
Buildroot 的设备与主机包改用该路径，并排除已有编译产物；外设构建包保持独立。
管理模块内部结构和运行协议保持不变，libbmc 不参与合并。

完整 ID：`b43043308a2dfce9986fc2d454db77ec9794fa9816a69626516f35c935f1f2e2`。
发布审计编号 88，AM625 `192.168.10.211` 已完成重启健康确认并上报 success。
当前 kernel/rootfs 为 A 槽，启动 ID `6fd2dadf-e5e0-40b3-b952-0ecf069c799a`。

合并路径下的完整管理模块测试、SDK 构建测试、固件与恢复测试通过。
实机 systemd 无失败单元，当前固件实际内容及两个 rootfs 槽校验通过；
日志持久化、SOL 上报、UTC+8 时间同步和 PDM 加载正常。
本次未更新 SPL/U-Boot。

验证记录：workspace 的 `docs/am62x/edk-device-manager-merge.md`。
原始证据：`output/ota-validation/0.0.1-edk-device-manager-merge/`。


<a id="v0.0.1-e993e58c"></a>

## v0.0.1 / e993e58c OTA 验证记录

原记录：`bsp-base-external/board/ti/am625/releases/v0.0.1-e993e58c.md`。


- 发布编号：#17；tag 固定为 `v0.0.1`（数值 1）。设备 `1c-63-49-22-c4-f7` 在 deployment 1 重启、通过健康检查并上报 `success`。
- OTA 管理：SQLite 持久保存内容身份及下载事件；详情页包含上传时间、版本、哈希、下载/升级统计及有效状态；支持手动下载并重新上传；顶层标签页为“上传与发布 / 升级历史 / 发布记录 / 异常审计”。同一时间仅一个活动发布，历史保留。
- 性能：同一现有 feed 的 `/api/state` 从约 8 秒降至约 0.013 秒；首次补录数据库需额外校验，后续读取不重新哈希未变化的固件。
- 日志：统一使用模块与等级前缀，去除分割线和重复前缀；版本行附所属完整固件 ID 的前 8 位。旧 SPL/U-Boot 未更新，当前板端仍显示 `hash=unknown`；本记录不把身份链路标记为完成。
- 失败处置：#15 / 8fe4fb33 的 `S99fw-version` 因误删 if 行产生语法错误，健康检查拒绝确认。根据用户串口日志人工隔离并审计，回退发布 #14 的正常内容为 #16；随后设备上报 #15 `rolled-back`。#15 未作为成功版本提交。
- 修复：恢复版本查询条件；增加生成 rootfs 前的全部启动脚本语法检查。最终 SquashFS 内 19 个启动脚本与解包内容逐一核对，并用目标 ARM64 BusyBox ash 检查。
- 验证：15 项服务端目录/下载测试、6 项隔离测试、12 项启动脚本测试、12 项原生测试通过；真实浏览器验证上传、发布、详情、下载入口、四个标签页与手机布局；发布包通过 FIT/rootfs 恢复、ARM64 加载器、元数据互操作、实际上传下载和工厂元数据校验。
- 产物、完整源码快照与设备上报存放在 `output/ota-validation/0.0.1-init-script-fix/`。本次仅验证 kernel/rootfs 自动升级，不包括未安装的 bootloader。

完整内容 ID：`e993e58c961abd7c0eab701671dfcb83bbd0a290825bc53cfdb610f40c3a574b`。

```text
1793604640 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 17 1 de083286-0a6a-492d-b909-623d22d84275 installing 1 1 none
1793604644 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 17 1 de083286-0a6a-492d-b909-623d22d84275 rebooting 1 1 none
1793604672 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 17 1 de083286-0a6a-492d-b909-623d22d84275 boot-testing 1 1 none
1793604702 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 17 1 de083286-0a6a-492d-b909-623d22d84275 success 1 1 none
```


<a id="v1.0.16"></a>

## v1.0.16 OTA 验证记录

原记录：`bsp-base-external/board/ti/am625/releases/v1.0.16.md`。


- 发布编号：#13；固件内容 ID：`3e41ce92`（日志缩写）。
- 设备：`1c-63-49-22-c4-f7`；产品：`ti-am62x`；布局：`am62x-sd-ab-v1`。
- 版本数值：65552；目标 deployment：1。
- 内容：突出各启动、写入和健康确认节点，写入进度显示语义版本；保留完整 SHA256 校验。
- 配套源码包含此前尚未提交的内容身份、独立 initramfs 恢复、OTA 历史审计、异常隔离和设备服务退出修复。
- 验证：AM625 完整构建、12 项 EDK 原生测试、22 项 OTA 集成测试、6 项恢复测试、U-Boot 沙箱、实际 ARM64 initramfs 加载器和 EDK/U-Boot 身份互操作检查通过。实际发布包另行通过 FIT/rootfs 修复及 OTA 上传下载检查。
- 设备结果：服务器收到重启后的 `boot-testing`，随后收到 `success`，运行版本 65552。
- 范围：本次 OTA 仅安装 kernel/rootfs。新 SPL/U-Boot 未在该设备安装，不能据此认定完整启动链身份显示已经板端验证。
- 本地产物及完整审计：`output/ota-validation/1.0.16/`；固件与构建目录不纳入 Git。

完整内容 ID：`3e41ce9285c4800f6d6aecb43c9f8bb87d7f2ac3acfb7f9d291cc39bbf727af4`。

服务器事务记录（时间戳为 Unix 秒）：

```text
1793598264 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 13 65552 5e70c87f-7ba3-4977-b0c6-f6af7d33c80d installing 1 65551 none
1793598269 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 13 65552 5e70c87f-7ba3-4977-b0c6-f6af7d33c80d rebooting 1 65551 none
1793598307 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 13 65552 5e70c87f-7ba3-4977-b0c6-f6af7d33c80d boot-testing 1 65552 none
1793598322 0 BSPOTASTATE2 1c-63-49-22-c4-f7 ti-am62x am62x-sd-ab-v1 13 65552 5e70c87f-7ba3-4977-b0c6-f6af7d33c80d success 1 65552 none
```

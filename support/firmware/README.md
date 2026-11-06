# 统一固件生成器

板级只维护一份 `firmware.json`。AM625 实例见 [配置文件](../../board/ti/am625/firmware.json)。
原有四份板级 ITS 和组件 `genimage_ti.cfg` 已移除；生成的 ITS 保存在输出目录。

## 配置字段

| 字段 | 用途 |
| --- | --- |
| `schema_version` | 配置格式，目前为 1 |
| `description` | 固件说明 |
| `version` | 版本源，AM625 使用 `{"file":"../../../../edk/VERSION"}`；统一用于所有 FIT |
| `rollback_index` | 统一防回滚索引，默认 0 |
| `hwids` | 支持的完整 HWID 列表，1～256 项，小写、有效且不重复 |
| `architecture` | 镜像默认架构，例如 `arm64` 或 `arm` |
| `components` | bootloader、kernel、rootfs 的输入和启动关系 |
| `release` | 发布说明及本次升级包含的组件 |
| `factory` | 可选的工厂存储布局和默认环境来源 |
| `validation` | 可选的独立布局一致性检查来源，不生成分区配置 |

EDK 的 `VERSION` 是 SDK、Buildroot target/host 包和设备固件的共同版本源，
当前为 `0.0.1`。版本文件路径相对于 `firmware.json` 所在目录，支持引用相邻
仓库；缺失、内容无效或已构建 EDK 的版本不符时拒绝生成发布包。输出的
`images/firmware.json` 保存解析后的版本值，构建清单保存版本文件 SHA256。
生成器也支持直接填入 `major.minor.patch`，供不依赖 EDK 的独立描述和测试使用。
同一版本下继续使用完整固件内容 SHA256 区分构建；人类日志显示前八位。

组件的 `images` 每项具有 `name`、`file`；`file` 相对于 Buildroot images 目录。
`description`、`architecture`、`os` 可以按镜像覆盖；组件 `os` 由镜像继承。
`type` 默认 `firmware`，支持 `kernel`、`flat_dt`、`ramdisk`；`compression` 默认 `none`。
输入文件的压缩格式须与 `compression` 相符，生成器直接封装已有文件。

`kernel`、`fdt`、`ramdisk`、`firmware` 和 `loadables` 引用镜像的 `name`。
每个镜像都必须被引用且只引用一次。bootloader 的镜像数量可调整，无 ATF 时可省略对应镜像。
内核镜像必须提供 `load`、`entry`，支持 JSON 整数或十六进制字符串；超过 32 位时自动生成双 cell 地址。

`max_size` 使用字节数：镜像级限制实际载荷大小，组件级限制整个 ITB 大小。
rootfs 载荷限制在 verity 数据与哈希树生成后再次检查，内核限制在 DTB 对齐调整后再次检查。
这些限制须与对应板级物理分区容量一致。

## RAW 布局一致性检查

AM625 的 `validation.linux_layout` 相对于板级目录；`validation.uboot_dtbs`
相对于 `BUILD_DIR`，同时检查 A53 和 R5 的实际 DTB 及其构建 `.config`。
生成前核对 Linux 源配置与已安装配置、12 个区域的偏移/容量、工厂 genimage、
默认环境中的 blkdevparts、两份环境的编译偏移与 `/etc/fw_env.config`、HWID allowlist
和 JSON 容量上限。任何差异都会停止生成，输出明确指出区域和配置来源。
通过后在 images 中保存 `layout-validation.json`，包括区域表与九份输入的 SHA256。

当前检查用于板卡现有 RAW MMC 布局，不迁移 GPT、运行设备的分区或环境。
同一 HWID 的已部署布局仍应保持不变；全部配置自洽不代表可以在线改变分区。
单独编译 U-Boot 不会调用此检查，最终打包必须使用相符的构建产物；缺少依赖会拒绝打包。

```sh
HOST_DIR="$PWD/output/am625-time-ui/host" \
python3 bsp-base-external/support/firmware/tests/test_layout.py
```

内核 ramdisk 镜像设置 `name: "initramfs"`、`file: "initramfs.cpio.gz"` 和
`generate: "initramfs"`，由 `../scripts/build-initramfs.py` 收集现有工具和 ELF 依赖生成。
FIT 配置通过 `ramdisk: "initramfs"` 引用该镜像；它随 kernel FIT 存放，无独立物理分区。
其中 `/init` 脚本调用 `fwctl init`，负责正常启动的 Rootfs 校验、切换根文件系统和异常恢复。
rootfs 可设置 `verity: true`，此时要求内核有 fdt、ramdisk 引用；生成器保留原 DTB，
生成带验证参数的 DTB 和包含哈希树的 rootfs，然后封装到相应 FIT。

`release.components` 必须包含 kernel/rootfs，以构成完整内容 ID。
加入 bootloader 时会生成 `fw,allow-bootloader`，用于受控本地或 U-Boot 升级；
设备升级策略仍须显式允许，当前 OTA server 发布接口继续限定 kernel/rootfs。

`factory.layout` 相对于板级 JSON 所在目录，描述实际介质的分区、偏移与容量。
布局可用 `${FW_ROOTFS_IMAGE}` 和 `${FW_BOOTLOADER_<镜像名大写>_IMAGE}` 引用实际载荷，
例如 `${FW_BOOTLOADER_TIBOOT3_IMAGE}`，避免重复指定输入文件。
`factory.environment` 相对于 target 目录，仅用于生成工厂默认环境，不参与普通 OTA 写入。

## 构建与产物

Buildroot 的 post-image 参数指向统一配置：

```text
BR2_ROOTFS_POST_IMAGE_SCRIPT_ARGS="-c $(BR2_EXTERNAL_LINUX_BSP_PATH)/board/ti/am625/firmware.json"
```

1. 校验 JSON、镜像引用、输入文件和大小限制。
2. 按配置生成 verity、恢复 initramfs 和三个组件 ITS；mkimage 生成组件 ITB。
3. 对齐内嵌 DTB，计算实际 kernel/rootfs 内容 ID 及组件哈希。
4. 生成 release ITS/ITB 和冗余启动元数据。
5. 配置 `factory` 时生成默认环境，并调用 genimage 生成工厂镜像。

`images/firmware.json` 保留带默认值的实际配置；`firmware-identity.json` 保留版本与内容 ID。
`images/release/` 保留四份 ITS 和 ITB，便于检查和追溯。工具不写设备，不格式化设备存储。

## 模块与验证

- `config.py`：JSON 校验、字段默认值和引用关系。
- `fit.py`：生成标准 FIT/DTS 文本。
- `identity.py`：DTB 对齐、内容 ID 及启动元数据。
- `image.py`：组织依赖顺序，调用 mkimage、verity、initramfs 和工厂镜像工具。
- `../scripts/firmware-image.sh`：Buildroot 的薄入口。

从 workspace 执行测试：

```sh
HOST_DIR="$PWD/output/am625-time-ui/host" \
LD_LIBRARY_PATH="$PWD/output/am625-time-ui/host/lib" \
python3 bsp-base-external/support/firmware/tests/test_image.py
```

测试使用真实 mkimage/dtc 验证生成格式；ARMv7 描述和 64 位地址测试不代表对应硬件已完成板级验证。
AM625 的启动、升级和恢复兼容性还需实际生成镜像测试及设备健康确认。

## 可复现发布与来源清单

AM625 启用 BR2_REPRODUCIBLE，时间输入统一使用 SOURCE_DATE_EPOCH；独立打包未提供时使用 0。
FIT 自定义构建时间和 mkimage 时间戳使用同一值；verity salt 和 initramfs 压缩已固定。
完整 kernel/rootfs 的 SHA256 算法保持不变，不通过排除数据来伪造一致的固件 ID。

生成器先在同一文件系统的私有目录完成全部组件、验证与工厂镜像，再通过 Linux
renameat2 交换完整 release 目录。失败保留上一次有效 OTA 包。images 顶层身份、
配置、metadata 和 build-manifest.json 是 release 内文件的链接；工厂镜像不作为 OTA 发布入口。
同一 images 目录由单个 Buildroot 构建任务使用。

build-manifest.json 保存完整固件身份、各仓库提交与未提交改动摘要、配置 SHA256、
EDK Host/Target 编译来源和工具版本。副本与源码补丁一并保存在每次验收目录中。
当前可复现测试验证固定输入重复打包及同一构建目录重复生成的 OTA ITB；
工厂 ext4/SD 镜像的 UUID 与跨机器全量工具链重建不属于该项已验证保证。

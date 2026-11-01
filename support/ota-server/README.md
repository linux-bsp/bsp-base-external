# BSP OTA：发布版本与设备主动下载

这一版提供两个 C 可执行程序，代码放在 `bsp-base-external`，不依赖 SadBoard：

- `ota-server`：提供 HTTP 下载和简单网页；`publish` 子命令发布固件快照。
- `ota-agent`：设备定期查询最新发布，下载到本地，校验大小和 SHA256。默认每 60 秒检查一次，失败后下次重试。

流程：构建固件 → 发布 → 设备轮询 → 下载并校验 → 手动 `fwctl update` → 按需重启 → 现有健康检查确认启动。

## 1. 编译并发布

以下命令从 `~/workspaces/am62x` 执行。编译只需要 C 编译器和 make；发布时需要 `sha256sum`、`fdtget`，设备下载需要 `curl` 和 `sha256sum`。程序通过参数数组执行工具，不通过 shell 拼接命令。

```sh
make -C bsp-base-external/support/ota-server
export PATH="$PWD/output/am625/host/bin:$PATH"
mkdir -p output/ota-feed
bsp-base-external/support/ota-server/ota-server publish \
    --root "$PWD/output/ota-feed" \
    --source "$PWD/output/am625/images/release" \
    --version 1 --product ti-am62x --layout am62x-sd-ab-v1
bsp-base-external/support/ota-server/ota-server \
    --root "$PWD/output/ota-feed" --bind 0.0.0.0 --port 8080
```

如果主机 IP 为 `192.168.10.246`，浏览器访问 `http://192.168.10.246:8080/`。
默认只监听 `127.0.0.1`；开发板连接时需显式指定外部监听地址。

发布会复制 `release.itb`、`kernel.itb`、`rootfs.itb`，检查 release FIT 的产品、布局、组件文件名和组件 SHA256，保存为 `releases/1/`，最后原子替换 `latest` 清单。发布期间服务可以继续运行；旧版本 URL 保留不变。不要修改或覆盖已经发布的目录。

新固件构建完成后，再运行同样的发布命令，把 `--version` 改为 `2`。重复或倒退的编号、不同产品/布局、混合的组件文件会被拒绝。第一版每个服务目录只管理一种产品和布局。

**这里的 `--version` 是递增发布编号（1～2147483647），不是 FIT 的 `fw,version`。** 发布不会修改已构建 FIT、提升固件版本或绕过回滚检查。当前板级 ITS 模板仍使用固定版本；真正升级固件版本时，需要调整对应 FIT 元数据后重新构建。最终是否允许安装仍由 `fwctl` 决定。

## 2. 设备主动检查与下载

AM62x defconfig 已启用 `BR2_PACKAGE_OTA_AGENT`，并增加 curl 命令和 BusyBox SHA256。首次从配置构建时：

```sh
make -C buildroot BR2_EXTERNAL=../bsp-base-external alientek_am62x_defconfig
make -C buildroot
```

使用已有 `output/am625` 构建目录时，保留原来的下载目录等本地配置，通过 `menuconfig` 启用 `ota-agent`，然后执行：

```sh
make -C output/am625 menuconfig
make -C output/am625 libcurl-reconfigure busybox-reconfigure ota-agent
make -C output/am625
```

开发板需先准备好可写且容量足够的缓存目录；推荐将 `/data` 挂载到持久存储。不要直接假设当前板卡已经挂载了 data 分区，也不要为测试格式化现有数据。

```sh
mkdir -p /data/ota
ota-agent --server http://192.168.10.246:8080 \
    --product ti-am62x --layout am62x-sd-ab-v1 \
    --cache /data/ota --interval 60
```

该命令前台运行；加 `--once` 则只检查一次，失败返回非零。没有发布版本时会报告检查失败并等待下一轮。下载固定版本 URL，所有文件校验通过后才出现 `/data/ota/1/` 和 `current` 记录。`current` 只表示下载完成，不能用于判断设备当前运行版本或升级成功。

重复检查不会重新下载同一版本的固件，但会重新校验缓存。网络错误、型号不匹配、损坏文件或发布编号倒退不会替换之前的 `current`。损坏的已完成缓存需要删除对应编号目录后重试；中断下载下一轮重新开始，暂不支持断点续传。设备会保留历史下载，需定期人工清理；异常断电可能留下 `.download-*` 临时目录，可在停止 agent 后清理。

## 3. 安装与开机轮询

查看 agent 输出的具体路径，检查 `fwctl status` 后安装。例如发布编号为 1：

```sh
fwctl status
fwctl update /data/ota/1/release.itb
```

`fwctl` 校验 FIT、版本和回滚策略，写入非活动槽并设置待启动状态；返回成功不代表新版本已启动。确认写入成功后再按设备策略重启，后续沿用 `S99fw-mark-good` 健康确认流程。OTA 程序不会自动安装或重启。

`S98ota-agent` 默认关闭。若 `/data` 已在启动脚本运行前挂载，可以创建仅由管理员维护的 `/data/ota-agent.conf`：

```sh
OTA_ENABLED=1
OTA_SERVER="http://192.168.10.246:8080"
OTA_CACHE="/data/ota"
OTA_INTERVAL=60
```

其余默认值来自 `/etc/default/ota-agent`。执行 `/etc/init.d/S98ota-agent start` 启动，`stop` 停止。只读 rootfs 无需直接修改 `/etc`；持久配置生效依赖 `/data` 的挂载时机。

## 协议与范围

- `GET /latest`：`BSPOTA1` 文本清单，包含发布编号、产品、布局和三个文件的大小与 SHA256。
- `GET /releases/<编号>/{release.itb,kernel.itb,rootfs.itb,manifest}`：固定版本下载。
- `GET /`：最新发布的文件链接；`GET /healthz`：服务存活检查。
- 支持 GET/HEAD；路径严格限制，不提供上传接口，不发布 bootloader。

这是局域网开发验证版本：HTTP 服务串行处理请求，没有账号、TLS、推送连接、设备管理或自动清理。设备采用主动轮询而非服务端直接连接设备。SHA256 用于完整性检查，不等于发布者身份认证；生产部署需要补上认证传输和固件签名策略。发布程序校验的是 release 元数据及组件文件哈希，完整 FIT/签名/安装策略由 `fwctl` 检查。

## 验证

```sh
make -C bsp-base-external/support/ota-server test
```

测试使用本机临时目录、回环 HTTP 和合成清单，覆盖在线发布后自动发现、重复版本、文件校验失败、型号不匹配、旧版本拒绝、缓存保留、互斥和路径限制。它不会调用真实 `fwctl`、写入板卡闪存或重启设备。实际板卡的安装、重启及回滚还需要硬件验证。

已完成主机端到端测试、AM62x 交叉编译和完整镜像构建，并使用实际 FIT 固件完成发布、下载和逐字节比对。可重复运行实际固件传输测试：

```sh
sh bsp-base-external/support/ota-server/tests/test-real-release.sh \
    output/am625/images/release
```

这不等同于开发板 OTA 安装测试；当前未进行硬件刷写。

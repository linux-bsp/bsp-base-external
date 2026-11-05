DEVICE_MANAGER_VERSION = 1
DEVICE_MANAGER_SITE = $(BR2_EXTERNAL_LINUX_BSP_PATH)/../edk
DEVICE_MANAGER_SITE_METHOD = local
# Never import native binaries or objects into a target/host package build.
DEVICE_MANAGER_OVERRIDE_SRCDIR_RSYNC_EXCLUSIONS = \
	--exclude='/.build' --exclude='/device-manager/bin' --exclude='/device-manager/build' --exclude='/user/transfer/build' --exclude='/user/fwctl/build' \
	--exclude='/device-manager/ota/device-server' --exclude='/device-manager/ota/fwctld' --exclude='/device-manager/ota/ota-cli' \
	--exclude='/device-manager/ota/ota-page.h' --exclude='/user/logctl/logctl' --exclude='/user/logctl/logctld' \
	--exclude='/user/timectl/timectl' --exclude='/user/timectl/timectld' --exclude='__pycache__'

ifeq ($(BR2_PACKAGE_DEVICE_MANAGER_FWCTL),y)
DEVICE_MANAGER_DEPENDENCIES += dtc libcurl openssl libubootenv host-cmake host-python3 host-flex host-bison
endif
ifeq ($(BR2_PACKAGE_DEVICE_MANAGER_FWCTLD),y)
DEVICE_MANAGER_DEPENDENCIES += libcurl openssl busybox
endif
ifeq ($(BR2_PACKAGE_DEVICE_MANAGER_LOGCTL),y)
DEVICE_MANAGER_DEPENDENCIES += busybox libcurl openssl zlib
endif
ifeq ($(BR2_PACKAGE_DEVICE_MANAGER_TIMECTL),y)
DEVICE_MANAGER_DEPENDENCIES += libcurl openssl
endif

ifneq ($(strip $(DEVICE_MANAGER_TARGETS)),)
define DEVICE_MANAGER_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(MAKE) -B -C $(@D)/device-manager CC="$(TARGET_CC)" AR="$(TARGET_AR)" \
		CFLAGS="$(TARGET_CFLAGS)" LDFLAGS="$(TARGET_LDFLAGS)" \
		$(DEVICE_MANAGER_TARGETS)
endef
else
define DEVICE_MANAGER_BUILD_CMDS
	true
endef
endif

# Buildroot owns component selection; one generated seed feeds EDK Kconfig.
ifneq ($(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTL) $(BR2_PACKAGE_DEVICE_MANAGER_LOGCTL) $(BR2_PACKAGE_DEVICE_MANAGER_TIMECTL)),)
DEVICE_MANAGER_DEPENDENCIES += host-cmake host-python3 host-flex host-bison
define DEVICE_MANAGER_BUILD_MANAGEMENT
	mkdir -p $(@D)/.build
	printf 'CONFIG_ARCH="%s"\nCONFIG_FWCTL=%s\nCONFIG_FWCTLD=%s\nCONFIG_LOGCTL=%s\nCONFIG_TIMECTL=%s\n' \
		"$(KERNEL_ARCH)" "$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTL)),y,n)" \
		"$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTLD)),y,n)" \
		"$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_LOGCTL)),y,n)" \
		"$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_TIMECTL)),y,n)" > $(@D)/.build/management.config
	$(TARGET_MAKE_ENV) $(HOST_DIR)/bin/cmake -S $(@D) -B $(@D)/.build/management \
		-DCONFIG_FILE=$(@D)/.build/management.config \
		-DCMAKE_TOOLCHAIN_FILE=$(HOST_DIR)/share/buildroot/toolchainfile.cmake \
		-DCMAKE_BUILD_TYPE=MinSizeRel -DCMAKE_INSTALL_PREFIX=/usr \
		-DCMAKE_C_FLAGS="$(filter-out -O% -g%,$(TARGET_CFLAGS))" \
		-DCMAKE_EXE_LINKER_FLAGS="$(TARGET_LDFLAGS)"
	$(TARGET_MAKE_ENV) $(HOST_DIR)/bin/cmake --build $(@D)/.build/management --parallel $(PARALLEL_JOBS)
endef
DEVICE_MANAGER_POST_BUILD_HOOKS += DEVICE_MANAGER_BUILD_MANAGEMENT
endif

define DEVICE_MANAGER_INSTALL_TARGET_CMDS
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTL)),$(INSTALL) -D -m 0755 $(@D)/.build/management/bin/fwctl $(TARGET_DIR)/usr/sbin/fwctl)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTLD)),$(INSTALL) -D -m 0755 $(@D)/.build/management/bin/fwctld $(TARGET_DIR)/usr/sbin/fwctld)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTLD)),$(INSTALL) -D -m 0644 $(DEVICE_MANAGER_PKGDIR)/fwctld.default $(TARGET_DIR)/etc/default/fwctld)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_LOGCTL)),$(INSTALL) -d $(TARGET_DIR)/data)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_LOGCTL)),$(INSTALL) -D -m 0755 $(@D)/.build/management/bin/logctl $(TARGET_DIR)/usr/sbin/logctl)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_LOGCTL)),ln -sf logctl $(TARGET_DIR)/usr/sbin/logctld)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_TIMECTL)),$(INSTALL) -D -m 0755 $(@D)/.build/management/bin/timectl $(TARGET_DIR)/usr/sbin/timectl)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_TIMECTL)),ln -sf timectl $(TARGET_DIR)/usr/sbin/timectld)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_TIMECTL)),$(INSTALL) -D -m 0755 $(@D)/device-manager/integration/systemd/timectld-start $(TARGET_DIR)/usr/libexec/device-manager/timectld-start)
endef

define DEVICE_MANAGER_INSTALL_INIT_SYSV
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTLD)),$(INSTALL) -D -m 0755 $(DEVICE_MANAGER_PKGDIR)/S98fwctld $(TARGET_DIR)/etc/init.d/S98fwctld)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_LOGCTL)),$(INSTALL) -D -m 0755 $(DEVICE_MANAGER_PKGDIR)/S01logctld $(TARGET_DIR)/etc/init.d/S01logctld)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_TIMECTL)),$(INSTALL) -D -m 0755 $(DEVICE_MANAGER_PKGDIR)/S02timectld $(TARGET_DIR)/etc/init.d/S02timectld)
endef

# Native systemd units run daemons in the foreground; no second supervisor.
define DEVICE_MANAGER_INSTALL_INIT_SYSTEMD
	$(INSTALL) -d $(TARGET_DIR)/usr/lib/systemd/system $(TARGET_DIR)/usr/libexec/device-manager $(TARGET_DIR)/usr/lib/systemd/system-preset
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTL)),$(INSTALL) -m 0644 $(@D)/device-manager/integration/systemd/fw-health.service $(@D)/device-manager/integration/systemd/fw-confirm.service $(@D)/device-manager/integration/systemd/fw-health-failure.service $(TARGET_DIR)/usr/lib/systemd/system/)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTL)),$(INSTALL) -m 0755 $(@D)/device-manager/integration/systemd/fw-confirm $(@D)/device-manager/integration/systemd/fw-health-monitor $(@D)/device-manager/integration/systemd/fw-health-failure $(TARGET_DIR)/usr/libexec/device-manager/)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTLD)),$(INSTALL) -m 0644 $(@D)/device-manager/integration/systemd/fwctld.service $(TARGET_DIR)/usr/lib/systemd/system/)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTLD)),$(INSTALL) -m 0755 $(@D)/device-manager/integration/systemd/fwctld-start $(TARGET_DIR)/usr/libexec/device-manager/)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_LOGCTL)),$(INSTALL) -m 0644 $(@D)/device-manager/integration/systemd/logctld.service $(@D)/device-manager/integration/systemd/logctl-journal.service $(@D)/device-manager/integration/systemd/device-shutdown-intent.service $(TARGET_DIR)/usr/lib/systemd/system/)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_LOGCTL)),$(INSTALL) -m 0755 $(@D)/device-manager/integration/systemd/logctld-start $(TARGET_DIR)/usr/libexec/device-manager/)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_TIMECTL)),$(INSTALL) -m 0644 $(@D)/device-manager/integration/systemd/timectld.service $(TARGET_DIR)/usr/lib/systemd/system/)
	$(INSTALL) -m 0644 $(@D)/device-manager/integration/systemd/*.preset $(TARGET_DIR)/usr/lib/systemd/system-preset/
endef

HOST_DEVICE_MANAGER_VERSION = 1
HOST_DEVICE_MANAGER_SITE = $(DEVICE_MANAGER_SITE)
HOST_DEVICE_MANAGER_SITE_METHOD = local
HOST_DEVICE_MANAGER_OVERRIDE_SRCDIR_RSYNC_EXCLUSIONS = $(DEVICE_MANAGER_OVERRIDE_SRCDIR_RSYNC_EXCLUSIONS)
ifeq ($(BR2_PACKAGE_HOST_DEVICE_MANAGER_SERVER),y)
HOST_DEVICE_MANAGER_DEPENDENCIES += host-sqlite host-zlib host-uboot-tools host-openssl
HOST_DEVICE_MANAGER_TARGETS += device-server
endif
ifeq ($(BR2_PACKAGE_HOST_DEVICE_MANAGER_OTA_CLI),y)
HOST_DEVICE_MANAGER_DEPENDENCIES += host-libcurl host-openssl
HOST_DEVICE_MANAGER_TARGETS += ota-cli
endif

ifneq ($(strip $(HOST_DEVICE_MANAGER_TARGETS)),)
define HOST_DEVICE_MANAGER_BUILD_CMDS
	$(HOST_MAKE_ENV) $(MAKE) -B -C $(@D)/device-manager CC="$(HOSTCC)" \
		CPPFLAGS="$(HOST_CPPFLAGS)" CFLAGS="$(HOST_CFLAGS)" \
		LDFLAGS="$(HOST_LDFLAGS)" $(HOST_DEVICE_MANAGER_TARGETS)
endef
else
define HOST_DEVICE_MANAGER_BUILD_CMDS
	true
endef
endif

define HOST_DEVICE_MANAGER_INSTALL_CMDS
	$(if $(filter y,$(BR2_PACKAGE_HOST_DEVICE_MANAGER_SERVER)),$(INSTALL) -D -m 0755 $(@D)/device-manager/ota/device-server $(HOST_DIR)/bin/device-server)
	$(if $(filter y,$(BR2_PACKAGE_HOST_DEVICE_MANAGER_OTA_CLI)),$(INSTALL) -D -m 0755 $(@D)/device-manager/ota/ota-cli $(HOST_DIR)/bin/ota-cli)
endef

$(eval $(generic-package))
$(eval $(host-generic-package))

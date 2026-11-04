DEVICE_MANAGER_VERSION = 1
DEVICE_MANAGER_SITE = $(BR2_EXTERNAL_LINUX_BSP_PATH)/../device-manager
DEVICE_MANAGER_SITE_METHOD = local

ifeq ($(BR2_PACKAGE_DEVICE_MANAGER_FWCTL),y)
DEVICE_MANAGER_DEPENDENCIES += dtc libcurl openssl libubootenv
DEVICE_MANAGER_TARGETS += fwctl
endif
ifeq ($(BR2_PACKAGE_DEVICE_MANAGER_FWCTLD),y)
DEVICE_MANAGER_DEPENDENCIES += libcurl busybox
DEVICE_MANAGER_TARGETS += fwctld
endif
ifeq ($(BR2_PACKAGE_DEVICE_MANAGER_LOGCTL),y)
DEVICE_MANAGER_DEPENDENCIES += busybox libcurl
DEVICE_MANAGER_TARGETS += logctl logctld
endif

ifneq ($(strip $(DEVICE_MANAGER_TARGETS)),)
define DEVICE_MANAGER_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(MAKE) -B -C $(@D) CC="$(TARGET_CC)" \
		CFLAGS="$(TARGET_CFLAGS)" LDFLAGS="$(TARGET_LDFLAGS)" \
		$(DEVICE_MANAGER_TARGETS)
endef
else
define DEVICE_MANAGER_BUILD_CMDS
	true
endef
endif

define DEVICE_MANAGER_INSTALL_TARGET_CMDS
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTL)),$(INSTALL) -D -m 0755 $(@D)/bin/fwctl $(TARGET_DIR)/usr/sbin/fwctl)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTLD)),$(INSTALL) -D -m 0755 $(@D)/ota/fwctld $(TARGET_DIR)/usr/sbin/fwctld)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTLD)),$(INSTALL) -D -m 0644 $(DEVICE_MANAGER_PKGDIR)/fwctld.default $(TARGET_DIR)/etc/default/fwctld)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_LOGCTL)),$(INSTALL) -d $(TARGET_DIR)/data)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_LOGCTL)),$(INSTALL) -D -m 0755 $(@D)/logging/logctl $(TARGET_DIR)/usr/sbin/logctl)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_LOGCTL)),$(INSTALL) -D -m 0755 $(@D)/logging/logctld $(TARGET_DIR)/usr/sbin/logctld)
endef

define DEVICE_MANAGER_INSTALL_INIT_SYSV
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_FWCTLD)),$(INSTALL) -D -m 0755 $(DEVICE_MANAGER_PKGDIR)/S98fwctld $(TARGET_DIR)/etc/init.d/S98fwctld)
	$(if $(filter y,$(BR2_PACKAGE_DEVICE_MANAGER_LOGCTL)),$(INSTALL) -D -m 0755 $(DEVICE_MANAGER_PKGDIR)/S01logctld $(TARGET_DIR)/etc/init.d/S01logctld)
endef

HOST_DEVICE_MANAGER_VERSION = 1
HOST_DEVICE_MANAGER_SITE = $(DEVICE_MANAGER_SITE)
HOST_DEVICE_MANAGER_SITE_METHOD = local
ifeq ($(BR2_PACKAGE_HOST_DEVICE_MANAGER_SERVER),y)
HOST_DEVICE_MANAGER_DEPENDENCIES += host-sqlite host-zlib host-uboot-tools
HOST_DEVICE_MANAGER_TARGETS += device-server
endif
ifeq ($(BR2_PACKAGE_HOST_DEVICE_MANAGER_OTA_CLI),y)
HOST_DEVICE_MANAGER_TARGETS += ota-cli
endif

ifneq ($(strip $(HOST_DEVICE_MANAGER_TARGETS)),)
define HOST_DEVICE_MANAGER_BUILD_CMDS
	$(HOST_MAKE_ENV) $(MAKE) -B -C $(@D) CC="$(HOSTCC)" \
		CPPFLAGS="$(HOST_CPPFLAGS)" CFLAGS="$(HOST_CFLAGS)" \
		LDFLAGS="$(HOST_LDFLAGS)" $(HOST_DEVICE_MANAGER_TARGETS)
endef
else
define HOST_DEVICE_MANAGER_BUILD_CMDS
	true
endef
endif

define HOST_DEVICE_MANAGER_INSTALL_CMDS
	$(if $(filter y,$(BR2_PACKAGE_HOST_DEVICE_MANAGER_SERVER)),$(INSTALL) -D -m 0755 $(@D)/ota/device-server $(HOST_DIR)/bin/device-server)
	$(if $(filter y,$(BR2_PACKAGE_HOST_DEVICE_MANAGER_OTA_CLI)),$(INSTALL) -D -m 0755 $(@D)/ota/ota-cli $(HOST_DIR)/bin/ota-cli)
endef

$(eval $(generic-package))
$(eval $(host-generic-package))

HOST_DEVICE_SERVER_VERSION = 1
HOST_DEVICE_SERVER_SITE = $(BR2_EXTERNAL_LINUX_BSP_PATH)/../device-manager
HOST_DEVICE_SERVER_SITE_METHOD = local
HOST_DEVICE_SERVER_DEPENDENCIES = host-sqlite host-zlib host-uboot-tools

define HOST_DEVICE_SERVER_BUILD_CMDS
	$(HOST_MAKE_ENV) $(MAKE) -B -C $(@D) CC="$(HOSTCC)" \
		CPPFLAGS="$(HOST_CPPFLAGS)" CFLAGS="$(HOST_CFLAGS)" \
		LDFLAGS="$(HOST_LDFLAGS)" host
endef

define HOST_DEVICE_SERVER_INSTALL_CMDS
	$(INSTALL) -D -m 0755 $(@D)/ota/device-server $(HOST_DIR)/bin/device-server
	$(INSTALL) -D -m 0755 $(@D)/ota/ota-cli $(HOST_DIR)/bin/ota-cli
endef

$(eval $(host-generic-package))

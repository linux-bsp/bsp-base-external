FWCTL_VERSION = 1
FWCTL_SITE = $(BR2_EXTERNAL_LINUX_BSP_PATH)/../device-manager
FWCTL_SITE_METHOD = local
FWCTL_DEPENDENCIES = dtc libcurl openssl

define FWCTL_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(MAKE) -B -C $(@D) CC="$(TARGET_CC)" \
		CFLAGS="$(TARGET_CFLAGS)" LDFLAGS="$(TARGET_LDFLAGS)" fwctl
endef

define FWCTL_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/bin/fwctl $(TARGET_DIR)/usr/sbin/fwctl
endef

$(eval $(generic-package))

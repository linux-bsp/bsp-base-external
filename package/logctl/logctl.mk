LOGCTL_VERSION = 1
LOGCTL_SITE = $(BR2_EXTERNAL_LINUX_BSP_PATH)/../device-manager
LOGCTL_SITE_METHOD = local
LOGCTL_DEPENDENCIES = busybox libcurl

define LOGCTL_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(MAKE) -B -C $(@D) CC="$(TARGET_CC)" \
		CFLAGS="$(TARGET_CFLAGS)" LDFLAGS="$(TARGET_LDFLAGS)" logctl logctld
endef

define LOGCTL_INSTALL_TARGET_CMDS
	$(INSTALL) -d $(TARGET_DIR)/data
	$(INSTALL) -D -m 0755 $(@D)/logging/logctl $(TARGET_DIR)/usr/sbin/logctl
	$(INSTALL) -D -m 0755 $(@D)/logging/logctld $(TARGET_DIR)/usr/sbin/logctld
endef

define LOGCTL_INSTALL_INIT_SYSV
	$(INSTALL) -D -m 0755 $(LOGCTL_PKGDIR)/S01logctld $(TARGET_DIR)/etc/init.d/S01logctld
endef

$(eval $(generic-package))

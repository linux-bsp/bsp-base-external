################################################################################
#
# fwctld
#
################################################################################

FWCTLD_VERSION = 1
FWCTLD_SITE = $(BR2_EXTERNAL_LINUX_BSP_PATH)/support/ota-server
FWCTLD_SITE_METHOD = local
FWCTLD_DEPENDENCIES = libcurl busybox edk

# License selection for this repository is pending; do not claim an SPDX license.
define FWCTLD_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(MAKE) -B -C $(@D) CC="$(TARGET_CC)" \
		CFLAGS="$(TARGET_CFLAGS) -std=c11 -Wall -Wextra -Werror" \
		LDFLAGS="$(TARGET_LDFLAGS)" fwctld
endef

define FWCTLD_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/fwctld $(TARGET_DIR)/usr/sbin/fwctld
	$(INSTALL) -D -m 0644 $(FWCTLD_PKGDIR)/fwctld.default \
		$(TARGET_DIR)/etc/default/fwctld
endef

define FWCTLD_INSTALL_INIT_SYSV
	$(INSTALL) -D -m 0755 $(FWCTLD_PKGDIR)/S98fwctld \
		$(TARGET_DIR)/etc/init.d/S98fwctld
endef

$(eval $(generic-package))

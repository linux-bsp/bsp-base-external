################################################################################
#
# ota-agent
#
################################################################################

OTA_AGENT_VERSION = 1
OTA_AGENT_SITE = $(BR2_EXTERNAL_LINUX_BSP_PATH)/support/ota-server
OTA_AGENT_SITE_METHOD = local
OTA_AGENT_DEPENDENCIES = libcurl busybox

# License selection for this repository is pending; do not claim an SPDX license.
define OTA_AGENT_BUILD_CMDS
	$(TARGET_MAKE_ENV) $(MAKE) -B -C $(@D) CC="$(TARGET_CC)" \
		CFLAGS="$(TARGET_CFLAGS) -std=c11 -Wall -Wextra -Werror" \
		LDFLAGS="$(TARGET_LDFLAGS)" ota-agent
endef

define OTA_AGENT_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/ota-agent $(TARGET_DIR)/usr/sbin/ota-agent
	$(INSTALL) -D -m 0644 $(OTA_AGENT_PKGDIR)/ota-agent.default \
		$(TARGET_DIR)/etc/default/ota-agent
endef

define OTA_AGENT_INSTALL_INIT_SYSV
	$(INSTALL) -D -m 0755 $(OTA_AGENT_PKGDIR)/S98ota-agent \
		$(TARGET_DIR)/etc/init.d/S98ota-agent
endef

$(eval $(generic-package))

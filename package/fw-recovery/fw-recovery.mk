FW_RECOVERY_VERSION = 1
FW_RECOVERY_SITE = $(BR2_EXTERNAL_LINUX_BSP_PATH)/support/fw-recovery
FW_RECOVERY_SITE_METHOD = local
FW_RECOVERY_DEPENDENCIES = openssl libcurl busybox edk

# Local sources may contain the executable built by host-side tests.
# Always compile it with TARGET_CC before installing into the target image.
define FW_RECOVERY_BUILD_CMDS
    $(TARGET_MAKE_ENV) $(MAKE) -B -C $(@D) CC="$(TARGET_CC)" \
        CFLAGS="$(TARGET_CFLAGS) -std=c11 -Wall -Wextra -Werror" \
        LDFLAGS="$(TARGET_LDFLAGS)" fw-init
endef

define FW_RECOVERY_INSTALL_TARGET_CMDS
    $(INSTALL) -D -m 0755 $(@D)/fw-init $(TARGET_DIR)/usr/sbin/fw-init
endef

$(eval $(generic-package))

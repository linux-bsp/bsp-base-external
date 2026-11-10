HOST_FW_TOOLS_VERSION = 1
HOST_FW_TOOLS_SITE = $(BR2_EXTERNAL_LINUX_BSP_PATH)/support/fw-tools
HOST_FW_TOOLS_SITE_METHOD = local
HOST_FW_TOOLS_DEPENDENCIES = host-cjson host-dtc host-jq host-cpio host-cmake

define HOST_FW_TOOLS_BUILD_CMDS
    $(HOSTCC) $(HOST_CFLAGS) -I$(HOST_DIR)/include/libfdt -std=c11 -Wall -Wextra -Werror \
        $(@D)/fw-build-tool.c $(HOST_LDFLAGS) -lcjson -lfdt -o $(@D)/fw-build-tool
endef

define HOST_FW_TOOLS_INSTALL_CMDS
    $(INSTALL) -D -m 0755 $(@D)/fw-build-tool $(HOST_DIR)/bin/fw-build-tool
endef

$(eval $(host-generic-package))

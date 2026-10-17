################################################################################
# bmctool
################################################################################

BMCTOOL_SITE = $(TOPDIR)/../bmctool
BMCTOOL_SITE_METHOD = local
BMCTOOL_LICENSE = Proprietary
BMCTOOL_INSTALL_STAGING = YES
BMCTOOL_DEPENDENCIES = host-pkgconf

BMCTOOL_CONF_OPTS = \
	-DBMCTOOL_COLLECTOR=$(if $(filter y,$(BR2_PACKAGE_BMCTOOL_COLLECTOR)),ON,OFF) \
	-DBMCTOOL_REDFISH=$(if $(filter y,$(BR2_PACKAGE_BMCTOOL_REDFISH)),ON,OFF) \
	-DBMCTOOL_IPMI=$(if $(filter y,$(BR2_PACKAGE_BMCTOOL_IPMI)),ON,OFF) \
	-DBMCTOOL_PMCP=$(if $(filter y,$(BR2_PACKAGE_BMCTOOL_PMCP)),ON,OFF)

ifeq ($(BR2_PACKAGE_BMCTOOL_REDFISH),y)
BMCTOOL_DEPENDENCIES += libcurl cjson
endif

ifeq ($(BR2_PACKAGE_BMCTOOL_IPMI),y)
BMCTOOL_DEPENDENCIES += freeipmi
endif

# Previous package versions installed these as separate applications. Their
# functionality now lives in bmctool_test; remove stale files on incremental
# target/staging installs as well as on clean builds.
define BMCTOOL_REMOVE_LEGACY_APPS
	$(RM) -f $(addprefix $(TARGET_DIR)/usr/bin/,bmctool_telemetry bmctool_epdu_decode) \
		$(addprefix $(STAGING_DIR)/usr/bin/,bmctool_telemetry bmctool_epdu_decode)
endef
BMCTOOL_POST_INSTALL_TARGET_HOOKS += BMCTOOL_REMOVE_LEGACY_APPS

$(eval $(cmake-package))

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

# Public headers now use functional directories. Keep only the umbrella
# and shared types at the include root on incremental package installs.
BMCTOOL_LEGACY_PUBLIC_HEADERS = \
	bmctool_connection.h bmctool_device.h bmctool_policy.h \
	bmctool_collector.h bmctool_management.h bmctool_inventory.h \
	bmctool_epdu.h bmctool_epdu_limits.h bmctool_epdu_config.h \
	bmctool_epdu_mapping_config.h bmctool_csv.h bmctool_device_profiles.h \
	bmctool_source_config.h bmctool_output.h bmctool_output_queue.h \
	bmctool_text.h bmctool_clock.h bmctool_string.h \
	connection/bmctool_connection.h device/bmctool_device.h \
	device/bmctool_backoff.h collector/bmctool_collector.h \
	management/bmctool_management.h inventory/bmctool_inventory.h

define BMCTOOL_REMOVE_LEGACY_PUBLIC_HEADERS
	$(RM) -f $(addprefix $(TARGET_DIR)/usr/include/bmctool/,$(BMCTOOL_LEGACY_PUBLIC_HEADERS)) \
		$(addprefix $(STAGING_DIR)/usr/include/bmctool/,$(BMCTOOL_LEGACY_PUBLIC_HEADERS))
	-rmdir $(addprefix $(TARGET_DIR)/usr/include/bmctool/,connection device collector management inventory) \
		$(addprefix $(STAGING_DIR)/usr/include/bmctool/,connection device collector management inventory) 2>/dev/null
endef
BMCTOOL_POST_INSTALL_TARGET_HOOKS += BMCTOOL_REMOVE_LEGACY_PUBLIC_HEADERS

$(eval $(cmake-package))

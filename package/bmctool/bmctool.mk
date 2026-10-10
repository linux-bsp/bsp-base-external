################################################################################
# bmctool
################################################################################

BMCTOOL_SITE = $(TOPDIR)/../bmctool
BMCTOOL_SITE_METHOD = local
BMCTOOL_LICENSE = Proprietary
BMCTOOL_INSTALL_STAGING = YES
BMCTOOL_DEPENDENCIES = host-pkgconf

BMCTOOL_CONF_OPTS = \
	-DBMC_COLLECTOR=$(if $(filter y,$(BR2_PACKAGE_BMCTOOL_COLLECTOR)),ON,OFF) \
	-DBMC_REDFISH=$(if $(filter y,$(BR2_PACKAGE_BMCTOOL_REDFISH)),ON,OFF) \
	-DBMC_IPMI=$(if $(filter y,$(BR2_PACKAGE_BMCTOOL_IPMI)),ON,OFF) \
	-DBMC_PMCP=$(if $(filter y,$(BR2_PACKAGE_BMCTOOL_PMCP)),ON,OFF)

ifeq ($(BR2_PACKAGE_BMCTOOL_REDFISH),y)
BMCTOOL_DEPENDENCIES += libcurl cjson
endif

ifeq ($(BR2_PACKAGE_BMCTOOL_IPMI),y)
BMCTOOL_DEPENDENCIES += freeipmi
endif

$(eval $(cmake-package))

################################################################################
# libbmc
################################################################################

LIBBMC_SITE = $(TOPDIR)/../libbmc
LIBBMC_SITE_METHOD = local
LIBBMC_LICENSE = Proprietary
LIBBMC_INSTALL_STAGING = YES
LIBBMC_DEPENDENCIES = host-pkgconf

LIBBMC_CONF_OPTS = \
	-DBMC_COLLECTOR=$(if $(filter y,$(BR2_PACKAGE_LIBBMC_COLLECTOR)),ON,OFF) \
	-DBMC_REDFISH=$(if $(filter y,$(BR2_PACKAGE_LIBBMC_REDFISH)),ON,OFF) \
	-DBMC_IPMI=$(if $(filter y,$(BR2_PACKAGE_LIBBMC_IPMI)),ON,OFF) \
	-DBMC_PMCP=$(if $(filter y,$(BR2_PACKAGE_LIBBMC_PMCP)),ON,OFF)

ifeq ($(BR2_PACKAGE_LIBBMC_REDFISH),y)
LIBBMC_DEPENDENCIES += libcurl cjson
endif

ifeq ($(BR2_PACKAGE_LIBBMC_IPMI),y)
LIBBMC_DEPENDENCIES += freeipmi
endif

$(eval $(cmake-package))

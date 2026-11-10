# EDK is pinned by the surrounding workspace Git submodule.
EDK_SITE = $(BR2_EXTERNAL_LINUX_BSP_PATH)/../edk
EDK_VERSION = $(strip $(shell cat "$(EDK_SITE)/VERSION"))
EDK_SITE_METHOD = local
EDK_LICENSE = Proprietary, GPL-2.0+
EDK_DEPENDENCIES = host-pkgconf host-flex host-bison host-cmake
EDK_INSTALL_STAGING = YES
EDK_SUPPORTS_IN_SOURCE_BUILD = NO
EDK_OVERRIDE_SRCDIR_RSYNC_EXCLUSIONS = --exclude='.build' --exclude='build' \
    --exclude='__pycache__' --exclude='*.o' --exclude='*.a' --exclude='*.ko' \
    --exclude='*.mod' --exclude='*.mod.c' --exclude='.*.cmd' \
    --exclude='Module.symvers' --exclude='modules.order' --exclude='.tmp_versions'
EDK_CONF_OPTS = -DCONFIG_FILE=$(@D)/buildroot.config \
    -DEDK_SOURCE_DIR=$(EDK_SITE) \
    -DCMAKE_BUILD_TYPE=$(call qstrip,$(BR2_PACKAGE_EDK_BUILD_TYPE))
EDK_CONF_ENV = HOSTCC="$(HOSTCC)"

ifeq ($(BR2_PACKAGE_EDK_WEB),y)
EDK_DEPENDENCIES += cjson lighttpd
endif
ifeq ($(BR2_PACKAGE_EDK_FWCTL),y)
EDK_DEPENDENCIES += dtc libcurl openssl libubootenv
endif
ifeq ($(BR2_PACKAGE_EDK_FWCTLD),y)
EDK_DEPENDENCIES += busybox
endif
ifeq ($(BR2_PACKAGE_EDK_LOGCTL),y)
EDK_DEPENDENCIES += busybox libcurl openssl zlib
endif
ifeq ($(BR2_PACKAGE_EDK_TIMECTL),y)
EDK_DEPENDENCIES += libcurl openssl
endif

# Buildroot owns component selection; Kconfig normalizes this native seed.
define EDK_CONFIGURE_SELECTION
    $(INSTALL) -D -m 0644 $(@D)/configs/$(call qstrip,$(BR2_PACKAGE_EDK_DEFCONFIG)) $(@D)/buildroot.config
    $(call KCONFIG_SET_OPT,CONFIG_ARCH,"$(KERNEL_ARCH)",$(@D)/buildroot.config)
    $(call KCONFIG_SET_OPT,CONFIG_PDM,$(if $(filter y,$(BR2_PACKAGE_EDK_PDM)),m,n),$(@D)/buildroot.config)
    $(call KCONFIG_SET_OPT,CONFIG_PDEBUG_WEB,$(if $(filter y,$(BR2_PACKAGE_EDK_WEB)),y,n),$(@D)/buildroot.config)
    $(call KCONFIG_SET_OPT,CONFIG_FWCTL,$(if $(filter y,$(BR2_PACKAGE_EDK_FWCTL)),y,n),$(@D)/buildroot.config)
    $(call KCONFIG_SET_OPT,CONFIG_FWCTLD,$(if $(filter y,$(BR2_PACKAGE_EDK_FWCTLD)),y,n),$(@D)/buildroot.config)
    $(call KCONFIG_SET_OPT,CONFIG_LOGCTL,$(if $(filter y,$(BR2_PACKAGE_EDK_LOGCTL)),y,n),$(@D)/buildroot.config)
    $(call KCONFIG_SET_OPT,CONFIG_TIMECTL,$(if $(filter y,$(BR2_PACKAGE_EDK_TIMECTL)),y,n),$(@D)/buildroot.config)
    $(foreach option,DMSERVER DMCLI MANAGEMENT_TESTS TRANSFER_TESTS,$(call KCONFIG_DISABLE_OPT,CONFIG_$(option),$(@D)/buildroot.config)$(sep))
endef
EDK_PRE_CONFIGURE_HOOKS += EDK_CONFIGURE_SELECTION

EDK_INSTALL_STAGING_OPTS = --component libraries
define EDK_INSTALL_HEADERS
    $(if $(filter y,$(BR2_PACKAGE_EDK_INSTALL_HEADERS)),DESTDIR=$(STAGING_DIR) $(BR2_CMAKE) --install $(EDK_BUILDDIR) --component headers)
endef
EDK_POST_INSTALL_STAGING_HOOKS += EDK_INSTALL_HEADERS

define EDK_INSTALL_DEFAULTS
    $(if $(filter y,$(BR2_PACKAGE_EDK_FWCTLD)),$(INSTALL) -D -m 0644 $(EDK_PKGDIR)/fwctld.default $(TARGET_DIR)/etc/default/fwctld)
    $(if $(filter y,$(BR2_PACKAGE_EDK_LOGCTL)),$(INSTALL) -d $(TARGET_DIR)/data)
endef
EDK_POST_INSTALL_TARGET_HOOKS += EDK_INSTALL_DEFAULTS

define EDK_INSTALL_INIT_SYSV
	$(if $(filter y,$(BR2_PACKAGE_EDK_FWCTLD)),$(INSTALL) -D -m 0755 $(EDK_PKGDIR)/S98fwctld $(TARGET_DIR)/etc/init.d/S98fwctld)
	$(if $(filter y,$(BR2_PACKAGE_EDK_LOGCTL)),$(INSTALL) -D -m 0755 $(EDK_PKGDIR)/S01logctld $(TARGET_DIR)/etc/init.d/S01logctld)
	$(if $(filter y,$(BR2_PACKAGE_EDK_TIMECTL)),$(INSTALL) -D -m 0755 $(EDK_PKGDIR)/S02timectld $(TARGET_DIR)/etc/init.d/S02timectld)
endef

define EDK_INSTALL_INIT_SYSTEMD
    DESTDIR=$(TARGET_DIR) $(BR2_CMAKE) --install $(EDK_BUILDDIR) --component services
endef

ifeq ($(BR2_PACKAGE_EDK_PDM),y)
define EDK_KERNEL_METADATA
    $(HOST_DIR)/bin/cmake -DBUILD_DIR=$(EDK_BUILDDIR) -DCOMPILER=$(TARGET_CC) \
        -DSOURCE_DIR=$(EDK_SITE) -DARCH=$(KERNEL_ARCH) \
        -DKERNEL=$(LINUX_VERSION_PROBED) -P $(@D)/scripts/cmake/build_info.cmake
endef
EDK_POST_BUILD_HOOKS += EDK_KERNEL_METADATA
EDK_MODULE_SUBDIRS = kernel
EDK_MODULE_MAKE_OPTS = PDM_BUILD_DIR=$(EDK_BUILDDIR) MO=$(EDK_BUILDDIR)/modules INSTALL_MOD_DIR=extra/pdm
$(eval $(kernel-module))
endif

HOST_EDK_VERSION = $(EDK_VERSION)
HOST_EDK_SITE = $(EDK_SITE)
HOST_EDK_SITE_METHOD = local
HOST_EDK_SUPPORTS_IN_SOURCE_BUILD = NO
HOST_EDK_OVERRIDE_SRCDIR_RSYNC_EXCLUSIONS = $(EDK_OVERRIDE_SRCDIR_RSYNC_EXCLUSIONS)
HOST_EDK_DEPENDENCIES = host-flex host-bison host-pkgconf host-cmake
ifeq ($(BR2_PACKAGE_HOST_EDK_DMSERVER),y)
HOST_EDK_DEPENDENCIES += host-sqlite host-zlib host-uboot-tools host-openssl
endif
ifeq ($(BR2_PACKAGE_HOST_EDK_DMCLI),y)
HOST_EDK_DEPENDENCIES += host-libcurl host-openssl
endif
HOST_EDK_CONF_OPTS = -DCONFIG_FILE=$(@D)/buildroot.config -DEDK_SOURCE_DIR=$(EDK_SITE)
HOST_EDK_CONF_ENV = HOSTCC="$(HOSTCC)"
HOST_EDK_INSTALL_OPTS = --component host-tools

define HOST_EDK_CONFIGURE_SELECTION
    $(INSTALL) -D -m 0644 $(@D)/configs/management_base_defconfig $(@D)/buildroot.config
    $(call KCONFIG_SET_OPT,CONFIG_ARCH,"$(HOSTARCH)",$(@D)/buildroot.config)
    $(call KCONFIG_SET_OPT,CONFIG_DMSERVER,$(if $(filter y,$(BR2_PACKAGE_HOST_EDK_DMSERVER)),y,n),$(@D)/buildroot.config)
    $(call KCONFIG_SET_OPT,CONFIG_DMCLI,$(if $(filter y,$(BR2_PACKAGE_HOST_EDK_DMCLI)),y,n),$(@D)/buildroot.config)
endef
HOST_EDK_PRE_CONFIGURE_HOOKS += HOST_EDK_CONFIGURE_SELECTION

$(eval $(cmake-package))
$(eval $(host-cmake-package))

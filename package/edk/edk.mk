# EDK is pinned by the surrounding workspace Git submodule.
EDK_VERSION = 2.0.0
EDK_SITE = $(BR2_EXTERNAL_LINUX_BSP_PATH)/../edk
EDK_SITE_METHOD = local
EDK_LICENSE = Proprietary, GPL-2.0+
EDK_DEPENDENCIES = host-python3 host-pkgconf host-cmake host-flex host-bison
EDK_INSTALL_STAGING = YES
EDK_BUILD_OUTPUT = $(@D)/.build/target
EDK_MODULES_OUTPUT = $(EDK_BUILD_OUTPUT)/modules
EDK_MODULE_EXTRA_DIR = extra/pdm
EDK_OVERRIDE_SRCDIR_RSYNC_EXCLUSIONS = --exclude='.build' --exclude='build' \
    --exclude='__pycache__' --exclude='*.o' --exclude='*.a' --exclude='*.ko' \
    --exclude='*.mod' --exclude='*.mod.c' --exclude='.*.cmd' \
    --exclude='Module.symvers' --exclude='modules.order' --exclude='.tmp_versions'
ifeq ($(BR2_PACKAGE_EDK_PDM),y)
EDK_DEPENDENCIES += linux
endif
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
EDK_SOURCE_ID = $(shell git -C "$(EDK_SITE)" describe --always --dirty 2>/dev/null || echo archive)
EDK_MAKE_OPTS = EDK_SOURCE_REVISION="$(EDK_SOURCE_ID)" BUILD_DIR="$(EDK_BUILD_OUTPUT)" \
    PYTHON3="$(HOST_DIR)/bin/python3" HOSTCC="$(HOSTCC)" \
    MODULES_BUILD_DIR="$(EDK_MODULES_OUTPUT)" KERNEL_SRC="$(LINUX_DIR)" \
    ARCH="$(KERNEL_ARCH)" CROSS_COMPILE="$(TARGET_CROSS)" CC="$(TARGET_CC)" \
    CMAKE_BUILD_TYPE="$(call qstrip,$(BR2_PACKAGE_EDK_BUILD_TYPE))" \
    CMAKE_TOOLCHAIN_FILE="$(HOST_DIR)/share/buildroot/toolchainfile.cmake" \
    CMAKE_EXTRA_FLAGS='-DCONFIG_FILE="$(EDK_BUILD_OUTPUT).config" -DCMAKE_C_FLAGS="$(filter-out -O% -g%,$(TARGET_CFLAGS))" -DCMAKE_EXE_LINKER_FLAGS="$(TARGET_LDFLAGS)"' \
    CMAKE_INSTALL_PREFIX="/usr"

define EDK_CONFIGURE_CMDS
    $(HOST_DIR)/bin/python3 $(@D)/scripts/buildroot_config.py \
        --preset $(@D)/configs/$(call qstrip,$(BR2_PACKAGE_EDK_DEFCONFIG)) \
        --output $(EDK_BUILD_OUTPUT).config --arch "$(KERNEL_ARCH)" \
        --set PDM=$(if $(filter y,$(BR2_PACKAGE_EDK_PDM)),m,n) \
        --set PDEBUG_WEB=$(if $(filter y,$(BR2_PACKAGE_EDK_WEB)),y,n) \
        --set FWCTL=$(if $(filter y,$(BR2_PACKAGE_EDK_FWCTL)),y,n) \
        --set FWCTLD=$(if $(filter y,$(BR2_PACKAGE_EDK_FWCTLD)),y,n) \
        --set LOGCTL=$(if $(filter y,$(BR2_PACKAGE_EDK_LOGCTL)),y,n) \
        --set TIMECTL=$(if $(filter y,$(BR2_PACKAGE_EDK_TIMECTL)),y,n) \
        --set DEVICE_SERVER=n --set OTA_CLI=n --set MANAGEMENT_TESTS=n --set TRANSFER_TESTS=n
    $(TARGET_MAKE_ENV) $(MAKE) -C $(@D) $(EDK_MAKE_OPTS) configure
    $(HOST_DIR)/bin/python3 $(@D)/scripts/check_buildroot.py --build-dir $(EDK_BUILD_OUTPUT) --web "$(BR2_PACKAGE_EDK_WEB)"
endef

define EDK_BUILD_CMDS
    $(TARGET_MAKE_ENV) $(MAKE) -C $(@D) $(EDK_MAKE_OPTS) all
endef

define EDK_INSTALL_TARGET_CMDS
    $(TARGET_MAKE_ENV) $(MAKE) -C $(@D) $(EDK_MAKE_OPTS) install DESTDIR=$(TARGET_DIR)
    $(if $(filter y,$(BR2_PACKAGE_EDK_PDM)),$(INSTALL) -D -m 0644 $(EDK_MODULES_OUTPUT)/pdm.ko $(TARGET_DIR)/lib/modules/$(LINUX_VERSION_PROBED)/$(EDK_MODULE_EXTRA_DIR)/pdm.ko)
    $(if $(filter y,$(BR2_PACKAGE_EDK_FWCTLD)),$(INSTALL) -D -m 0644 $(EDK_PKGDIR)/fwctld.default $(TARGET_DIR)/etc/default/fwctld)
    $(if $(filter y,$(BR2_PACKAGE_EDK_LOGCTL)),$(INSTALL) -d $(TARGET_DIR)/data)
endef

define EDK_INSTALL_STAGING_CMDS
    DESTDIR=$(STAGING_DIR) $(HOST_DIR)/bin/cmake --install $(EDK_BUILD_OUTPUT) --prefix /usr --component libraries
    $(if $(filter y,$(BR2_PACKAGE_EDK_INSTALL_HEADERS)),$(MAKE) -C $(@D) $(EDK_MAKE_OPTS) install_headers DESTDIR=$(STAGING_DIR))
endef

define EDK_INSTALL_INIT_SYSV
	$(if $(filter y,$(BR2_PACKAGE_EDK_FWCTLD)),$(INSTALL) -D -m 0755 $(EDK_PKGDIR)/S98fwctld $(TARGET_DIR)/etc/init.d/S98fwctld)
	$(if $(filter y,$(BR2_PACKAGE_EDK_LOGCTL)),$(INSTALL) -D -m 0755 $(EDK_PKGDIR)/S01logctld $(TARGET_DIR)/etc/init.d/S01logctld)
	$(if $(filter y,$(BR2_PACKAGE_EDK_TIMECTL)),$(INSTALL) -D -m 0755 $(EDK_PKGDIR)/S02timectld $(TARGET_DIR)/etc/init.d/S02timectld)
endef

# Native systemd units run daemons in the foreground; no second supervisor.
define EDK_INSTALL_INIT_SYSTEMD
    DESTDIR=$(TARGET_DIR) $(HOST_DIR)/bin/cmake --install $(EDK_BUILD_OUTPUT) --prefix /usr --component services
endef


HOST_EDK_VERSION = $(EDK_VERSION)
HOST_EDK_SITE = $(EDK_SITE)
HOST_EDK_SITE_METHOD = local
HOST_EDK_OVERRIDE_SRCDIR_RSYNC_EXCLUSIONS = $(EDK_OVERRIDE_SRCDIR_RSYNC_EXCLUSIONS)
HOST_EDK_DEPENDENCIES = host-cmake host-python3 host-flex host-bison host-pkgconf
ifeq ($(BR2_PACKAGE_HOST_EDK_SERVER),y)
HOST_EDK_DEPENDENCIES += host-sqlite host-zlib host-uboot-tools host-openssl
endif
ifeq ($(BR2_PACKAGE_HOST_EDK_OTA_CLI),y)
HOST_EDK_DEPENDENCIES += host-libcurl host-openssl
endif

define HOST_EDK_CONFIGURE_CMDS
    $(HOST_DIR)/bin/python3 $(@D)/scripts/buildroot_config.py \
        --preset $(@D)/configs/management_base_defconfig --output $(@D)/.build/host.config --arch "$(HOSTARCH)" \
        --set DEVICE_SERVER=$(if $(filter y,$(BR2_PACKAGE_HOST_EDK_SERVER)),y,n) \
        --set OTA_CLI=$(if $(filter y,$(BR2_PACKAGE_HOST_EDK_OTA_CLI)),y,n)
    $(HOST_MAKE_ENV) $(HOST_DIR)/bin/cmake -S $(@D) -B $(@D)/.build/host \
        -DCONFIG_FILE=$(@D)/.build/host.config -DCMAKE_C_COMPILER="$(HOSTCC)" \
        -DCMAKE_PREFIX_PATH="$(HOST_DIR)" -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_FLAGS="$(filter-out -O% -g%,$(HOST_CFLAGS))" -DCMAKE_EXE_LINKER_FLAGS="$(HOST_LDFLAGS)"
endef

define HOST_EDK_BUILD_CMDS
    $(HOST_MAKE_ENV) $(HOST_DIR)/bin/cmake --build $(@D)/.build/host --parallel $(PARALLEL_JOBS)
endef

define HOST_EDK_INSTALL_CMDS
    $(HOST_MAKE_ENV) $(HOST_DIR)/bin/cmake --install $(@D)/.build/host --prefix $(HOST_DIR) --component host-tools
endef

$(eval $(generic-package))
$(eval $(host-generic-package))

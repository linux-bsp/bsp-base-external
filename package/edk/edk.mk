################################################################################
#
# edk
#
################################################################################

# Default: use the canonical EDK git repository.
# Product trees can set EDK_OVERRIDE_SRCDIR in BR2_PACKAGE_OVERRIDE_FILE for
# local development or board integration testing.
EDK_VERSION = v1.0.0
EDK_SITE = git@192.168.10.250:ssdc/bsp/EDK.git
EDK_SITE_METHOD = git
EDK_LICENSE = Proprietary
EDK_INSTALL_TARGET = YES
EDK_ADD_TOOLCHAIN_DEPENDENCY = NO

# Dependencies - Kconfig + CMake/Kbuild build system
EDK_DEPENDENCIES = host-python3 host-pkgconf host-cmake host-flex host-bison linux



ifeq ($(BR2_PACKAGE_EDK_WEB),y)
EDK_DEPENDENCIES += cjson lighttpd
endif

# Local override builds must not sync generated build directories or stale
# Kbuild products from the EDK workspace into Buildroot. Linux refuses external
# modules when modules.order exists in the module source tree.
EDK_OVERRIDE_SRCDIR_RSYNC_EXCLUSIONS = \
	--exclude='/device-manager' \
	--exclude='/user/transfer/build' \
	--exclude='__pycache__' \
	--exclude='.build' \
	--exclude='_build' \
	--exclude='*.o' \
	--exclude='*.o.d' \
	--exclude='*.ko' \
	--exclude='*.mod' \
	--exclude='*.mod.c' \
	--exclude='.*.cmd' \
	--exclude='Module.symvers' \
	--exclude='modules.order' \
	--exclude='.tmp_versions'

# Kconfig configuration to use (from Buildroot config)
EDK_KCONFIG_DEFCONFIG = $(call qstrip,$(BR2_PACKAGE_EDK_DEFCONFIG))

# Build type from Buildroot configuration
EDK_BUILD_TYPE = $(call qstrip,$(BR2_PACKAGE_EDK_BUILD_TYPE))

# Build in-tree for Buildroot (output/build/edk/.build)
EDK_BUILD_OUTPUT = $(@D)/.build/target
EDK_MODULES_OUTPUT = $(EDK_BUILD_OUTPUT)/modules
EDK_MODULE_EXTRA_DIR = extra/pdm

EDK_MAKE_OPTS = \
	BUILD_DIR="$(EDK_BUILD_OUTPUT)" \
	EDK_SOURCE_REVISION="$(EDK_VERSION)" \
	PYTHON3="$(HOST_DIR)/bin/python3" \
	HOSTCC="$(HOSTCC)" \
	MODULES_BUILD_DIR="$(EDK_MODULES_OUTPUT)" \
	KERNEL_SRC="$(LINUX_DIR)" \
	ARCH="$(KERNEL_ARCH)" \
	CROSS_COMPILE="$(TARGET_CROSS)" \
	CC="$(TARGET_CC)" \
	CMAKE_BUILD_TYPE="$(EDK_BUILD_TYPE)" \
	CMAKE_TOOLCHAIN_FILE="$(HOST_DIR)/share/buildroot/toolchainfile.cmake" \
	CMAKE_EXTRA_FLAGS='-DCMAKE_C_FLAGS="$(filter-out -O% -g%,$(TARGET_CFLAGS))" -DCMAKE_EXE_LINKER_FLAGS="$(TARGET_LDFLAGS)"' \
	CMAKE_INSTALL_PREFIX="/usr"

EDK_CHECK_FEATURES = $(HOST_DIR)/bin/python3 $(@D)/scripts/check_buildroot.py \
    --build-dir "$(EDK_BUILD_OUTPUT)" \
    --web "$(BR2_PACKAGE_EDK_WEB)"

# Configure using make (kernel-style interface)
# This loads the defconfig and generates .config + autoconf.h
define EDK_CONFIGURE_CMDS
	@test -n "$(EDK_KCONFIG_DEFCONFIG)" || { \
		echo "EDK: BR2_PACKAGE_EDK_DEFCONFIG must be set"; \
		exit 1; \
	}
	@echo "EDK: Loading defconfig $(EDK_KCONFIG_DEFCONFIG)"
	$(MAKE) -C $(@D) $(EDK_MAKE_OPTS) $(EDK_KCONFIG_DEFCONFIG)
	$(EDK_CHECK_FEATURES)
	@echo "EDK: Configuration loaded successfully"
endef

# Build userspace libraries and kernel modules.
define EDK_BUILD_CMDS
	@echo "EDK: Building with configuration $(EDK_KCONFIG_DEFCONFIG)"
	$(EDK_CHECK_FEATURES)
	$(TARGET_MAKE_ENV) $(MAKE) -C $(@D) $(EDK_MAKE_OPTS) all
endef

# Clean build artifacts (keep configuration)
define EDK_CLEAN_CMDS
	@echo "EDK: Cleaning build artifacts"
	-$(MAKE) -C $(@D) $(EDK_MAKE_OPTS) clean
endef

# Complete clean (remove configuration and build directory)
define EDK_DISTCLEAN_CMDS
	@echo "EDK: Complete clean"
	-$(MAKE) -C $(@D) $(EDK_MAKE_OPTS) distclean
endef

# Install userspace shared libraries, tools, and kernel modules to target.
define EDK_INSTALL_TARGET_CMDS
	@echo "EDK: Installing to target"
	$(MAKE) -C $(@D) \
		BUILD_DIR="$(EDK_BUILD_OUTPUT)" \
		CMAKE_INSTALL_PREFIX="/usr" \
		install DESTDIR=$(TARGET_DIR)
	kernel_release="$(LINUX_VERSION_PROBED)"; \
	if [ -z "$$kernel_release" ]; then \
		kernel_release="$$($(MAKE) -C "$(LINUX_DIR)" \
			ARCH="$(KERNEL_ARCH)" \
			CROSS_COMPILE="$(TARGET_CROSS)" \
			--no-print-directory -s kernelrelease)"; \
	fi; \
	module_install_dir="$(TARGET_DIR)/lib/modules/$$kernel_release/$(EDK_MODULE_EXTRA_DIR)"; \
	$(INSTALL) -d "$$module_install_dir"; \
	modules_found=0; \
	for module in "$(EDK_MODULES_OUTPUT)"/*.ko; do \
		[ -e "$$module" ] || continue; \
		modules_found=1; \
		$(INSTALL) -m 0644 "$$module" "$$module_install_dir/$$(basename "$$module")"; \
	done; \
	if [ "$$modules_found" -eq 0 ]; then \
		echo "EDK: no kernel modules found in $(EDK_MODULES_OUTPUT)"; \
		exit 1; \
	fi
	@echo "EDK: Target installation complete"
endef

# Optional: Install development headers and userspace shared libraries to staging.
ifeq ($(BR2_PACKAGE_EDK_INSTALL_HEADERS),y)
EDK_INSTALL_STAGING = YES
define EDK_INSTALL_STAGING_CMDS
	@echo "EDK: Installing libraries to staging"
	$(MAKE) -C $(@D) \
		BUILD_DIR="$(EDK_BUILD_OUTPUT)" \
		CMAKE_INSTALL_PREFIX="/usr" \
		install DESTDIR=$(STAGING_DIR)
	@echo "EDK: Installing development headers to staging"
	$(MAKE) -C $(@D) \
		BUILD_DIR="$(EDK_BUILD_OUTPUT)" \
		CMAKE_INSTALL_PREFIX="/usr" \
		install_headers DESTDIR=$(STAGING_DIR)
	@echo "EDK: Staging installation complete"
endef
endif

$(eval $(generic-package))

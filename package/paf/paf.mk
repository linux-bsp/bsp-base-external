################################################################################
#
# paf
#
################################################################################

# Default: use the canonical PAF git repository.
# Product trees can set PAF_OVERRIDE_SRCDIR in BR2_PACKAGE_OVERRIDE_FILE for
# local development or board integration testing.
PAF_VERSION = v1.0.0
PAF_SITE = https://github.com/linux-bsp/paf.git
PAF_SITE_METHOD = git
PAF_LICENSE = Proprietary
PAF_INSTALL_TARGET = YES
PAF_ADD_TOOLCHAIN_DEPENDENCY = NO

# Dependencies - Kconfig + CMake/Kbuild build system
PAF_DEPENDENCIES = host-pkgconf host-cmake host-flex host-bison linux

ifeq ($(BR2_PACKAGE_PAF_BMC_REDFISH),y)
PAF_DEPENDENCIES += libcurl cjson
endif

ifeq ($(BR2_PACKAGE_PAF_BMC_IPMI),y)
PAF_DEPENDENCIES += freeipmi
endif

ifeq ($(BR2_PACKAGE_PAF_FW),y)
PAF_DEPENDENCIES += dtc libcurl openssl
PAF_LICENSE += , GPL-2.0+
PAF_LICENSE_FILES += LICENSE.GPL-2.0
endif

ifeq ($(BR2_PACKAGE_PAF_FW_FIT_SIGNATURE),y)
PAF_DEPENDENCIES += uboot-tools
endif

# Local override builds must not sync generated build directories or stale
# Kbuild products from the PAF workspace into Buildroot. Linux refuses external
# modules when modules.order exists in the module source tree.
PAF_OVERRIDE_SRCDIR_RSYNC_EXCLUSIONS = \
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
PAF_KCONFIG_DEFCONFIG = $(call qstrip,$(BR2_PACKAGE_PAF_DEFCONFIG))

# Build type from Buildroot configuration
PAF_BUILD_TYPE = $(call qstrip,$(BR2_PACKAGE_PAF_BUILD_TYPE))

# Build in-tree for Buildroot (output/build/paf/.build)
PAF_BUILD_OUTPUT = $(@D)/.build
PAF_MODULES_OUTPUT = $(@D)/.build/modules
PAF_MODULE_EXTRA_DIR = extra/pdm

PAF_MAKE_OPTS = \
	BUILD_DIR="$(PAF_BUILD_OUTPUT)" \
	MODULES_BUILD_DIR="$(PAF_MODULES_OUTPUT)" \
	BR2_EXTERNAL=1 \
	KERNEL_SRC="$(LINUX_DIR)" \
	ARCH="$(KERNEL_ARCH)" \
	CROSS_COMPILE="$(TARGET_CROSS)" \
	CC="$(TARGET_CC)" \
	CMAKE_BUILD_TYPE="$(PAF_BUILD_TYPE)" \
	CMAKE_TOOLCHAIN_FILE="$(HOST_DIR)/share/buildroot/toolchainfile.cmake" \
	CMAKE_EXTRA_FLAGS='-DCMAKE_C_COMPILER="$(TARGET_CC)" -DCMAKE_C_FLAGS="$(TARGET_CFLAGS)" -DCMAKE_EXE_LINKER_FLAGS="$(TARGET_LDFLAGS)"' \
	CMAKE_INSTALL_PREFIX="/usr"

# Configure using make (kernel-style interface)
# This loads the defconfig and generates .config + autoconf.h
define PAF_CONFIGURE_CMDS
	@test -n "$(PAF_KCONFIG_DEFCONFIG)" || { \
		echo "PAF: BR2_PACKAGE_PAF_DEFCONFIG must be set"; \
		exit 1; \
	}
	@echo "PAF: Loading defconfig $(PAF_KCONFIG_DEFCONFIG)"
	$(MAKE) -C $(@D) $(PAF_MAKE_OPTS) $(PAF_KCONFIG_DEFCONFIG)
	@echo "PAF: Configuration loaded successfully"
endef

# Build userspace libraries and kernel modules.
define PAF_BUILD_CMDS
	@echo "PAF: Building with configuration $(PAF_KCONFIG_DEFCONFIG)"
	rm -f "$(PAF_BUILD_OUTPUT)/CMakeCache.txt"
	$(TARGET_MAKE_ENV) $(MAKE) -C $(@D) $(PAF_MAKE_OPTS) all
endef

# Clean build artifacts (keep configuration)
define PAF_CLEAN_CMDS
	@echo "PAF: Cleaning build artifacts"
	-$(MAKE) -C $(@D) clean
endef

# Complete clean (remove configuration and build directory)
define PAF_DISTCLEAN_CMDS
	@echo "PAF: Complete clean"
	-$(MAKE) -C $(@D) distclean
endef

# Install userspace shared libraries, tools, and kernel modules to target.
define PAF_INSTALL_TARGET_CMDS
	@echo "PAF: Installing to target"
	$(MAKE) -C $(@D) \
		BUILD_DIR="$(PAF_BUILD_OUTPUT)" \
		CMAKE_INSTALL_PREFIX="/usr" \
		install DESTDIR=$(TARGET_DIR)
	kernel_release="$(LINUX_VERSION_PROBED)"; \
	if [ -z "$$kernel_release" ]; then \
		kernel_release="$$($(MAKE) -C "$(LINUX_DIR)" \
			ARCH="$(KERNEL_ARCH)" \
			CROSS_COMPILE="$(TARGET_CROSS)" \
			--no-print-directory -s kernelrelease)"; \
	fi; \
	module_install_dir="$(TARGET_DIR)/lib/modules/$$kernel_release/$(PAF_MODULE_EXTRA_DIR)"; \
	$(INSTALL) -d "$$module_install_dir"; \
	modules_found=0; \
	for module in "$(PAF_MODULES_OUTPUT)"/*.ko; do \
		[ -e "$$module" ] || continue; \
		modules_found=1; \
		$(INSTALL) -m 0644 "$$module" "$$module_install_dir/$$(basename "$$module")"; \
	done; \
	if [ "$$modules_found" -eq 0 ]; then \
		echo "PAF: no kernel modules found in $(PAF_MODULES_OUTPUT)"; \
		exit 1; \
	fi
	@echo "PAF: Target installation complete"
endef

# Optional: Install development headers and userspace shared libraries to staging.
ifeq ($(BR2_PACKAGE_PAF_INSTALL_HEADERS),y)
PAF_INSTALL_STAGING = YES
define PAF_INSTALL_STAGING_CMDS
	@echo "PAF: Installing libraries to staging"
	$(MAKE) -C $(@D) \
		BUILD_DIR="$(PAF_BUILD_OUTPUT)" \
		CMAKE_INSTALL_PREFIX="/usr" \
		install DESTDIR=$(STAGING_DIR)
	@echo "PAF: Installing development headers to staging"
	$(MAKE) -C $(@D) \
		BUILD_DIR="$(PAF_BUILD_OUTPUT)" \
		CMAKE_INSTALL_PREFIX="/usr" \
		install_headers DESTDIR=$(STAGING_DIR)
	@echo "PAF: Staging installation complete"
endef
endif

$(eval $(generic-package))

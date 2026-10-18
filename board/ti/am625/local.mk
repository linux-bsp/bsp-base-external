# Local source overrides for the TI AM62x board.
#
# Keep product-specific source-tree selections in the external tree instead of
# relying on an untracked local.mk in the Buildroot root directory.

UBOOT_OVERRIDE_SRCDIR = $(TOPDIR)/../uboot/u-boot-2026.04
LINUX_OVERRIDE_SRCDIR = $(TOPDIR)/../linux/linux-7.0

# EDK local source used when BR2_PACKAGE_EDK is enabled.
EDK_OVERRIDE_SRCDIR = $(TOPDIR)/../edk
BMCTOOL_OVERRIDE_SRCDIR = $(TOPDIR)/../bmctool

# TI K3 R5 Loader uses the same U-Boot source tree as the A53 U-Boot
TI_K3_R5_LOADER_OVERRIDE_SRCDIR = $(TOPDIR)/../uboot/u-boot-2026.04

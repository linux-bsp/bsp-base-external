# Alientek AM62x Board Files

`configs/alientek_am62x_defconfig` selects the Alientek AM62x device tree,
kernel and U-Boot configurations, BusyBox configuration, root filesystem
overlay, and local source overrides in this directory.

`layout/genimage_ti.cfg` builds the bootloader, kernel, and root filesystem
FIT components. `support/scripts/firmware-image.sh` then creates a release
manifest and uses `layout/genimage_sdcard.cfg` for the RAW A/B SD image.

The image contains two 64 KiB metadata copies, two 24 MiB kernel slots, and
two 128 MiB root filesystem slots. The first stage bootloader occupies the
start of the SD card, so interrupted updates to slot A can require reflashing.

The Redfish endpoint `192.168.10.201` is configured in
`rootfs-overlay/etc/paf/ptelemetryd.conf`. Set its `username`, create
`/etc/paf/bmc.password` on the target with the password on the first line
(mode 0600), then set `[daemon] enabled = true` to start telemetry collection.
Keep credentials out of the repository.

#!/usr/bin/env python3
"""Verify the actual generated FIT with the production device-manager parser; mutate only copies."""
import os
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

WORKSPACE=Path(__file__).resolve().parents[4]
HOST=Path(os.environ.get('HOST_DIR',WORKSPACE/'output/am625/host'))
IMAGES=Path(os.environ.get('FW_TEST_IMAGES', WORKSPACE/'output/am625/images'))
EDK=WORKSPACE/'device-manager/firmware'
FDT=WORKSPACE/'uboot/u-boot-2026.04/scripts/dtc/libfdt'

class FITIntegrity(unittest.TestCase):
    def test_recovery_ramdisk_is_verified(self):
        with tempfile.TemporaryDirectory(prefix='fw-fit-test-') as name:
            root=Path(name);source=root/'check.c';binary=root/'check'
            source.write_text(r'''
#include "dm_fw_fit_priv.h"
#include <string.h>
#include "dm/hwid.h"
/* Payload tests inject a fixed identity; environment backends have separate tests. */
int dm_hwid_read(const char *config, struct dm_hwid_status *result) {
    if (strcmp(config,"test-hwid")) return -1;
    strcpy(result->text,"1010001000110000");return 0;
}
const char *fw_component_name(enum fw_component c) {
    static const char *names[]={"bootloader","kernel","rootfs"};
    return c<FW_COMPONENT_COUNT ? names[c] : "invalid";
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    struct fw_layout layout={0}; struct fw_fit fit; struct fw_package package;
    strcpy(layout.hwid_config,"test-hwid");
    if (fw_fit_open(&fit,argv[1],&layout)) return 3;
    int rc=fw_fit_verify_package(&layout,&fit,&package);
    if (!rc) rc=fw_fit_recovery_capable(&fit);
    fw_fit_close(&fit);return rc ? 1 : 0;
}
''')
            subprocess.run(['cc','-D_POSIX_C_SOURCE=200809L','-std=c11','-Wall','-Wextra','-Werror',
                '-I'+str(EDK/'src'),'-I'+str(EDK.parent/'identity/include'),'-I'+str(FDT),'-I'+str(HOST/'include'),str(source),str(EDK/'src/dm_fw_fit.c'),
                str(FDT/'fdt.c'),str(FDT/'fdt_ro.c'),'-L'+str(HOST/'lib'),'-Wl,-rpath,'+str(HOST/'lib'),'-lcrypto','-o',str(binary)],check=True)
            fit=IMAGES/'release/kernel.itb';ramdisk=(IMAGES/'recovery.cpio.gz').read_bytes()
            self.assertEqual(subprocess.run([str(binary),str(fit)]).returncode,0)
            for n in range(2):
                aligned=root/f'alignment-{n}.itb';shutil.copyfile(fit,aligned)
                subprocess.run([str(HOST/'bin/fdtput'),'-t','s',str(aligned),'/',
                                'description','align'+'xxxx'*n],check=True)
                self.assertEqual(subprocess.run([str(binary),str(aligned)]).returncode,0)
            data=bytearray(fit.read_bytes());offset=data.find(ramdisk)
            self.assertGreaterEqual(offset,0)
            data[offset+len(ramdisk)//2]^=1
            broken=root/'corrupt-ramdisk.itb';broken.write_bytes(data)
            self.assertNotEqual(subprocess.run([str(binary),str(broken)]).returncode,0)
            missing=root/'no-recovery.itb';shutil.copyfile(fit,missing)
            subprocess.run([str(HOST/'bin/fdtput'),'-d',str(missing),'/configurations/conf-1','ramdisk'],check=True)
            self.assertNotEqual(subprocess.run([str(binary),str(missing)]).returncode,0)

    def test_inline_dtb_alignment_is_repeatable(self):
        spec=importlib.util.spec_from_file_location('identity_generator',WORKSPACE/'bsp-base-external/support/scripts/firmware-identity.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        dtb=next(IMAGES.glob('verity-*.dtb'))
        data=dtb.read_bytes()
        with tempfile.TemporaryDirectory(prefix='fit-alignment-') as name:
            base=Path(name)
            for index in range(2):
                fit=base/f'{index}.itb';shutil.copyfile(IMAGES/'release/kernel.itb',fit)
                if index:subprocess.run([str(HOST/'bin/fdtput'),'-t','x',str(fit),'/', 'test-padding'],check=True)
                before=fit.read_bytes().find(data)
                self.assertIn(before%8,(0,4))
                module.align_kernel_dtb(HOST,fit,dtb)
                self.assertEqual(fit.read_bytes().find(data)%8,0)
                aligned=fit.read_bytes()
                module.align_kernel_dtb(HOST,fit,dtb)
                self.assertEqual(fit.read_bytes(),aligned)

    def test_real_rootfs_fit_repair_on_regular_file(self):
        import hashlib
        with tempfile.TemporaryDirectory(prefix='fw-real-restore-') as name:
            root=Path(name); source=root/'restore.c'; binary=root/'restore'
            source.write_text(r'''
#include "dm/firmware.h"
#include "dm_fw_update_priv.h"
#include "dm_fw_fit_priv.h"
#include <assert.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include "dm/hwid.h"
/* Payload tests inject a fixed identity; environment backends have separate tests. */
int dm_hwid_read(const char *config, struct dm_hwid_status *result) {
    if (strcmp(config,"test-hwid")) return -1;
    strcpy(result->text,"1010001000110000");return 0;
}
int fw_update_release(const struct fw_layout *l, struct fw_storage *s, const char *p,
    uint32_t c, dm_fw_progress_fn f, void *u)
{ (void)l;(void)s;(void)p;(void)c;(void)f;(void)u;return -ENOTSUP; }
int main(int argc,char **argv) {
    assert(argc==5);
    int handle=dm_fw_open(argv[1]);assert(handle>0);
    assert(!dm_fw_initialize(handle,0));
    /* Factory initialization has no component version; bind the repair to this FIT. */
    struct fw_layout layout;struct fw_storage storage;struct fw_metadata metadata;
    struct fw_fit fit;struct fw_package package;
    fw_layout_defaults(&layout);
    assert(!fw_layout_load(&layout,argv[1]));assert(!fw_storage_open(&storage,&layout,true));
    assert(!fw_metadata_load(&storage,&metadata));assert(!fw_fit_open(&fit,argv[2],&layout));
    assert(!fw_fit_verify_package(&layout,&fit,&package));fw_fit_close(&fit);
    metadata.deployment[0].release_version=package.version;
    metadata.deployment[0].component[FW_COMPONENT_ROOTFS].version=package.version;
    metadata.deployment[0].component[FW_COMPONENT_ROOTFS].rollback_index=package.rollback_index;
    assert(!fw_metadata_save(&storage,&metadata));fw_storage_close(&storage);
    uint8_t digest[32],bad[32]={0};const char *digits="0123456789abcdef";
    for(unsigned i=0;i<32;i++) digest[i]=(strchr(digits,argv[4][2*i])-digits)*16+strchr(digits,argv[4][2*i+1])-digits;
    uint64_t bytes=strtoull(argv[3],NULL,10);
    assert(dm_fw_restore_rootfs(handle,0,argv[2],bytes,bad)==-EBADMSG);
    struct dm_fw_status before,after;
    assert(!dm_fw_get_status(handle,&before));
    assert(!dm_fw_restore_rootfs(handle,0,argv[2],bytes,digest));
    assert(!dm_fw_get_status(handle,&after));
    assert(!memcmp(&before,&after,sizeof(before)));
    assert(!dm_fw_close(handle));return 0;
}
''')
            modules=['dm_fw.c','dm_fw_identity.c','dm_fw_recovery.c','dm_fw_fit.c','dm_fw_layout.c',
                'dm_fw_metadata.c','dm_fw_storage.c','dm_fw_storage_block.c','dm_fw_storage_mtd.c']
            subprocess.run(['cc','-D_POSIX_C_SOURCE=200809L','-std=c11','-Wall','-Wextra','-Werror',
                '-I'+str(EDK/'src'),'-I'+str(EDK/'include'),'-I'+str(EDK.parent/'identity/include'),'-I'+str(FDT),'-I'+str(HOST/'include'),str(source)] +
                [str(EDK/'src'/module) for module in modules] + [str(FDT/'fdt.c'),str(FDT/'fdt_ro.c'),
                '-L'+str(HOST/'lib'),'-Wl,-rpath,'+str(HOST/'lib'),'-lcrypto','-pthread','-o',str(binary)],check=True)
            media=root/'media';config=root/'firmware.conf';span=32*1024*1024
            regions=['meta0','meta1','tiboot3_a','tiboot3_b','tispl_a','tispl_b','uboot_a','uboot_b','kernel_a','kernel_b','rootfs_a','rootfs_b']
            with media.open('wb') as f:
                f.truncate(len(regions)*span);f.seek(regions.index('rootfs_b')*span);f.write(b'KEEP_OTHER_SLOT')
            config.write_text(f'device={media}\nhwid-config=test-hwid\n'+
                ''.join(f'{name}-offset={i*span}\n{name}-size={span}\n' for i,name in enumerate(regions)))
            raw=(IMAGES/'rootfs-verity.squashfs').read_bytes()
            subprocess.run([str(binary),str(config),str(IMAGES/'release/rootfs.itb'),str(len(raw)),hashlib.sha256(raw).hexdigest()],check=True)
            with media.open('rb') as f:
                f.seek(regions.index('rootfs_a')*span);self.assertEqual(f.read(len(raw)),raw)
                f.seek(regions.index('rootfs_b')*span);self.assertEqual(f.read(15),b'KEEP_OTHER_SLOT')

if __name__=='__main__':unittest.main()

#!/usr/bin/env python3
"""Reconstruct real release identity after legacy bootloaders discard extensions."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

WORKSPACE=Path(__file__).resolve().parents[4]
EDK=WORKSPACE/'edk'
HOST=WORKSPACE/'output/am625/host'
IMAGES=Path(os.environ.get('FW_TEST_IMAGES',WORKSPACE/'output/am625/images'))

class StorageIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='fw-storage-id-')
        cls.root=Path(cls.tmp.name)
        source=cls.root/'identity.c'
        source.write_text(r'''
#include "edk/firmware.h"
#include "edk_fw_update_priv.h"
#include <stdio.h>
#include <errno.h>
int fw_update_release(const struct fw_layout *l, struct fw_storage *s,
    const char *p, uint32_t c, edk_fw_progress_fn cb, void *d)
{ (void)l; (void)s; (void)p; (void)c; (void)cb; (void)d; return -ENOSYS; }
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    int h=edk_fw_open(argv[1]);
    if (h < 0) { printf("open=%d\n",h); return 1; }
    char tag[32], id[65];
    int rc=edk_fw_get_identity(h,0,tag,id);
    edk_fw_close(h);
    if (rc) { printf("error=%d\n",rc); return 1; }
    printf("%s %s\n",tag,id); return 0;
}
''')
        cls.binary=cls.root/'identity'
        src=EDK/'user/firmware/src'
        files=['edk_fw.c','edk_fw_identity.c','edk_fw_recovery.c','edk_fw_fit.c','edk_fw_layout.c','edk_fw_metadata.c','edk_fw_storage.c','edk_fw_storage_block.c','edk_fw_storage_mtd.c']
        command=['cc','-std=c11','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror','-I'+str(src),'-I'+str(EDK/'user/firmware/include'),'-I'+str(EDK/'user/common'),'-I'+str(EDK/'user/osa/include'),'-I'+str(HOST/'include'),'-I'+str(HOST/'include/libfdt'),str(source)]
        command += [str(src/f) for f in files]
        command += ['-L'+str(HOST/'lib'),'-Wl,-rpath,'+str(HOST/'lib'),'-lcrypto','-lfdt','-pthread','-o',str(cls.binary)]
        cls.runner=[]
        if os.environ.get('FW_ID_TEST_TARGET'):
            target=WORKSPACE/'output/am625/target'
            sysroot=WORKSPACE/'output/am625/staging'
            command=[str(HOST/'bin/aarch64-buildroot-linux-gnu-gcc'),'--sysroot='+str(sysroot),
                '-I'+str(src),'-I'+str(EDK/'user/firmware/include'),str(source),
                '-L'+str(target/'usr/lib'),'-Wl,-rpath-link,'+str(target/'usr/lib'),'-Wl,-rpath-link,'+str(sysroot/'usr/lib'),
                '-ledk_firmware','-o',str(cls.binary)]
            cls.runner=[str(WORKSPACE/'output/initramfs-qemu/tools/usr/bin/qemu-aarch64'),'-L',str(target)]
        subprocess.run(command,check=True)
        cls.identity=json.loads((IMAGES/'firmware-identity.json').read_text())
        cls.kernel=(IMAGES/'release/kernel.itb').read_bytes()
        cls.rootfs=(IMAGES/'rootfs-verity.squashfs').read_bytes()
        cls.original=(IMAGES/'meta1.bin').read_bytes()

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def setUp(self):
        self.disk=self.root/'media'
        with self.disk.open('wb') as f:
            f.truncate(0x14000000)
            f.seek(0x01000000);f.write(self.kernel)
            f.seek(0x04000000);f.write(self.rootfs)
        config=(WORKSPACE/'bsp-base-external/board/ti/am625/rootfs-overlay/etc/edk/firmware.conf').read_text()
        config=config.replace('device=/dev/mmcblk1','device='+str(self.disk)).replace('work-dir=/tmp','work-dir='+str(self.root))
        self.config=self.root/'config';self.config.write_text(config)
        self.metadata(legacy=True)

    def metadata(self,legacy=True,kernel_slot=0):
        record=bytearray(self.original)
        record[32]=kernel_slot
        if legacy:
            record[18:20]=b'\0\0'
            record[128:]=b'\xff'*(len(record)-128)
        struct.pack_into('<I',record,124,zlib.crc32(record[:124]))
        if not legacy:struct.pack_into('<I',record,4092,zlib.crc32(record[:4092]))
        with self.disk.open('r+b') as f:
            for offset in (0x500000,0x510000):f.seek(offset);f.write(record)
        self.saved=bytes(record)

    def read_identity(self,valid=True):
        result=subprocess.run(self.runner+[str(self.binary),str(self.config)],capture_output=True,text=True)
        if valid:
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stdout.strip(),self.identity['tag']+' '+self.identity['firmware_id'])
        else:self.assertNotEqual(result.returncode,0,result.stdout)
        with self.disk.open('rb') as f:
            for offset in (0x500000,0x510000):f.seek(offset);self.assertEqual(f.read(4096),self.saved)
        self.assertEqual(list(self.root.glob('fw-identity-*')),[])
        return result

    def flip(self,offset):
        with self.disk.open('r+b') as f:
            f.seek(offset);byte=f.read(1);f.seek(offset);f.write(bytes([byte[0]^1]))

    def test_legacy_identity_matches_packaging(self):self.read_identity()
    def test_existing_identity_unchanged(self):
        self.metadata(legacy=False);self.read_identity()
    def test_deployment_uses_component_slots(self):
        with self.disk.open('r+b') as f:f.seek(0x2800000);f.write(self.kernel)
        self.metadata(kernel_slot=1)
        self.flip(0x01000000)
        self.read_identity()
    def test_rootfs_damage_is_not_a_valid_new_identity(self):
        self.flip(0x04000000+123);self.read_identity(False)
    def test_kernel_damage_rejected(self):
        self.flip(0x01000000+4096);self.read_identity(False)
    def test_invalid_fit_length_rejected(self):
        with self.disk.open('r+b') as f:f.seek(0x01000004);f.write(struct.pack('>I',0xffffffff))
        self.read_identity(False)
    def test_partition_padding_excluded(self):
        self.flip(0x01000000+self.identity['kernel_bytes']+16)
        self.flip(0x04000000+self.identity['rootfs_bytes']+16)
        self.read_identity()

if __name__=='__main__':unittest.main()

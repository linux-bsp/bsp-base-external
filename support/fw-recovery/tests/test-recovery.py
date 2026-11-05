#!/usr/bin/env python3
"""Exercise recovery C logic with a host test entry and real initramfs artifacts."""
import gzip
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
import unittest

EXTERNAL=Path(__file__).resolve().parents[3]
WORKSPACE=EXTERNAL.parent
SOURCE=WORKSPACE/"edk/device-manager"
HOST=Path(os.environ.get('HOST_DIR',WORKSPACE/'output/am625/host'))
TARGET=Path(os.environ.get('TARGET_DIR',WORKSPACE/'output/am625/target'))
BUILDER=EXTERNAL/'support/scripts/build-initramfs.py'
BOARD=EXTERNAL/'board/ti/am625'


def cpio_entries(path):
    raw=gzip.decompress(path.read_bytes()); offset=0; entries={}
    while True:
        assert raw[offset:offset+6]==b'070701'
        values=[int(raw[offset+6+i*8:offset+14+i*8],16) for i in range(13)]
        size,namesize=values[6],values[11]
        start=offset+110
        name=raw[start:start+namesize-1].decode()
        assert raw[start+namesize-1]==0
        offset=(start+namesize+3)&~3
        data=raw[offset:offset+size]
        assert len(data)==size
        if name=='TRAILER!!!':break
        assert name not in entries and not name.startswith('/') and '..' not in Path(name).parts
        entries[name]=(values,data)
        offset=(offset+size+3)&~3
    return entries


class Recovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native_dir=tempfile.TemporaryDirectory(prefix='fwctl-recovery-native-')
        root=Path(cls.native_dir.name)
        wrapper=root/'entry.c'
        wrapper.write_text(r'''#include <string.h>
extern int fwctl_recovery_main(int, char **);
int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "init"))
        return fwctl_recovery_main(0, 0);
    if (argc == 5 && !strcmp(argv[1], "recovery"))
        return fwctl_recovery_main(3, argv + 2);
    return 2;
}
''')
        cls.native=root/'fwctl-recovery-test'
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',
            '-I'+str(HOST/'include'),'-I'+str(SOURCE.parent/'user/transfer/include'),str(wrapper),str(SOURCE/'fwctl/recovery/fw-init.c'),
            '-L'+str(HOST/'lib'),'-Wl,-rpath,'+str(HOST/'lib'),
            str(SOURCE.parent/'user/transfer/build/libdm-transfer.a'),'-lcurl','-lcrypto','-pthread','-o',str(cls.native)],check=True)

    @classmethod
    def tearDownClass(cls):
        cls.native_dir.cleanup()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='fw-init-test-');self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name);self.raw=self.dir/'raw';self.image=self.dir/'verity';self.dtb=self.dir/'board.dtb'
        self.raw.write_bytes(bytes(range(256))*3201)
        self.dtb.write_bytes(subprocess.check_output([str(HOST/'bin/dtc'),'-I','dts','-O','dtb'],input=b'/dts-v1/; / { chosen {}; };'))
        subprocess.run([str(EXTERNAL/'support/scripts/rootfs-verity.sh'),str(HOST),str(self.raw),str(self.image),str(self.dtb)],check=True,stdout=subprocess.DEVNULL)
        self.dt=self.dir/'dt';self.dt.mkdir()
        for name in ('root-hash','salt','payload-sha256','algorithm'):
            value=subprocess.check_output([str(HOST/'bin/fdtget'),'-t','s',str(self.dtb),'/chosen/fw-verity',name]).strip()
            (self.dt/name).write_bytes(value+b'\0')
        for name in ('version','data-blocks','hash-start-block','hash-blocks','payload-bytes'):
            value=int(subprocess.check_output([str(HOST/'bin/fdtget'),'-t','u',str(self.dtb),'/chosen/fw-verity',name]))
            (self.dt/name).write_bytes(struct.pack('>I',value))

    def check(self,image=None):
        return subprocess.run([str(self.native),'recovery','check-root',str(image or self.image),str(self.dt)],capture_output=True).returncode

    def test_full_payload_and_padding(self):
        self.assertEqual(self.check(),0)
        with self.image.open('ab') as f:f.write(b'unused partition padding')
        self.assertEqual(self.check(),0)
        self.assertEqual((self.dt/'payload-sha256').read_bytes()[:-1].decode(),hashlib.sha256(self.image.read_bytes()[:-len(b'unused partition padding')]).hexdigest())

    def test_data_tree_and_short_reads_rejected(self):
        data=self.image.read_bytes()
        offset=struct.unpack('>I',(self.dt/'hash-start-block').read_bytes())[0]*4096
        for at in (17,offset+17):
            corrupt=bytearray(data);corrupt[at]^=1
            self.image.write_bytes(corrupt);self.assertEqual(self.check(),1)
        self.image.write_bytes(data[:-1]);self.assertEqual(self.check(),1)
        self.assertEqual(self.check(self.dir/'missing'),1)

    def test_bad_identity_and_device_rejected(self):
        result=subprocess.run([str(self.native),'recovery','table','/dev/mmcblk1p14',str(self.dt)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        self.assertIn('1 /dev/mmcblk1p14 /dev/mmcblk1p14 4096 4096',result.stdout)
        self.assertIn('restart_on_corruption restart_on_error',result.stdout)
        bad=subprocess.run([str(self.native),'recovery','table','/dev/x bad',str(self.dt)],capture_output=True)
        self.assertEqual(bad.returncode,2)
        (self.dt/'payload-bytes').write_bytes(struct.pack('>I',129*1024*1024))
        self.assertEqual(self.check(),2)
        (self.dt/'payload-sha256').write_bytes(b'x'*64+b'\0');self.assertEqual(self.check(),2)

    def test_delayed_root_device_discovery(self):
        binary = self.dir/'storage-ready-test'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-I'+str(HOST/'include'), '-I'+str(SOURCE.parent/'user/transfer/include'), str(SOURCE/'fwctl/tests/recovery/storage-ready-test.c'),
            '-L'+str(HOST/'lib'), '-Wl,-rpath,'+str(HOST/'lib'),
            '-Wl,--wrap=access', '-Wl,--wrap=fork', '-Wl,--wrap=execv',
            str(SOURCE.parent/'user/transfer/build/libdm-transfer.a'), '-lcurl', '-lcrypto', '-pthread', '-o', str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertIn('PASS:', result.stdout)

    def test_pid1_guard(self):
        result=subprocess.run([str(self.native),'init'],capture_output=True)
        self.assertEqual(result.returncode,2)
        self.assertIn(b'PID 1',result.stderr)

    def test_real_initramfs_dependency_closure_and_determinism(self):
        one=self.dir/'one.cpio.gz';two=self.dir/'two.cpio.gz'
        for output in (one,two):
            subprocess.run(['python3',str(BUILDER),'--target',str(TARGET),'--board',str(BOARD),
                '--host',str(HOST),'--output',str(output)],check=True,stdout=subprocess.DEVNULL)
        self.assertEqual(one.read_bytes(),two.read_bytes())
        entries=cpio_entries(one)
        for name in ('init','usr/sbin/fwctl','bin/busybox',
                     'etc/device-manager/firmware.conf','etc/fw-recovery.conf','etc/network/interfaces',
                     'sbin/switch_root','sbin/ip','sbin/ifup','var/run','dev/console'):
            self.assertIn(name,entries)
        self.assertNotIn('usr/bin/curl', entries)
        self.assertEqual(entries['init'][1],b'#!/bin/sh\nexec /usr/sbin/fwctl init\n')
        for alias in ('lib64', 'usr/lib64'):
            self.assertEqual(entries[alias][1], b'lib')
            self.assertTrue(stat.S_ISLNK(entries[alias][0][1]))
        self.assertEqual(entries['var/run'][1],b'../run')
        self.assertTrue(stat.S_ISCHR(entries['dev/console'][0][1]))
        self.assertEqual(entries['dev/console'][0][9:11],[5,1])
        self.assertFalse(any('libedk_firmware.so' in name for name in entries))
        self.assertTrue(any('ld-linux-aarch64.so' in name for name in entries))
        for name,(header,_) in entries.items():
            self.assertEqual(header[2:4],[0,0])
            self.assertNotIn('lib/modules/',name)
            self.assertNotIn('system_manager',name)

if __name__=='__main__':unittest.main()

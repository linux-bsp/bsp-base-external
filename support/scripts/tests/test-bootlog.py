#!/usr/bin/env python3
"""Run production U-Boot record code across simulated R5/A53/U-Boot processes."""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

WORKSPACE=Path(__file__).resolve().parents[4]
SOURCE=WORKSPACE/'uboot/u-boot-2026.04/common/bsp_bootlog.c'
STRIDE=16384

class Bootlog(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='bootlog-')
        self.root=Path(self.tmp.name)
        for folder in ('linux','asm'):(self.root/folder).mkdir()
        (self.root/'linux/types.h').write_text('#include <stdint.h>\n#include <stddef.h>\n#include <stdbool.h>\ntypedef uint32_t u32;typedef uint8_t u8;typedef unsigned long ulong;\n#define __aligned(x) __attribute__((aligned(x)))\n#define __section(x) __attribute__((section(x)))\n')
        (self.root/'linux/string.h').write_text('#include <string.h>\n')
        (self.root/'linux/kconfig.h').write_text('#define IS_ENABLED(x) (x)\n')
        (self.root/'asm/cache.h').write_text('')
        (self.root/'cpu_func.h').write_text('static inline void flush_dcache_range(unsigned long a,unsigned long b){(void)a;(void)b;}\n')
        (self.root/'bsp_bootlog.h').write_text('#include <linux/types.h>\n')
        self.wrapper=self.root/'main.c'
        self.wrapper.write_text('''#define _GNU_SOURCE
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include "'''+str(SOURCE)+'''"
int main(int argc,char **argv){assert(argc==3);int fd=open(argv[1],O_RDWR);assert(fd>=0);
assert(mmap((void*)BASE,3*STRIDE,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED_NOREPLACE,fd,0)==(void*)BASE);
bsp_bootlog_init();bsp_bootlog_write("early\\n",6);
#if defined(CONFIG_CPU_V7R)
if(atoi(argv[2]))for(int i=0;i<4000;i++)bsp_bootlog_write("x",1);
bsp_bootlog_ddr_ready();
#endif
bsp_bootlog_write("late\\n",5);msync((void*)BASE,3*STRIDE,MS_SYNC);return 0;}
''')
        for name,defs in [('r5',['-DCONFIG_CPU_V7R=1','-DCONFIG_XPL_BUILD=1']),('a53',['-DCONFIG_XPL_BUILD=1']),('uboot',['-DCONFIG_XPL_BUILD=0'])]:
            subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-I'+str(self.root),*defs,str(self.wrapper),'-o',str(self.root/name)],check=True)
        self.media=self.root/'ram';self.media.write_bytes(b'\0'*(3*STRIDE))
    def tearDown(self):self.tmp.cleanup()
    def run_stage(self,stage,overflow=False):subprocess.run([str(self.root/stage),str(self.media),str(int(overflow))],check=True)
    def records(self):
        data=self.media.read_bytes();result=[]
        for i in range(3):
            record=data[i*STRIDE:(i+1)*STRIDE]
            magic,version,stage,length,dropped,crc,_,_=struct.unpack_from('<8I',record)
            if magic:
                self.assertEqual((magic,version,stage),(0x31474f4c,1,i+1))
                payload=record[32:32+length];self.assertEqual(crc,zlib.crc32(payload))
                result.append((payload,dropped))
            else:result.append(None)
        return result
    def test_stage_handoff_and_next_boot(self):
        for stage in ('r5','a53','uboot'):self.run_stage(stage)
        self.assertEqual(self.records(),[(b'early\nlate\n',0)]*3)
        self.run_stage('r5');self.assertIsNone(self.records()[1]);self.assertIsNone(self.records()[2])
    def test_overflow_accounted_before_ddr(self):
        self.run_stage('r5',True);data,dropped=self.records()[0]
        self.assertEqual(len(data),2048-32+5);self.assertEqual(dropped,6+4000-(2048-32))
        self.assertTrue(data.endswith(b'late\n'))
    def test_stale_or_corrupt_previous_stage_discarded(self):
        for stage in ('r5','a53','uboot'):self.run_stage(stage)
        self.run_stage('a53');self.assertIsNone(self.records()[0]);self.assertIsNone(self.records()[2])
        raw=bytearray(self.media.read_bytes());raw[STRIDE+32]^=1;self.media.write_bytes(raw)
        self.run_stage('uboot');self.assertIsNone(self.records()[1]);self.assertEqual(self.records()[2][0],b'early\nlate\n')

if __name__=='__main__':unittest.main()

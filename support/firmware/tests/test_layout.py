#!/usr/bin/env python3
"""Cross-check real A53/R5 DTBs and independent RAW layout descriptions."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
WORKSPACE = SOURCE.parents[2]
BOARD = WORKSPACE/'bsp-base-external/board/ti/am625'
OUTPUT = WORKSPACE/'output/am625-time-ui'
HOST = Path(os.environ.get('HOST_DIR', OUTPUT/'host'))
sys.path.insert(0, str(SOURCE))
import config
import layout


class Layout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='firmware-layout-')
        self.addCleanup(self.tmp.cleanup)
        self.board = Path(self.tmp.name)/'board';self.board.mkdir()
        self.target = Path(self.tmp.name)/'target'
        self.build = Path(self.tmp.name)/'build'
        self.data = json.loads((BOARD/'firmware.json').read_text())
        for relative in (self.data['validation']['linux_layout'],self.data['factory']['layout']):
            path=self.board/relative;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BOARD/relative,path)
        for relative in (self.data['factory']['environment'],'etc/device-manager/firmware.conf','etc/fw_env.config'):
            path=self.target/relative;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(OUTPUT/'target'/relative,path)
        for relative in self.data['validation']['uboot_dtbs']:
            path=self.build/relative;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(OUTPUT/'build'/relative,path)
            shutil.copyfile((OUTPUT/'build'/relative).parent/'.config',path.parent/'.config')
        self.linux=self.board/self.data['validation']['linux_layout']
        self.factory=self.board/self.data['factory']['layout']
        self.env=self.target/self.data['factory']['environment']
    def run_check(self):
        path=self.board/'firmware.json';path.write_text(json.dumps(self.data))
        return layout.validate(config.load(path),HOST,self.target,self.build)
    def test_actual_board_all_descriptions_match(self):
        report=self.run_check()
        self.assertEqual(report['result'],'consistent')
        self.assertEqual(len(report['regions']),12)
        self.assertEqual(len(report['sources']),9)
        self.assertEqual(report['regions']['rootfs_b'],{'offset':192*1024**2,'size':128*1024**2})
    def test_overlap_in_linux_layout_rejected(self):
        self.linux.write_text(self.linux.read_text().replace('kernel_b-offset=0x02800000','kernel_b-offset=0x01000000'))
        with self.assertRaisesRegex(ValueError,'overlapping'):self.run_check()
    def test_installed_configuration_drift_rejected(self):
        path=self.target/'etc/device-manager/firmware.conf'
        path.write_text(path.read_text().replace('device=/dev/mmcblk1','device=/dev/mmcblk0'))
        with self.assertRaisesRegex(ValueError,'installed Linux'):self.run_check()
    def test_factory_and_environment_drift_rejected(self):
        original=self.factory.read_text()
        self.factory.write_text(original.replace('offset = 192M','offset = 193M'))
        with self.assertRaisesRegex(ValueError,'rootfs_b'):self.run_check()
        self.factory.write_text(original)
        self.env.write_text(self.env.read_text().replace('24M(kernel_a)','25M(kernel_a)'))
        with self.assertRaisesRegex(ValueError,'kernel_a'):self.run_check()
    def test_a53_and_r5_dtb_drift_rejected(self):
        for relative in self.data['validation']['uboot_dtbs']:
            with self.subTest(dtb=relative):
                path=self.build/relative;original=path.read_bytes()
                subprocess.run([str(HOST/'bin/fdtput'),'-t','x',str(path),'/firmware-manager/kernel_b','size','0','1000000'],check=True)
                with self.assertRaisesRegex(ValueError,'kernel_b'):self.run_check()
                path.write_bytes(original)
    def test_json_capacity_gate(self):
        self.data['components']['kernel']['max_size']=25*1024**2
        with self.assertRaisesRegex(ValueError,'kernel: explicit firmware max_size'):self.run_check()
    def test_environment_copies_and_hwid_checked(self):
        envconfig=self.target/'etc/fw_env.config';original=envconfig.read_text()
        envconfig.write_text(original.replace('0x620000','0x630000'))
        with self.assertRaisesRegex(ValueError,'HWID environment copies'):self.run_check()
        envconfig.write_text(original)
        self.env.write_text(self.env.read_text().replace('hwid=1010001000110000','hwid=1010001000210000'))
        with self.assertRaisesRegex(ValueError,'HWID is absent'):self.run_check()
    def test_raw_geometry_required(self):
        self.factory.write_text(self.factory.read_text().replace('"none"','"gpt"'))
        with self.assertRaisesRegex(ValueError,'explicit RAW'):self.run_check()
    def test_compiled_environment_offsets_checked(self):
        path=(self.build/self.data['validation']['uboot_dtbs'][1]).parent/'.config'
        path.write_text(path.read_text().replace('CONFIG_ENV_OFFSET=0x600000','CONFIG_ENV_OFFSET=0x610000'))
        with self.assertRaisesRegex(ValueError,'U-Boot environment offsets'):self.run_check()
    def test_missing_build_dependency_fails_closed(self):
        (self.build/self.data['validation']['uboot_dtbs'][1]).unlink()
        with self.assertRaisesRegex(ValueError,'U-Boot DTB'):self.run_check()
    def test_ambiguous_configuration_fails(self):
        self.linux.write_text(self.linux.read_text()+'\nkernel_a-size=0x1000000\n')
        with self.assertRaisesRegex(ValueError,'conflicting duplicate'):self.run_check()


if __name__=='__main__':unittest.main()

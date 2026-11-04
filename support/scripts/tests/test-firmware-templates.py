#!/usr/bin/env python3
"""Shared hardware configuration must reach every FIT without source edits."""
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
BOARD = SCRIPTS.parents[1] / 'board/ti/am625'
spec = importlib.util.spec_from_file_location('firmware_templates', SCRIPTS / 'firmware-templates.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
A, B = '1010001000110000', '1010001000111000'
TEMPLATES = ['release/bootloader.its', 'release/kernel.its', 'release/rootfs.its']


class FirmwareTemplates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='firmware-templates-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.layout = self.root / 'layout'
        shutil.copytree(BOARD / 'layout', self.layout)
        self.config = self.root / 'firmware.json'
        self.images = self.root / 'images'
        self.images.mkdir()

    def render(self, hwids):
        self.config.write_text(json.dumps({'hwids': hwids}))
        module.render(self.config, self.layout, self.images, 12345, TEMPLATES)

    def read_hwids(self, name):
        text = (self.images / name).read_text()
        # Other release placeholders are normally filled after payload hashing.
        text = re.sub(r'@[A-Z_]+@', '0', text)
        dtb = self.root / 'rendered.dtb'
        subprocess.run(['dtc', '-I', 'dts', '-O', 'dtb', '-o', str(dtb)],
                       input=text, text=True, capture_output=True, check=True)
        return subprocess.check_output(['fdtget', '-t', 's', str(dtb),
                                        '/configurations/conf-1', 'fw,hwids'], text=True).split()

    def test_board_configuration_reaches_all_four_compiled_declarations(self):
        shutil.copyfile(BOARD / 'firmware.json', self.config)
        module.render(self.config, self.layout, self.images, 12345, TEMPLATES)
        for name in [*TEMPLATES, 'release/release.its.in']:
            self.assertEqual(self.read_hwids(name), [A])
        self.assertEqual(json.loads((self.images / 'firmware.json').read_text()), {'hwids': [A]})

    def test_only_editing_common_configuration_updates_every_component(self):
        before = {p.name: p.read_bytes() for p in self.layout.iterdir() if p.is_file()}
        self.render([A])
        self.render([B, A])
        for name in [*TEMPLATES, 'release/release.its.in']:
            self.assertEqual(self.read_hwids(name), [B, A])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.layout.iterdir() if p.is_file()})

    def test_bad_configuration_never_changes_existing_generated_templates(self):
        self.render([A])
        before = {p: p.read_bytes() for p in self.images.rglob('*') if p.is_file()}
        invalid = [None, [], {}, {'hwids': []}, {'hwids': A}, {'hwids': [A, A]},
                   {'hwids': [A], 'hwid': A}, {'hwids': [A] * 257}]
        invalid += [{'hwids': [value]} for value in [None, 123, '2010001000110000',
                    '1010001000110001', '101000100011A000', '1000001000110000',
                    '1010000000110000', '1010001000010000', A + ' ', '<script>']]
        texts = [json.dumps(value) for value in invalid] + ['{', '{"hwids":["'+A+'"],"hwids":["'+B+'"]}']
        for text in texts:
            with self.subTest(config=text):
                self.config.write_text(text)
                with self.assertRaises(ValueError):
                    module.render(self.config, self.layout, self.images, 12345, TEMPLATES)
                self.assertEqual(before, {p: p.read_bytes() for p in self.images.rglob('*') if p.is_file()})

    def test_missing_placeholder_or_template_fails_before_any_write(self):
        self.config.write_text(json.dumps({'hwids': [A]}))
        path = self.layout / 'rootfs.its'
        original = path.read_text()
        path.write_text(original.replace('@FW_HWIDS@', '"'+A+'"'))
        with self.assertRaises(ValueError):
            module.render(self.config, self.layout, self.images, 12345, TEMPLATES)
        self.assertEqual(list(self.images.iterdir()), [])
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            module.render(self.config, self.layout, self.images, 12345, TEMPLATES)
        self.assertEqual(list(self.images.iterdir()), [])

    def test_invalid_output_paths_and_timestamps_are_rejected(self):
        self.config.write_text(json.dumps({'hwids': [A]}))
        for paths in [['../kernel.its'], ['/kernel.its'], ['release/../kernel.its'],
                      ['release/kernel.its', 'release/kernel.its']]:
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                module.render(self.config, self.layout, self.images, 12345, paths)
        for minutes in [-1, 0x100000000]:
            with self.subTest(minutes=minutes), self.assertRaises(ValueError):
                module.render(self.config, self.layout, self.images, minutes, TEMPLATES)
        self.assertEqual(list(self.images.iterdir()), [])


if __name__ == '__main__':
    unittest.main()

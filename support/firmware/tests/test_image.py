#!/usr/bin/env python3
"""Exercise unified JSON validation and real mkimage output, without target execution."""
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

FIRMWARE = Path(__file__).resolve().parents[1]
WORKSPACE = FIRMWARE.parents[2]
sys.path.insert(0, str(FIRMWARE))
import config as configuration
import image as builder

BOARD = WORKSPACE / 'bsp-base-external/board/ti/am625'
HOST = Path(os.environ.get('HOST_DIR', WORKSPACE / 'output/am625-time-ui/host'))
A, B = '1010001000110000', '1010001000111000'


class FirmwareImage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='firmware-json-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.images = self.root / 'images'; self.images.mkdir()
        self.target = self.root / 'target'; self.target.mkdir()
        self.path = self.root / 'firmware.json'
        self.data = json.loads((BOARD / 'firmware.json').read_text())
        self.data['version'] = configuration.load(BOARD / 'firmware.json').data['version']
        self.data.pop('factory')
        self.data.pop('validation', None)
        self.data['components']['rootfs']['verity'] = False
        self.data['components']['kernel']['images'][1].pop('generate')
        self.payload = b'rootfs test content\x00' * 1024
        for name, payload in [('tiboot3.bin', b'r5'), ('tispl.bin_unsigned', b'spl'),
                              ('u-boot.img_unsigned', b'uboot'), ('Image.gz', gzip.compress(b'kernel')),
                              ('initramfs.cpio.gz', gzip.compress(b'initramfs')), ('rootfs.squashfs', self.payload)]:
            (self.images / name).write_bytes(payload)
        subprocess.run([str(HOST / 'bin/dtc'), '-I', 'dts', '-O', 'dtb', '-o',
                        str(self.images / 'k3-am625-alientek.dtb')],
                       input=b'/dts-v1/; / { model="test board"; };', check=True, capture_output=True)

    def load(self, data=None):
        self.path.write_text(json.dumps(self.data if data is None else data))
        return configuration.load(self.path)

    def build(self):
        self.load()
        builder.build(self.path, self.images, HOST, self.target)

    def prop(self, name, key, kind='s', node='/configurations/conf-1'):
        return subprocess.check_output([str(HOST / 'bin/fdtget'), '-t', kind,
                                       str(self.images / 'release' / (name + '.itb')), node, key], text=True).strip()

    def test_fixed_epoch_is_reproducible_and_failed_rebuild_preserves_bundle(self):
        with mock.patch.dict(os.environ, {'SOURCE_DATE_EPOCH':'1793800000'}):
            self.build()
            original = {p.name:p.read_bytes() for p in (self.images/'release').glob('*.itb')}
            identity = (self.images/'firmware-identity.json').read_bytes()
            with mock.patch.object(builder.time, 'time', return_value=2000000000):
                self.build()
            self.assertEqual(original, {p.name:p.read_bytes() for p in (self.images/'release').glob('*.itb')})
            self.assertEqual(identity, (self.images/'firmware-identity.json').read_bytes())
            actual = builder.run
            def fail(args, env):
                if str(args[0]).endswith('/mkimage'):
                    raise ValueError('injected FIT build failure')
                return actual(args, env)
            with mock.patch.object(builder, 'run', side_effect=fail):
                with self.assertRaisesRegex(ValueError, 'injected'):
                    self.build()
            self.assertEqual(original, {p.name:p.read_bytes() for p in (self.images/'release').glob('*.itb')})
            self.assertEqual(identity, (self.images/'firmware-identity.json').read_bytes())
            self.assertTrue((self.images/'release/build-manifest.json').is_file())

    def test_board_configuration_has_one_version_and_explicit_inputs(self):
        config = configuration.load(BOARD / 'firmware.json')
        self.assertEqual(config.version, 1)
        self.assertEqual(config.version_file, WORKSPACE / 'edk/VERSION')
        self.assertEqual(config.data['version'], (WORKSPACE / 'edk/VERSION').read_text().strip())
        self.assertEqual(config.data['components']['kernel']['images'][0]['load'], 0x82000000)
        self.assertEqual(config.data['components']['bootloader']['images'][0]['architecture'], 'arm')
        self.assertEqual(config.data['components']['bootloader']['images'][1]['architecture'], 'arm64')

    def test_version_file_updates_every_fit_and_records_source_checksum(self):
        source = self.root / 'VERSION'
        source.write_text('0.0.1\n')
        self.data['version'] = {'file': 'VERSION'}
        self.build()
        original = json.loads((self.images/'firmware-identity.json').read_text())
        source.write_text('1.2.3\n')
        self.build()
        for name in (*configuration.COMPONENTS, 'release'):
            self.assertEqual(self.prop(name, 'fw,version', 'u'), str(0x10203))
        identity = json.loads((self.images/'firmware-identity.json').read_text())
        self.assertEqual(identity['tag'], 'v1.2.3')
        self.assertNotEqual(identity['firmware_id'], original['firmware_id'])
        manifest = json.loads((self.images/'build-manifest.json').read_text())
        self.assertEqual(manifest['configuration_sha256']['edk_version'],
                         hashlib.sha256(source.read_bytes()).hexdigest())

    def test_version_file_rejects_missing_invalid_and_ambiguous_sources(self):
        for value in [{'file':'missing'}, {'file':'/VERSION'}, {'file':'a//VERSION'},
                      {'file':True}, {}, {'file':'VERSION','value':'0.0.1'}]:
            self.data['version'] = value
            with self.subTest(value=value), self.assertRaises((OSError, ValueError)):
                self.load()
        source = self.root/'VERSION'
        self.data['version'] = {'file':'VERSION'}
        for value in ['v0.0.1\n', '0.0.1\n1.0.0\n', '1.256.0\n']:
            source.write_text(value)
            with self.subTest(contents=value), self.assertRaises(ValueError): self.load()

    def test_stale_edk_build_cannot_replace_previous_release(self):
        (self.root/'VERSION').write_text('0.0.1\n')
        self.data['version'] = {'file':'VERSION'}
        info = self.root/'build/edk-custom/.build/target/build-info.json'
        info.parent.mkdir(parents=True)
        info.write_text(json.dumps({'version':'0.0.1'}))
        with mock.patch.dict(os.environ, {'BUILD_DIR':str(self.root/'build')}):
            self.build()
            original = {p.name:p.read_bytes() for p in (self.images/'release').glob('*.itb')}
            info.write_text(json.dumps({'version':'2.0.0'}))
            with self.assertRaisesRegex(ValueError, 'rebuild edk'): self.build()
            self.assertEqual(original, {p.name:p.read_bytes() for p in (self.images/'release').glob('*.itb')})

    def test_real_fits_and_release_identity_are_generated_from_json(self):
        self.build()
        identity = json.loads((self.images / 'firmware-identity.json').read_text())
        for name in (*configuration.COMPONENTS, 'release'):
            self.assertTrue((self.images / 'release' / (name + '.its')).is_file())
            self.assertEqual(self.prop(name, 'fw,hwids'), A)
            self.assertEqual(self.prop(name, 'fw,version', 'u'), '1')
            self.assertEqual(self.prop(name, 'fw,rollback-index', 'u'), '0')
        self.assertEqual(self.prop('kernel', 'load', 'x', '/images/kernel'), '82000000')
        self.assertEqual(self.prop('kernel', 'compression', node='/images/kernel'), 'gzip')
        self.assertEqual(self.prop('bootloader', 'loadables'), 'tispl uboot')
        self.assertEqual(self.prop('kernel', 'ramdisk'), 'initramfs')
        self.assertEqual(self.prop('kernel', 'type', node='/images/initramfs'), 'ramdisk')
        self.assertEqual(self.prop('kernel', 'algo', node='/images/initramfs/hash-1'), 'sha256')
        self.assertEqual(self.prop('release', 'fw,components'), 'kernel rootfs')
        self.assertEqual(self.prop('release', 'fw,firmware-id'), identity['firmware_id'])
        self.assertEqual(identity['rootfs_sha256'], hashlib.sha256(self.payload).hexdigest())
        for name in ('kernel', 'rootfs'):
            self.assertEqual(self.prop('release', 'fw,' + name + '-sha256'),
                             hashlib.sha256((self.images / 'release' / (name + '.itb')).read_bytes()).hexdigest())
        self.assertEqual((self.images / 'meta0.bin').stat().st_size, 4096)

    def test_common_version_hardware_and_rollback_update_every_fit(self):
        self.data.update(version='1.2.3', hwids=[B, A], rollback_index=7)
        self.build()
        for name in (*configuration.COMPONENTS, 'release'):
            self.assertEqual(self.prop(name, 'fw,hwids'), B + ' ' + A)
            self.assertEqual(self.prop(name, 'fw,version', 'u'), str(0x10203))
            self.assertEqual(self.prop(name, 'fw,rollback-index', 'u'), '7')
        self.assertEqual(self.prop('release', 'fw,tag'), 'v1.2.3')

    def test_armv7_description_can_omit_atf_and_initramfs(self):
        self.data['architecture'] = 'arm'
        boot = self.data['components']['bootloader']
        boot['images'] = [{'name': 'uboot', 'file': 'u-boot.img_unsigned'}]
        boot['firmware'] = 'uboot'; boot['loadables'] = []
        kernel = self.data['components']['kernel']
        kernel.pop('ramdisk'); kernel['images'] = [i for i in kernel['images'] if i['name'] != 'initramfs']
        kernel['images'][0].update(load='0x80800000', entry='0x80800000')
        self.build()
        self.assertEqual(self.prop('bootloader', 'firmware'), 'uboot')
        self.assertEqual(self.prop('kernel', 'arch', node='/images/kernel'), 'arm')
        for name, key in [('bootloader', 'loadables'), ('kernel', 'ramdisk')]:
            result = subprocess.run([str(HOST / 'bin/fdtget'), str(self.images / 'release' / (name + '.itb')),
                                     '/configurations/conf-1', key], capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_64bit_load_addresses_use_two_cells(self):
        self.data['components']['kernel']['images'][0].update(load='0x180000000', entry='0x180000000')
        self.build()
        self.assertEqual(self.prop('kernel', '#address-cells', 'u', '/'), '2')
        self.assertEqual(self.prop('kernel', 'load', 'x', '/images/kernel'), '1 80000000')

    def test_explicit_bootloader_release_has_allow_flag_and_hash(self):
        self.data['release']['components'].insert(0, 'bootloader')
        self.build()
        self.assertEqual(self.prop('release', 'fw,components'), 'bootloader kernel rootfs')
        self.assertEqual(self.prop('release', 'fw,allow-bootloader'), '')
        self.assertEqual(self.prop('release', 'fw,bootloader-file'), 'bootloader.itb')

    def test_invalid_common_fields_are_rejected(self):
        invalid = [('version', v) for v in ['v0.0.1', '01.0.1', '0.0.0', '1.256.0', '65536.0.0', True]]
        invalid += [('hwids', v) for v in [[], [A, A], ['2010001000110000'], [None], [A] * 257]]
        invalid += [('hwids', ['101000100011A000']), ('schema_version', True), ('schema_version', 2),
                    ('rollback_index', -1), ('rollback_index', True)]
        for key, value in invalid:
            data = copy.deepcopy(self.data); data[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): self.load(data)
        for raw in ['{', '{"hwids":[],"hwids":[]}']:
            self.path.write_text(raw)
            with self.assertRaises(ValueError): configuration.load(self.path)

    def test_invalid_references_paths_and_payload_options_are_rejected(self):
        mutations = [lambda d: d.update(unknown=1),
                     lambda d: d['components']['kernel'].update(fdt='missing'),
                     lambda d: d['components']['kernel']['images'][0].pop('load'),
                     lambda d: d['components']['kernel']['images'][0].update(load='0x10000000000000000'),
                     lambda d: d['components']['kernel']['images'][0].update(file='../Image.gz'),
                     lambda d: d['components']['kernel']['images'][0].update(file='release/kernel.itb'),
                     lambda d: d['components']['kernel']['images'][0].update(type=[]),
                     lambda d: d['components']['kernel']['images'][0].update(compression=[]),
                     lambda d: d['components']['kernel']['images'][1].update(name='kernel'),
                     lambda d: d['components']['kernel']['images'][0].update(generate='initramfs'),
                     lambda d: d['components']['bootloader'].update(loadables=['tispl', 'tispl']),
                     lambda d: d['components']['rootfs'].update(verity='true'),
                     lambda d: d['components']['rootfs'].update(verity=True) or d['components']['kernel'].pop('ramdisk'),
                     lambda d: d['release'].update(components=['kernel']),
                     lambda d: d['release'].update(components=['kernel', 'rootfs', 'rootfs']),
                     lambda d: d.update(factory={'layout': '../layout.cfg'})]
        for mutate in mutations:
            data = copy.deepcopy(self.data); mutate(data)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError): self.load(data)

    def test_missing_or_oversized_input_leaves_previous_outputs_untouched(self):
        self.build()
        before = {p: p.read_bytes() for p in (self.images / 'release').iterdir()}
        self.data['components']['kernel']['images'][0]['file'] = 'missing.gz'
        self.load()
        with self.assertRaises(OSError): builder.build(self.path, self.images, HOST, self.target)
        self.assertEqual(before, {p: p.read_bytes() for p in (self.images / 'release').iterdir()})
        self.data['components']['kernel']['images'][0].update(file='Image.gz', max_size=1)
        self.load()
        with self.assertRaises(ValueError): builder.build(self.path, self.images, HOST, self.target)
        self.assertEqual(before, {p: p.read_bytes() for p in (self.images / 'release').iterdir()})

    def test_component_fit_size_limit_is_enforced(self):
        self.data['components']['kernel']['max_size'] = 1
        self.load()
        with self.assertRaisesRegex(ValueError, 'max_size'):
            builder.build(self.path, self.images, HOST, self.target)
        self.assertFalse((self.images / 'release/release.itb').exists())


if __name__ == '__main__': unittest.main()

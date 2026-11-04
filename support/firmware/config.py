"""Validate the board's firmware declaration before producing any artifacts."""
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re

COMPONENTS = ('bootloader', 'kernel', 'rootfs')


def object_keys(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ValueError(f'expected object with keys {sorted(allowed)}, required {sorted(required)}')


def text(value):
    if not isinstance(value, str) or not value or len(value) > 256 or any(ord(c) < 32 for c in value):
        raise ValueError(f'invalid text: {value!r}')
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,62}', value):
        raise ValueError(f'invalid identifier: {value!r}')
    return value


def relative_path(value):
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+', value)
            or PurePosixPath(value).is_absolute() or '..' in PurePosixPath(value).parts
            or PurePosixPath(value).as_posix() != value or value == '.'):
        raise ValueError(f'expected a canonical relative path: {value!r}')
    return value


def unsigned(value, bits=32):
    if isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]+', value):
        value = int(value, 16)
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ValueError(f'expected uint{bits}: {value!r}')
    return value


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate configuration key: {key}')
        result[key] = value
    return result


def version_number(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise ValueError('version must be major.minor.patch without a v prefix')
    major, minor, patch = map(int, value.split('.'))
    if major > 65535 or minor > 255 or patch > 255 or not (major or minor or patch):
        raise ValueError('version is outside the firmware metadata range')
    return major << 16 | minor << 8 | patch


@dataclass
class Firmware:
    data: dict
    board: Path
    version: int


def load(path):
    data = json.loads(path.read_text(), object_pairs_hook=unique_keys)
    object_keys(data, {'schema_version', 'description', 'version', 'rollback_index', 'hwids',
                      'architecture', 'components', 'release', 'factory', 'validation'},
                {'schema_version', 'description', 'version', 'hwids', 'architecture', 'components', 'release'})
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('unsupported firmware schema_version')
    text(data['description']); identifier(data['architecture'])
    version = version_number(data['version'])
    data['rollback_index'] = unsigned(data.get('rollback_index', 0))
    hwids = data['hwids']
    if not isinstance(hwids, list) or not 1 <= len(hwids) <= 256:
        raise ValueError('hwids must contain 1..256 entries')
    for value in hwids:
        if (not isinstance(value, str) or not re.fullmatch(r'1[0-9a-f]{12}000', value)
                or value[1:3] == '00' or value[3:7] == '0000' or value[7:11] == '0000'):
            raise ValueError(f'invalid canonical HWID: {value!r}')
    if len(set(hwids)) != len(hwids):
        raise ValueError('duplicate HWID')
    object_keys(data['components'], COMPONENTS, COMPONENTS)
    generated = set()
    inputs = []
    for name, component in data['components'].items():
        roles = {'kernel', 'fdt', 'ramdisk'} if name == 'kernel' else {'firmware'}
        if name == 'bootloader': roles.add('loadables')
        object_keys(component, {'description', 'os', 'max_size', 'images', 'verity'} | roles, {'images'})
        component['description'] = text(component.get('description', data['description'] + ' ' + name))
        if 'os' in component: identifier(component['os'])
        if 'max_size' in component:
            component['max_size'] = unsigned(component['max_size'], 64)
            if not component['max_size']: raise ValueError('component max_size must be positive')
        if 'verity' in component and (name != 'rootfs' or type(component['verity']) is not bool):
            raise ValueError('verity is a rootfs boolean')
        images = component['images']
        if not isinstance(images, list) or not 1 <= len(images) <= 16:
            raise ValueError('each component needs 1..16 images')
        nodes = {}
        for image in images:
            object_keys(image, {'name', 'file', 'description', 'architecture', 'type', 'compression',
                               'os', 'load', 'entry', 'generate', 'max_size'}, {'name', 'file'})
            key = identifier(image['name']); relative_path(image['file'])
            if key in nodes: raise ValueError(f'duplicate image node: {name}/{key}')
            nodes[key] = image
            image['description'] = text(image.get('description', key))
            image['architecture'] = identifier(image.get('architecture', data['architecture']))
            image['type'] = image.get('type', 'firmware')
            if not isinstance(image['type'], str) or image['type'] not in {'firmware', 'kernel', 'flat_dt', 'ramdisk'}:
                raise ValueError('unsupported FIT image type')
            image['compression'] = image.get('compression', 'none')
            if not isinstance(image['compression'], str) or image['compression'] not in {'none', 'gzip', 'bzip2', 'lzma', 'lzo', 'lz4', 'zstd'}:
                raise ValueError('unsupported FIT compression')
            if 'os' in image or 'os' in component:
                image['os'] = identifier(image.get('os', component.get('os')))
            if image['type'] == 'flat_dt': image.pop('os', None)
            for address in ('load', 'entry'):
                if address in image: image[address] = unsigned(image[address], 64)
            if 'max_size' in image:
                image['max_size'] = unsigned(image['max_size'], 64)
                if not image['max_size']: raise ValueError('image max_size must be positive')
            inputs.append(image['file'])
            if 'generate' in image:
                if image['generate'] != 'initramfs' or name != 'kernel' or image['type'] != 'ramdisk':
                    raise ValueError('initramfs generation requires a kernel ramdisk image')
                if image['file'] in generated: raise ValueError('duplicate generated image path')
                generated.add(image['file'])
        referenced = []
        for role in roles - {'loadables'}:
            if role in component:
                key = identifier(component[role])
                expected = {'fdt': 'flat_dt', 'ramdisk': 'ramdisk', 'kernel': 'kernel', 'firmware': 'firmware'}[role]
                if key not in nodes or nodes[key]['type'] != expected:
                    raise ValueError(f'{name}.{role} references a missing or incorrect image')
                referenced.append(key)
        if ('kernel' if name == 'kernel' else 'firmware') not in component:
            raise ValueError(f'missing boot reference in {name}')
        if name == 'kernel' and not {'load', 'entry'} <= set(nodes[component['kernel']]):
            raise ValueError('kernel image requires load and entry addresses')
        loadables = component.get('loadables', [])
        if not isinstance(loadables, list): raise ValueError('loadables must be a list')
        for key in loadables:
            if identifier(key) not in nodes: raise ValueError('loadable references missing image')
        referenced += loadables
        if len(set(referenced)) != len(referenced) or set(referenced) != set(nodes):
            raise ValueError(f'{name} must reference each image exactly once')
        if name == 'rootfs' and len(images) != 1:
            raise ValueError('rootfs requires one firmware image')
    if data['components']['rootfs'].get('verity'):
        if not all(role in data['components']['kernel'] for role in ('fdt', 'ramdisk')):
            raise ValueError('verity requires kernel fdt and ramdisk references')
        rootfs = data['components']['rootfs']
        if len(rootfs['images']) != 1 or rootfs['images'][0]['compression'] != 'none':
            raise ValueError('verity requires one uncompressed rootfs image')
    for file in generated:
        if inputs.count(file) != 1: raise ValueError('generated input aliases another image')
    reserved = {'firmware.json', 'firmware-identity.json', 'layout-validation.json', 'meta0.bin', 'meta1.bin'}
    reserved |= {f'release/{name}.{suffix}' for name in (*COMPONENTS, 'release') for suffix in ('its', 'itb')}
    if reserved.intersection(inputs): raise ValueError('input collides with generated metadata/FIT output')
    release = data['release']
    object_keys(release, {'description', 'manifest', 'components'}, {'components'})
    release['description'] = text(release.get('description', data['description'] + ' release'))
    release['manifest'] = text(release.get('manifest', data['description']))
    targets = release['components']
    if (not isinstance(targets, list) or not targets or any(t not in COMPONENTS for t in targets)
            or len(set(targets)) != len(targets) or not {'kernel', 'rootfs'} <= set(targets)):
        raise ValueError('release must include kernel and rootfs, and only known unique components')
    if 'factory' in data:
        object_keys(data['factory'], {'layout', 'environment'}, {'layout'})
        for value in data['factory'].values(): relative_path(value)
    if 'validation' in data:
        object_keys(data['validation'], {'linux_layout', 'uboot_dtbs'}, {'linux_layout', 'uboot_dtbs'})
        relative_path(data['validation']['linux_layout'])
        dtbs = data['validation']['uboot_dtbs']
        if (not isinstance(dtbs, list) or not 1 <= len(dtbs) <= 8 or
                any(not isinstance(value, str) for value in dtbs) or len(set(dtbs)) != len(dtbs)):
            raise ValueError('validation requires 1..8 unique U-Boot DTB paths')
        for value in dtbs: relative_path(value)
        if 'factory' not in data or 'environment' not in data['factory']:
            raise ValueError('layout validation requires factory layout and environment')
    return Firmware(data, path.resolve().parent, version)

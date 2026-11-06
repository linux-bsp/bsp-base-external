#!/usr/bin/env python3
"""Build component and release FITs from the single board firmware declaration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import tempfile
import ctypes
from manifest import write as write_manifest

from config import COMPONENTS, load
from fit import component, release
from identity import calculate, write_metadata
from layout import validate as validate_layout

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def run(args, env):
    subprocess.run([str(arg) for arg in args], env=env, check=True)


def size_limit(path, settings):
    size = path.stat().st_size
    if not path.is_file() or not size:
        raise ValueError(f'missing or empty firmware input: {path}')
    if size > settings.get('max_size', size):
        raise ValueError(f'{path.name} exceeds configured max_size')


def build_in_place(config_path, images, host, target):
    config = load(config_path)
    settings = config.data['components']
    files = {name: {image['name']: images / image['file'] for image in item['images']}
             for name, item in settings.items()}
    # Validate source inputs and board dependencies before touching build outputs.
    for name, item in settings.items():
        for image in item['images']:
            if 'generate' not in image: size_limit(files[name][image['name']], image)
            elif not (config.board / 'recovery.conf').is_file():
                raise ValueError('generated initramfs requires board recovery.conf')
    if 'factory' in config.data:
        factory = config.data['factory']
        if not (config.board / factory['layout']).is_file(): raise ValueError('factory layout not found')
        if 'environment' in factory and not (target / factory['environment']).is_file():
            raise ValueError('factory default environment not found')
        if not Path('support/scripts/genimage.sh').is_file():
            raise ValueError('run the factory image build from the Buildroot directory')
    layout_report = validate_layout(config, host, target,
                                    Path(os.environ['BUILD_DIR']) if os.environ.get('BUILD_DIR') else None)
    output = images / 'release'
    output.mkdir(parents=True, exist_ok=True)
    (images / 'firmware.json').write_text(json.dumps(config.data, indent=4) + '\n')
    if layout_report:
        (images / 'layout-validation.json').write_text(json.dumps(layout_report, indent=2) + '\n')
    env = dict(os.environ, PATH=str(host / 'bin') + ':' + str(host / 'sbin') + ':' + os.environ['PATH'],
               BINARIES_DIR=str(images), HOST_DIR=str(host), TARGET_DIR=str(target))
    dtb = files['kernel'].get(settings['kernel'].get('fdt'))
    if settings['rootfs'].get('verity'):
        source = files['rootfs'][settings['rootfs']['firmware']]
        verified = source.with_name(source.stem + '-verity' + source.suffix)
        verified_dtb = dtb.with_name('verity-' + dtb.name)
        inputs = {path for item in files.values() for path in item.values()}
        if verified in inputs or verified_dtb in inputs:
            raise ValueError('verity output collides with an input')
        shutil.copyfile(dtb, verified_dtb)
        run([SCRIPTS / 'rootfs-verity.sh', host, source, verified, verified_dtb], env)
        files['rootfs'][settings['rootfs']['firmware']] = verified
        files['kernel'][settings['kernel']['fdt']] = dtb = verified_dtb
    for image in settings['kernel']['images']:
        if image.get('generate') == 'initramfs':
            destination = files['kernel'][image['name']]
            destination.parent.mkdir(parents=True, exist_ok=True)
            run([host / 'bin/python3', SCRIPTS / 'build-initramfs.py',
                 '--target', target, '--board', config.board, '--host', host, '--output', destination], env)
    epoch = int(os.environ.get('SOURCE_DATE_EPOCH', '0'))
    if epoch < 0: raise ValueError('SOURCE_DATE_EPOCH must be nonnegative')
    env['SOURCE_DATE_EPOCH'] = str(epoch)
    minutes = epoch // 60
    if not 0 <= minutes <= 0xffffffff: raise ValueError('build time exceeds FIT uint32')
    mkimage = host / 'bin/mkimage'
    for name in COMPONENTS:
        for image in settings[name]['images']: size_limit(files[name][image['name']], image)
        its = output / (name + '.its')
        its.write_text(component(config, name, files[name], its, minutes))
        fit = output / (name + '.itb')
        run([mkimage, '-f', its, fit], env)
        size_limit(fit, settings[name])
    identity = calculate(host, images, dtb, settings['kernel'].get('max_size'))
    if identity['version'] != config.version: raise ValueError('built FIT version differs from firmware.json')
    hashes = {name: hashlib.sha256((output / (name + '.itb')).read_bytes()).hexdigest() for name in COMPONENTS}
    its = output / 'release.its'
    its.write_text(release(config, identity, hashes, minutes))
    run([mkimage, '-f', its, output / 'release.itb'], env)
    write_metadata(host, images, identity)
    write_manifest(images, host, config_path, target, epoch)
    if 'factory' in config.data:
        factory = config.data['factory']
        if 'environment' in factory:
            run([host / 'bin/python3', SCRIPTS / 'hwid-env-factory.py',
                 '--input', target / factory['environment'], '--output', images], env)
        env['FW_ROOTFS_IMAGE'] = str(files['rootfs'][settings['rootfs']['firmware']].relative_to(images))
        for name, path in files['bootloader'].items():
            env['FW_BOOTLOADER_' + name.upper().replace('-', '_') + '_IMAGE'] = str(path.relative_to(images))
        run(['support/scripts/genimage.sh', '-c', config.board / factory['layout']], env)
    print(f'Firmware: {identity["tag"]} / {identity["firmware_id"][:8]}')


def exchange(candidate, destination):
    if not destination.exists():
        candidate.replace(destination)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    if rename(-100, os.fsencode(candidate), -100, os.fsencode(destination), 2):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def build(config_path, images, host, target):
    config = load(config_path)
    images.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.firmware-', dir=images.parent) as name:
        staging = Path(name)
        inputs = set()
        for component in config.data['components'].values():
            for image in component['images']:
                if 'generate' not in image:
                    relative = image['file']
                    destination = staging/relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(images/relative, destination)
                    inputs.add(relative)
        build_in_place(config_path, staging, host, target)
        # Sidecars live with their validated ITBs; top-level paths remain views.
        sidecars = ['firmware.json','firmware-identity.json','layout-validation.json',
                    'build-manifest.json','meta0.bin','meta1.bin']
        for entry in sidecars:
            if (staging/entry).exists():
                shutil.move(staging/entry, staging/'release'/entry)
        for path in sorted(staging.rglob('*')):
            relative = path.relative_to(staging)
            if path.is_file() and relative.parts[0] != 'release' and str(relative) not in inputs:
                destination = images/relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                path.replace(destination)
        exchange(staging/'release', images/'release')
        for entry in sidecars:
            if (images/'release'/entry).is_file():
                link = images/('.'+entry+'.link')
                link.unlink(missing_ok=True)
                link.symlink_to('release/'+entry)
                link.replace(images/entry)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', type=Path)
    parser.add_argument('-c', '--config', required=True, type=Path)
    args = parser.parse_args()
    try:
        build(args.config.resolve(), args.images.resolve(), Path(os.environ['HOST_DIR']).resolve(),
              Path(os.environ['TARGET_DIR']).resolve())
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'firmware-image: {error}\n')

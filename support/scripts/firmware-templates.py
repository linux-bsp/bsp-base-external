#!/usr/bin/env python3
"""Render every FIT hardware declaration from one board firmware configuration."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re

HWID_LIMIT = 256


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate firmware configuration key: {key}')
        result[key] = value
    return result


def load_config(path):
    config = json.loads(path.read_text(), object_pairs_hook=unique_keys)
    if not isinstance(config, dict) or set(config) != {'hwids'}:
        raise ValueError('firmware configuration must contain only the hwids list')
    values = config['hwids']
    if not isinstance(values, list) or not 1 <= len(values) <= HWID_LIMIT:
        raise ValueError(f'hwids must contain 1..{HWID_LIMIT} hardware IDs')
    for value in values:
        if (not isinstance(value, str) or not re.fullmatch(r'1[0-9a-f]{12}000', value)
                or value[1:3] == '00' or value[3:7] == '0000' or value[7:11] == '0000'):
            raise ValueError(f'invalid canonical HWID: {value!r}')
    if len(set(values)) != len(values):
        raise ValueError('duplicate HWID in firmware configuration')
    return config


def render(config_path, layout, images, minutes, templates):
    config = load_config(config_path)
    if minutes < 0 or minutes > 0xffffffff:
        raise ValueError('build time must fit the FIT uint32 field')
    declaration = ', '.join(json.dumps(value) for value in config['hwids'])
    outputs = {}
    for name in [*templates, 'release/release.its.in']:
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or path.as_posix() != name
                or not re.fullmatch(r'[A-Za-z0-9_./-]+', name)):
            raise ValueError(f'invalid generated template path: {name}')
        if name in outputs:
            raise ValueError(f'duplicate template output: {name}')
        text = (layout / path.name).read_text()
        if (text.count('@FW_HWIDS@') != 1 or text.count('fw,hwids') != 1
                or not re.search(r'fw,hwids\s*=\s*@FW_HWIDS@\s*;', text)):
            raise ValueError(f'{path.name}: expected one shared fw,hwids placeholder')
        outputs[name] = text.replace('@FW_HWIDS@', declaration).replace('@FW_BUILD_TIME_MINUTES@', str(minutes))
    # Validate every input before changing generated files. The release template
    # is captured now, so later identity generation never rereads mutable config.
    for name, text in outputs.items():
        target = images / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    (images / 'firmware.json').write_text(json.dumps(config, indent=4) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--layout', required=True, type=Path)
    parser.add_argument('--images', required=True, type=Path)
    parser.add_argument('--build-time', required=True, type=int)
    parser.add_argument('templates', nargs='+')
    args = parser.parse_args()
    try:
        render(args.config, args.layout, args.images, args.build_time, args.templates)
    except (OSError, ValueError) as error:
        parser.exit(1, f'firmware-templates: {error}\n')

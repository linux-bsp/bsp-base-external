#!/usr/bin/env python3
"""Package the board's complete default environment for factory SD/eMMC/NOR images."""
import argparse
from pathlib import Path
import re
import struct
import zlib


def build(source, output):
    values = {}
    for line in source.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or not key:
            raise ValueError('invalid factory environment variable')
        # U-Boot's generated defaults can contain a text-environment value
        # followed by an old-style override. Preserve the effective last value.
        values[key] = value
    hwid = values.get('hwid', '')
    if not re.fullmatch(r'1[0-9a-f]{12}000', hwid):
        raise ValueError('factory default environment requires the assigned HWID')
    data = b'\0'.join((key+'='+value).encode() for key, value in values.items()) + b'\0\0'
    if len(data) > 65536 - 5:
        raise ValueError('factory environment exceeds 64 KiB')
    data = data.ljust(65536 - 5, b'\0')
    for copy, flag in enumerate((1, 0)):
        (output/f'uboot-env{copy}.bin').write_bytes(struct.pack('<I', zlib.crc32(data)) + bytes([flag]) + data)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    build(a.input, a.output)

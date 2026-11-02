#!/usr/bin/env python3
"""Bind finalized kernel/rootfs bytes into release metadata; never modify either image."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib


def factory_record(identity, components, sequence):
    """The shared 128-byte boot header plus the 4 KiB identity extension."""
    record = bytearray(4096)
    struct.pack_into('<IHHI8B', record, 0, 0x46574d44, 1, 128, sequence,
                     0, 255, 0, 255, 4, 0, ord('I'), ord('D'))
    high = []
    for i, (version, rollback, minutes) in enumerate(components):
        struct.pack_into('<BBHII', record, 20 + i * 12,
                         0, 1, minutes & 65535, version, rollback)
        high.append(minutes >> 16)
    struct.pack_into('<BBBBI', record, 56, 4, 0, 1, 0, identity['version'])
    struct.pack_into('<I6H', record, 108, 0x314d5442, *high, 0, 0, 0)
    struct.pack_into('<I', record, 124, zlib.crc32(record[:124]))
    struct.pack_into('<II32s32sQQ32s32s', record, 128,
        0x31444946, 1, identity['tag'].encode(), bytes.fromhex(identity['firmware_id']),
        identity['kernel_bytes'], identity['rootfs_bytes'],
        bytes.fromhex(identity['kernel_sha256']), bytes.fromhex(identity['rootfs_sha256']))
    struct.pack_into('<I', record, 4092, zlib.crc32(record[:4092]))
    return record


def render(host, images, template, output):
    binary = host/'bin'
    def prop(path, node, key, kind='s'):
        return subprocess.check_output([str(binary/'fdtget'), '-t', kind, str(path), node, key], text=True).strip()
    def digest(data): return hashlib.sha256(data).hexdigest()
    kernel = (images/'release/kernel.itb').read_bytes()
    size = struct.unpack('>I', kernel[4:8])[0]
    if kernel[:4] != bytes.fromhex('d00dfeed') or not 40 <= size <= len(kernel):
        raise ValueError('invalid kernel FIT size')
    root = images/'release/rootfs.itb'
    conf = '/configurations/'+prop(root, '/configurations', 'default')
    name = prop(root, conf, 'firmware')
    names = subprocess.check_output([str(binary/'fdtget'), '-l', str(root), '/images'], text=True).split()
    with tempfile.TemporaryDirectory(prefix='fw-release-id-') as temporary:
        raw = Path(temporary)/'rootfs'
        subprocess.run([str(binary/'dumpimage'), '-T', 'flat_dt', '-p', str(names.index(name)), '-o', str(raw), str(root)], check=True, stdout=subprocess.DEVNULL)
        payload = raw.read_bytes()
    version = int(prop(images/'release/kernel.itb', '/configurations/conf-1', 'fw,version', 'u'))
    if int(prop(root, conf, 'fw,version', 'u')) != version:
        raise ValueError('kernel/rootfs versions differ')
    kh, rh = digest(kernel[:size]), digest(payload)
    identity = digest(f'BSPFWCONTENT1\nkernel {size} {kh}\nrootfs {len(payload)} {rh}\n'.encode())
    tag = f'v{version >> 16}.{(version >> 8) & 255}.{version & 255}'
    values = {'KERNEL_SHA256': digest(kernel), 'ROOTFS_SHA256': digest(root.read_bytes()),
              'FW_TAG': tag, 'FW_ID': identity, 'FW_KERNEL_PAYLOAD_HASH': kh,
              'FW_ROOTFS_PAYLOAD_HASH': rh, 'FW_KERNEL_BYTES': f'0 {size}',
              'FW_ROOTFS_BYTES': f'0 {len(payload)}'}
    text = template.read_text()
    for key, value in values.items(): text = text.replace('@'+key+'@', value)
    if '@FW_' in text: raise ValueError('unexpanded identity placeholder')
    output.write_text(text)
    identity = dict(tag=tag, firmware_id=identity, version=version, kernel_bytes=size,
                    kernel_sha256=kh, rootfs_bytes=len(payload), rootfs_sha256=rh)
    (images/'firmware-identity.json').write_text(json.dumps(identity, indent=2)+'\n')
    components = []
    for name in ('bootloader', 'kernel', 'rootfs'):
        path = images/'release'/f'{name}.itb'
        node = '/configurations/' + prop(path, '/configurations', 'default')
        components.append(tuple(int(prop(path, node, key, 'u')) for key in
            ('fw,version', 'fw,rollback-index', 'fw,build-time-minutes')))
    for copy in range(2):
        (images/f'meta{copy}.bin').write_bytes(factory_record(identity, components, copy + 1))

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('host','images','template','output'): p.add_argument('--'+name, required=True, type=Path)
    a = p.parse_args(); render(a.host, a.images, a.template, a.output)

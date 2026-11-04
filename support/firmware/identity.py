#!/usr/bin/env python3
"""Align the kernel DTB and bind final payload bytes into release and boot metadata."""
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


def align_kernel_dtb(host, fit, dtb, max_size=None):
    """Inline DTB addresses must be 8-byte aligned for the deployed U-Boot."""
    data = dtb.read_bytes()
    if len(data) < 40 or data[:4] != bytes.fromhex('d00dfeed'):
        raise ValueError('invalid kernel DTB')
    def offset():
        blob = fit.read_bytes()
        at = blob.find(data)
        if at < 0 or blob.find(data, at + 1) >= 0:
            raise ValueError('kernel FIT must contain exactly one matching inline DTB')
        return at
    at = offset()
    if at % 8 == 4:
        # An empty root property occupies 12 bytes in the structure block.
        # Payloads and their hashes stay intact; content ID is generated later.
        subprocess.run([str(host/'bin/fdtput'), '-t', 'x', str(fit), '/',
                        'fw,dtb-alignment-padding'], check=True)
        if offset() % 8 == 4:
            subprocess.run([str(host/'bin/fdtput'), '-t', 'x', str(fit), '/',
                            'fw,dtb-alignment-padding', '0'], check=True)
    if offset() % 8:
        raise ValueError('kernel FIT DTB alignment failed')
    if max_size is not None and fit.stat().st_size > max_size:
        raise ValueError('kernel FIT exceeds configured max_size after alignment')


def calculate(host, images, dtb=None, max_size=None):
    binary = host/'bin'
    if dtb is not None:
        align_kernel_dtb(host, images/'release/kernel.itb', dtb, max_size)
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
    return dict(tag=tag, firmware_id=identity, version=version, kernel_bytes=size,
                kernel_sha256=kh, rootfs_bytes=len(payload), rootfs_sha256=rh)


def write_metadata(host, images, identity):
    binary = host/'bin'
    def prop(path, key):
        return int(subprocess.check_output([str(binary/'fdtget'), '-t', 'u', str(path),
                                           '/configurations/conf-1', key], text=True).strip())
    (images/'firmware-identity.json').write_text(json.dumps(identity, indent=2)+'\n')
    components = []
    for name in ('bootloader', 'kernel', 'rootfs'):
        path = images/'release'/f'{name}.itb'
        components.append(tuple(prop(path, key) for key in
            ('fw,version', 'fw,rollback-index', 'fw,build-time-minutes')))
    for copy in range(2):
        (images/f'meta{copy}.bin').write_bytes(factory_record(identity, components, copy + 1))

#!/usr/bin/env python3
"""Execute the ARM64 loader from an actual initramfs, without library overrides."""
import argparse
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).with_name('test-recovery.py'))
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def check(image, qemu, expect_broken=False):
    with tempfile.TemporaryDirectory(prefix='fw-loader-') as name:
        root = Path(name)
        for entry, (header, data) in recovery.cpio_entries(image).items():
            path = root/entry
            mode = header[1]
            if stat.S_ISDIR(mode):
                path.mkdir(parents=True, exist_ok=True)
            elif stat.S_ISLNK(mode):
                path.symlink_to(data.decode())
            elif stat.S_ISREG(mode):
                path.write_bytes(data)
                path.chmod(stat.S_IMODE(mode))
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('LD_', 'QEMU_'))}
        loader = root/'lib/ld-linux-aarch64.so.1'
        def run(program, *args, listing=False):
            return subprocess.run([str(qemu), '-L', str(root), str(loader),
                '--inhibit-cache'] + (['--list'] if listing else []) +
                [str(root/program), *args], env=env, capture_output=True, text=True, timeout=15)
        result = run('usr/sbin/fw-init')
        if expect_broken:
            assert result.returncode == 127 and 'libcrypto.so.3' in result.stderr, result
            print('PASS: original initramfs reproduces missing libcrypto.so.3 (exit 127)')
            return
        assert result.returncode == 2 and 'PID 1' in result.stderr, result
        for program in ('usr/sbin/fw-init', 'usr/sbin/fwctl', 'usr/bin/curl', 'bin/busybox'):
            result = run(program, listing=True)
            assert result.returncode == 0 and 'not found' not in result.stdout + result.stderr, result
        result = run('usr/bin/curl', '--version')
        assert result.returncode == 0 and 'curl ' in result.stdout, result
        result = run('bin/busybox', 'true')
        assert result.returncode == 0, result
        # A file-existence test cannot catch this regression; the target loader must fail.
        (root/'usr/lib64').unlink()
        result = run('usr/sbin/fw-init')
        assert result.returncode == 127 and 'libcrypto.so.3' in result.stderr, result
        print('PASS: actual ARM64 fw-init/curl/BusyBox execution, all ELF dependencies, missing-alias regression')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', required=True, type=Path)
    parser.add_argument('--image', required=True, type=Path)
    parser.add_argument('--expect-broken', action='store_true')
    args = parser.parse_args()
    check(args.image.resolve(), args.qemu.resolve(), args.expect_broken)

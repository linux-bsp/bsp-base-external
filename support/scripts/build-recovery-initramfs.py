#!/usr/bin/env python3
"""Build a minimal, deterministic newc initramfs without root or target execution."""
import argparse
import gzip
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import tempfile


def build(target, board, host, output):
    target = target.resolve()
    readelf = next(iter(sorted((host/'bin').glob('*-linux-*-readelf'))), None)
    if readelf is None:
        readelf = shutil.which('readelf')
    if not readelf:
        raise RuntimeError('readelf unavailable')
    with tempfile.TemporaryDirectory(prefix='fw-initramfs-') as directory:
        root = Path(directory)
        for name in ('bin','sbin','usr/bin','usr/sbin','lib','dev','proc','sys','run','tmp','newroot','etc/network','var','etc/network/if-pre-up.d','etc/network/if-up.d','etc/network/if-down.d','etc/network/if-post-down.d'):
            (root/name).mkdir(parents=True, exist_ok=True)
        (root/'tmp').chmod(0o1777)
        (root/'var/run').symlink_to('../run')
        (root/'var/lock').symlink_to('../run/lock')
        copied = set()

        def resolve(name):
            # Absolute target symlinks are resolved inside TARGET_DIR, never the host.
            pending = list(PurePosixPath('/'+str(name).lstrip('/')).parts[1:])
            parts = []; links = 0
            while pending:
                part = pending.pop(0)
                if part in ('','.'):
                    continue
                if part == '..':
                    if not parts: raise RuntimeError('target symlink escapes root')
                    parts.pop(); continue
                candidate = target.joinpath(*parts, part)
                if candidate.is_symlink():
                    links += 1
                    if links > 40: raise RuntimeError('target symlink loop')
                    link = os.readlink(candidate)
                    if link.startswith('/'): parts=[]
                    pending=list(PurePosixPath(link).parts)[int(link.startswith('/')):] + pending
                else:
                    parts.append(part)
            return target.joinpath(*parts)

        def copy(name):
            name = str(name).lstrip('/')
            if name in copied: return
            source = resolve(name)
            if not source.is_file(): raise RuntimeError('missing initramfs dependency: '+name)
            destination = root/name
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,destination)
            destination.chmod(stat.S_IMODE(source.stat().st_mode))
            copied.add(name)
            with source.open('rb') as stream: magic=stream.read(4)
            if magic != bytes([0x7f])+b'ELF': return
            text = subprocess.check_output([str(readelf),'-lW','-dW',str(source)],text=True)
            interp=re.search(r'Requesting program interpreter: ([^\]]+)',text)
            if interp: copy(interp.group(1))
            for needed in re.findall(r'\(NEEDED\).*\[([^\]]+)\]',text):
                for prefix in ('lib','usr/lib','lib64','usr/lib64'):
                    if resolve(prefix+'/'+needed).is_file():
                        copy(prefix+'/'+needed); break
                else: raise RuntimeError('missing ELF library: '+needed)

        # The AArch64 loader searches /lib64 and /usr/lib64 without a cache.
        # Preserve Buildroot's directory aliases as well as the ELF files.
        for name in ('lib64', 'usr/lib64'):
            if (target/name).is_symlink():
                canonical = resolve(name).relative_to(target)
                (root/canonical).mkdir(parents=True, exist_ok=True)
                alias = root/name
                alias.parent.mkdir(parents=True, exist_ok=True)
                alias.symlink_to(os.path.relpath(root/canonical, alias.parent))

        for name in ('bin/busybox','usr/sbin/fw-init','usr/sbin/fwctl','usr/bin/curl','etc/edk/firmware.conf','etc/network/interfaces','usr/share/udhcpc/default.script'):
            copy(name)
        config={}
        for line in (root/'etc/edk/firmware.conf').read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key,value=line.split('=',1);config[key.strip()]=value.strip()
        if config.get('require-signature')=='true':
            key=config.get('signature-key','')
            if not key.startswith('/'): raise RuntimeError('absolute signature-key required')
            copy(key);copy('usr/bin/fit_check_sign')
        # Keep only aliases to the one BusyBox executable, never other services.
        busybox=resolve('bin/busybox')
        for folder in ('bin','sbin','usr/bin','usr/sbin'):
            for entry in (target/folder).iterdir():
                if entry.is_symlink() and resolve(folder+'/'+entry.name)==busybox:
                    out=root/folder/entry.name
                    if not out.exists(): out.symlink_to('/bin/busybox')
        # ifup uses ip; the normal rootfs may replace that alias with iproute2.
        for name in ('sbin/ip','sbin/ifconfig','sbin/route','sbin/udhcpc'):
            out=root/name
            if not out.is_symlink() and not out.exists(): out.symlink_to('/bin/busybox')
        for name in ('etc/ssl/certs/ca-certificates.crt','etc/ssl/cert.pem'):
            if resolve(name).is_file(): copy(name)
        shutil.copyfile(board/'recovery.conf',root/'etc/fw-recovery.conf')
        (root/'etc/fw-recovery.conf').chmod(0o644)
        (root/'etc/resolv.conf').write_text('')
        (root/'init').symlink_to('/usr/sbin/fw-init')
        # Required handoff and network applets must be provided by BusyBox config.
        for name in ('bin/sh','sbin/switch_root','sbin/ifup','sbin/ifdown'):
            if not (root/name).is_symlink(): raise RuntimeError('required BusyBox applet missing: '+name)
        output.parent.mkdir(parents=True,exist_ok=True)
        temporary=output.with_suffix(output.suffix+'.tmp')
        inode=0
        with temporary.open('wb') as stream, gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0) as archive:
            def emit(name,mode,data=b'',rmajor=0,rminor=0):
                nonlocal inode
                inode+=1
                encoded=name.encode()+b'\0'
                header=[inode,mode,0,0,2 if stat.S_ISDIR(mode) else 1,0,len(data),0,0,rmajor,rminor,len(encoded),0]
                raw=b'070701'+b''.join(f'{value:08x}'.encode() for value in header)
                archive.write(raw+encoded+b'\0'*((-len(raw)-len(encoded))%4))
                archive.write(data+b'\0'*((-len(data))%4))
            emit('.',stat.S_IFDIR|0o755)
            for item in sorted(root.rglob('*'),key=lambda p:(len(p.relative_to(root).parts),str(p))):
                mode=item.lstat().st_mode; name=str(item.relative_to(root))
                if stat.S_ISDIR(mode): emit(name,stat.S_IFDIR|stat.S_IMODE(mode))
                elif stat.S_ISLNK(mode): emit(name,stat.S_IFLNK|0o777,os.readlink(item).encode())
                elif stat.S_ISREG(mode): emit(name,stat.S_IFREG|stat.S_IMODE(mode),item.read_bytes())
                else: raise RuntimeError('unexpected initramfs file type')
            emit('dev/console',stat.S_IFCHR|0o600,rmajor=5,rminor=1)
            emit('dev/null',stat.S_IFCHR|0o666,rmajor=1,rminor=3)
            emit('TRAILER!!!',0)
        temporary.replace(output)
        print(f'initramfs: {output} ({output.stat().st_size} bytes, {len(copied)} binaries/config/dependencies)')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('target','board','host','output'): parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    build(args.target,args.board,args.host,args.output)

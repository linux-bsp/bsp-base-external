"""Build provenance is sidecar data; it never changes the payload hash algorithm."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

WORKSPACE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WORKSPACE/'edk/scripts'))
from source_info import record


def write(images, host, config_path, target, epoch, version_file=None):
    sources = {name: record(WORKSPACE/name) for name in
               ['.', 'edk', 'bsp-base-external', 'buildroot', 'linux/linux-7.0', 'uboot/u-boot-2026.04', 'libbmc']}
    configs = {'firmware': config_path, 'buildroot': Path(os.environ.get('BR2_CONFIG','/missing'))}
    if version_file is not None:
        configs['edk_version'] = version_file
    build = Path(os.environ.get('BUILD_DIR','/missing'))
    package_info = {}
    for name in ['edk','host-edk']:
        for info in sorted(build.glob(name+'-*/.build/*/build-info.json')):
            package_info[name] = json.loads(info.read_text())
    for name in ['edk','linux','uboot','ti-k3-r5-loader']:
        matches = sorted(build.glob(name+'-*/.config'))
        if matches:
            configs[name] = matches[0]
    edk_config = sorted(build.glob('edk-*/.build/target/.config'))
    if edk_config:
        configs['edk'] = edk_config[0]
    checksums = {name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in configs.items() if p.is_file()}
    tools = {}
    for name in ['cmake','mkimage','dtc']:
        option = '-V' if name == 'mkimage' else '--version'
        result = subprocess.run([str(host/'bin'/name),option],capture_output=True,text=True,check=True)
        tools[name] = (result.stdout+result.stderr).splitlines()[0]
    identity = json.loads((images/'firmware-identity.json').read_text())
    # A VERSION change without rebuilding EDK must never produce a mixed release.
    if version_file is not None:
        for name, info in package_info.items():
            if info['version'] != identity['tag'].removeprefix('v'):
                raise ValueError(f'{name} build version differs from firmware; rebuild {name}')
    data = dict(schema_version=1, source_date_epoch=epoch, identity=identity,
                sources=sources, configuration_sha256=checksums, packages=package_info, tools=tools)
    (images/'build-manifest.json').write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')

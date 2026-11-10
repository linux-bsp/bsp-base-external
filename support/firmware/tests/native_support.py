"""Host-test adapters: exercise the real native build commands, not Python copies."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace

FIRMWARE = Path(__file__).resolve().parents[1]
WORKSPACE = FIRMWARE.parents[2]
HOST = Path(os.environ.get('HOST_DIR', WORKSPACE/'output/am625-debug-systemd/host'))

def run(command, **kwargs):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise ValueError(result.stdout + result.stderr)
    return result.stdout

def load(path):
    path = Path(path).resolve()
    run([HOST/'bin/fw-build-tool', 'check-json', path])
    raw = json.loads(path.read_text())
    value = raw.get('version')
    version_file = None
    if isinstance(value, dict):
        try:
            version_file = (path.parent/value['file']).resolve()
            value = version_file.read_text().strip()
        except (KeyError, TypeError, OSError) as error:
            raise ValueError('invalid version file') from error
    normalized = json.loads(run([HOST/'bin/jq', '--arg', 'version', value if isinstance(value,str) else '',
                                 '-f', FIRMWARE/'config.jq', path]))
    major,minor,patch=map(int,normalized['version'].split('.'))
    return SimpleNamespace(data=normalized,board=path.parent,path=path,
                           version=(major<<16)|(minor<<8)|patch,version_file=version_file)

def build(config, images, host, target):
    env=dict(os.environ,HOST_DIR=str(host),TARGET_DIR=str(target))
    run(['bash',FIRMWARE.parent/'scripts/firmware-image.sh',images,'-c',config],env=env)

def validate(config, host, target, build):
    if build is None:
        raise ValueError('layout validation requires BUILD_DIR')
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        (root/'config.json').write_text(json.dumps(config.data))
        run([host/'bin/cmake','-DCONFIG='+str(root/'config.json'),'-DDECLARATION='+str(config.path),
             '-DHOST_DIR='+str(host),'-DTARGET_DIR='+str(target),'-DBUILD_DIR='+str(build),
             '-DOUTPUT='+str(root/'report.json'),'-P',FIRMWARE/'layout.cmake'])
        return json.loads((root/'report.json').read_text())

configuration=SimpleNamespace(load=load,COMPONENTS=('bootloader','kernel','rootfs'))
builder=SimpleNamespace(build=build)
layout=SimpleNamespace(validate=validate)

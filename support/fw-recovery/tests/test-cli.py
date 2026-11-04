#!/usr/bin/env python3
"""Run factory-force command boundaries in a disposable U-Boot MMC sandbox."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[4]
SANDBOX=Path(os.environ.get('FW_TEST_UBOOT', ROOT/'output/uboot-ota-sandbox/u-boot'))
with tempfile.TemporaryDirectory(prefix='fw-cli-sandbox-') as name:
    directory=Path(name)
    def snapshot(label):
        return ['mmc read 1000000 0 10',f'host save hostfs - 1000000 {directory}/{label}.bin 2000']
    commands=['fwctl help','fwctl capabilities','mmc dev 0','fwctl factory-init a --force','fwctl status']
    commands+=snapshot('before')
    for command in ('fwctl factory-init a','fwctl factory-init c --force','fwctl init a'):
        commands += [f'if {command}; then echo UNSAFE_ACCEPTED; else echo EXPECTED_REFUSAL; fi']
    commands+=snapshot('after')
    commands+=['fwctl factory-init b --force','fwctl status']+snapshot('changed')+['poweroff']
    result=subprocess.run([str(SANDBOX),'-T','-c','; '.join(commands)],cwd=directory,
                          capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'runtime=uboot' in result.stdout and 'factory_init=explicit-force' in result.stdout
    assert 'UNSAFE_ACCEPTED' not in result.stdout
    assert result.stdout.count('EXPECTED_REFUSAL')==3,result.stdout
    assert 'slot=b version=v0.0.0' in result.stdout
    assert (directory/'before.bin').read_bytes()==(directory/'after.bin').read_bytes()
    assert (directory/'before.bin').read_bytes()!=(directory/'changed.bin').read_bytes()
print('PASS: U-Boot help/capabilities, forced factory init, unforced/legacy refusal and unchanged metadata')

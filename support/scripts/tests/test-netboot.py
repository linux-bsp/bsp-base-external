#!/usr/bin/env python3
"""Exercise boot-mode selection, saved environment migration and build identity."""
import os
import json
import gzip
import hashlib
import shutil
import tarfile
from pathlib import Path
import subprocess
import tempfile
import unittest

EXTERNAL = Path(__file__).resolve().parents[3]
WORKSPACE = EXTERNAL.parent
UBOOT = WORKSPACE / 'uboot/u-boot-2026.04'
JQ = os.environ.get('NETBOOT_TEST_JQ') or shutil.which('jq')


class Netboot(unittest.TestCase):
    def test_deployment_preflight_checks_both_manifests_without_modifying_destinations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images, target, host = root / 'images', root / 'target', root / 'host'
            images.mkdir(); (host / 'bin').mkdir(parents=True)
            (host / 'bin/jq').symlink_to(JQ)
            (target / 'etc/bsp').mkdir(parents=True)
            reference = 'BSPNET1 1 ' + 'a' * 64 + '\n'
            (target / 'etc/bsp/netboot.conf').write_text(reference)
            (images / 'Image.gz').write_bytes(gzip.compress(b'kernel'))
            (images / 'custom-board.dtb').write_bytes(b'device tree')
            with tarfile.open(images / 'rootfs.tar', 'w') as archive:
                archive.add(target / 'etc/bsp/netboot.conf', arcname='./etc/bsp/netboot.conf')
            subprocess.run(['bash', str(EXTERNAL / 'support/scripts/export-netboot.sh'), str(images),
                            'Image.gz', 'custom-board.dtb', 'gzip'],
                           env=dict(os.environ, TARGET_DIR=str(target), HOST_DIR=str(host)), check=True)
            # Checking a candidate must work before archiving the existing NFS root.
            nfs, tftp = root / 'nfs', root / 'tftp'
            nfs.mkdir(); (nfs / 'previous-root').write_text('keep me')
            net = ['bash', str(EXTERNAL / 'support/scripts/deploy-netboot.sh'), str(images),
                   '--nfs-root', str(nfs), '--tftp-root', str(tftp), '--check']
            subprocess.run(net, check=True, capture_output=True)
            manifest_path = images / 'netboot/manifest.json'
            good = json.loads(manifest_path.read_text())
            for bad in ('bad-dtb', 'bad-hash', 'missing-file', 'wrong-reference'):
                manifest = json.loads(json.dumps(good))
                if bad == 'bad-dtb':
                    manifest['dtb'] = '../outside.dtb'
                elif bad == 'bad-hash':
                    manifest['sha256']['netboot/Image'] = 'g' * 64
                elif bad == 'missing-file':
                    del manifest['sha256']['netboot/Image']
                else:
                    manifest['reference_build'] = 'BSPNET1 1 ' + 'b' * 64
                manifest_path.write_text(json.dumps(manifest))
                with self.subTest(manifest=bad):
                    self.assertNotEqual(subprocess.run(net, capture_output=True).returncode, 0)
            manifest_path.write_text(json.dumps(good))
            (images / 'netboot/Image').write_bytes(b'corrupted')
            self.assertNotEqual(subprocess.run(net, capture_output=True).returncode, 0)

            laboratory = images / 'sadboard'
            laboratory.mkdir(); (laboratory / 'init').write_bytes(b'laboratory payload')
            lab_manifest = {'format': 'SADBOARD-RAM-BOOT-1',
                            'sha256': {'init': hashlib.sha256(b'laboratory payload').hexdigest()}}
            lab_path = laboratory / 'manifest.json'
            lab_path.write_text(json.dumps(lab_manifest))
            lab = ['bash', str(WORKSPACE / 'sadboard-external/scripts/deploy-boot-labs.sh'),
                   str(images), str(tftp), '--check']
            subprocess.run(lab, check=True, capture_output=True)
            lab_manifest['sha256']['init'] = 'invalid'
            lab_path.write_text(json.dumps(lab_manifest))
            self.assertNotEqual(subprocess.run(lab, capture_output=True).returncode, 0)
            self.assertEqual((nfs / 'previous-root').read_text(), 'keep me')
            self.assertFalse(tftp.exists())

    def test_common_policy_excludes_local_slot_operations_on_network_boot(self):
        overlay = EXTERNAL / 'board/common/rootfs-overlay'
        for service in ('fw-health', 'fw-health-failure', 'firmware-version', 'fwctld'):
            policy = overlay / f'usr/lib/systemd/system/{service}.service.d/bsp-netboot.conf'
            self.assertIn('ConditionKernelCommandLine=!bsp.netboot=1', policy.read_text())
        confirm = (overlay / 'usr/libexec/bsp/confirm-boot').read_text()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Execute the real launcher with only filesystem endpoints relocated.
            for name in ('etc/bsp/netboot-health.d', 'run/device-manager', 'bin', 'usr/libexec/device-manager', 'usr/libexec/bsp'):
                (root / name).mkdir(parents=True, exist_ok=True)
            (root / 'proc').mkdir()
            (root / 'proc/cmdline').write_text('bsp.netboot=1 root=/dev/nfs')
            (root / 'run/device-manager/storage-state').write_text('persistent')
            (root / 'etc/bsp/netboot-health.conf').write_text('systemd-networkd.service\nlogctld.service\n')
            (root / 'etc/bsp/netboot-health.d/product.conf').write_text('product.service\n')
            record = 'BSPNET1 1 ' + 'a' * 64
            programs = {'sleep': 'exit 0', 'systemctl': 'echo "$*" >> "$CALLS"; [ "${REJECT_UNIT:-}" != "$3" ]',
                        'logctl': 'echo "logctl $*" >> "$CALLS"',
                        'fwctl': 'echo "forbidden slot operation" >&2; exit 99'}
            for name, body in programs.items():
                (root / 'bin' / name).write_text('#!/bin/sh\n' + body + '\n')
                (root / 'bin' / name).chmod(0o755)
            context = root / 'usr/libexec/bsp/boot-context'
            context.write_text('#!/bin/sh\necho "' + record + '"\n'); context.chmod(0o755)
            local = root / 'usr/libexec/device-manager/fw-confirm'
            local.write_text('#!/bin/sh\necho delegated\n'); local.chmod(0o755)
            script = root / 'confirm'
            for prefix in ('/usr/libexec/', '/proc/', '/etc/', '/run/', '/data/'):
                confirm = confirm.replace(prefix, str(root) + prefix)
            script.write_text(confirm)
            env = dict(os.environ, CALLS=str(root / 'calls'), PATH=str(root / 'bin') + ':' + os.environ['PATH'])
            subprocess.run(['sh', str(script)], env=env, check=True, capture_output=True)
            self.assertEqual((root / 'run/fwctl-boot-confirmed').read_text(), 'netboot\n')
            self.assertEqual((root / 'data/bsp/netboot-confirmed').read_text(), 'a' * 64 + '\n')
            calls = (root / 'calls').read_text()
            self.assertEqual(calls.count('is-active --quiet product.service'), 6)
            self.assertIn('logctl boot-event health-confirmed', calls)
            for condition in ('failed-unit', 'volatile-storage'):
                with self.subTest(condition=condition):
                    (root / 'run/fwctl-boot-confirmed').unlink(missing_ok=True)
                    (root / 'calls').write_text('')
                    failing = dict(env)
                    if condition == 'failed-unit':
                        failing['REJECT_UNIT'] = 'product.service'
                    else:
                        (root / 'run/device-manager/storage-state').write_text('volatile')
                    result = subprocess.run(['sh', str(script)], env=failing, capture_output=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse((root / 'run/fwctl-boot-confirmed').exists())
                    self.assertNotIn('health-confirmed', (root / 'calls').read_text())
            (root / 'proc/cmdline').write_text('root=/dev/mmcblk1p13 fw.deployment=0')
            self.assertEqual(subprocess.check_output(['sh', str(script)], env=env, text=True), 'delegated\n')

    def test_export_uses_board_selected_dtb_without_sadboard_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target, images, host = root / 'target', root / 'images', root / 'host'
            (target / 'etc/bsp').mkdir(parents=True); images.mkdir(); (host / 'bin').mkdir(parents=True)
            (host / 'bin/jq').symlink_to(JQ)
            (target / 'etc/bsp/netboot.conf').write_text('BSPNET1 1 ' + 'a' * 64 + '\n')
            (images / 'Image.gz').write_bytes(gzip.compress(b'kernel'))
            (images / 'custom-board.dtb').write_bytes(b'device tree')
            (images / 'rootfs.tar').write_bytes(b'rootfs archive')
            subprocess.run(['bash', str(EXTERNAL / 'support/scripts/export-netboot.sh'), str(images),
                            'Image.gz', 'custom-board.dtb', 'gzip'],
                           env=dict(os.environ, TARGET_DIR=str(target), HOST_DIR=str(host)), check=True)
            manifest = json.loads((images / 'netboot/manifest.json').read_text())
            self.assertEqual(manifest['format'], 'BSP-NETBOOT-1')
            self.assertEqual(manifest['dtb'], 'custom-board.dtb')
            self.assertEqual((images / 'netboot/Image').read_bytes(), b'kernel')
            for path, digest in manifest['sha256'].items():
                self.assertEqual(hashlib.sha256((images / path).read_bytes()).hexdigest(), digest)

    def test_four_compiled_environment_combinations(self):
        for tftp, nfs, profile in ((0, 0, 'mmc'), (1, 0, 'tftp-mmc'), (0, 1, 'mmc-nfs'), (1, 1, 'tftp-nfs')):
            cmd = ['cc', '-E', '-P', '-x', 'c', '-I', str(UBOOT / 'include')]
            for enabled, symbol in ((tftp, 'TFTP_KERNEL'), (nfs, 'NFS_ROOT')):
                if enabled:
                    cmd.append('-DCONFIG_AM62X_BOOT_' + symbol)
            text = subprocess.check_output(cmd + [str(UBOOT / 'board/ti/am62x/am62x_raw_ab.env')], text=True)
            values = dict(line.split('=', 1) for line in text.splitlines() if '=' in line and not line[0].isspace())
            self.assertEqual(values['fw_boot_profile'], profile)
            self.assertEqual(values['tftp_kernel'], str(tftp))
            self.assertEqual(values['nfs_root'], str(nfs))

    def test_context_distinguishes_network_from_saved_sd_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'cmdline').write_text('root=/dev/nfs bsp.netboot=1 rw\n')
            record = 'BSPNET1 1 ' + '1' * 64 + '\n'
            (root / 'build.conf').write_text(record)
            (root / 'fwctl').write_text('#!/bin/sh\necho FWOTA2-local-slot\n')
            (root / 'fwctl').chmod(0o755)
            env = dict(os.environ, BSP_CMDLINE=str(root / 'cmdline'),
                       BSP_NETBOOT_INFO=str(root / 'build.conf'), PATH=directory + ':' + os.environ['PATH'])
            cmd = ['sh', str(EXTERNAL / 'board/common/rootfs-overlay/usr/libexec/bsp/boot-context')]
            self.assertEqual(subprocess.check_output(cmd, env=env, text=True), record)
            (root / 'build.conf').write_text('BSPNET1 1 invalid\n')
            self.assertNotEqual(subprocess.run(cmd, env=env, capture_output=True).returncode, 0)
            (root / 'cmdline').write_text('root=/dev/mmcblk1p13 fw.deployment=0\n')
            self.assertEqual(subprocess.check_output(cmd, env=env, text=True), 'FWOTA2-local-slot\n')

    def test_build_identity_is_repeatable_and_tracks_kernel_and_root_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target, images = root / 'target', root / 'images'
            target.mkdir(); images.mkdir()
            (target / 'init').write_text('example root')
            (target / 'absolute-link').symlink_to('/usr/bin/example')
            (images / 'Image.gz').write_bytes(b'kernel')
            (images / 'k3-am625-alientek.dtb').write_bytes(b'dtb')
            env = dict(os.environ, TARGET_DIR=str(target), BINARIES_DIR=str(images))
            def build():
                subprocess.run(['bash', str(EXTERNAL / 'support/scripts/netboot-build.sh'), str(target), str(images / 'Image.gz'), str(images / 'k3-am625-alientek.dtb'), str(WORKSPACE / 'edk/VERSION')], env=env, check=True, capture_output=True)
                return (target / 'etc/bsp/netboot.conf').read_text()
            original = build()
            self.assertEqual(original, build())
            (target / 'init').write_text('changed root')
            self.assertNotEqual(original, build())
            before_kernel = build()
            (images / 'Image.gz').write_bytes(b'new kernel')
            self.assertNotEqual(before_kernel, build())

    def test_saved_profile_migration_preserves_provisioning_and_manual_switches(self):
        text = (UBOOT / 'board/ti/am62x/evm.c').read_text()
        function = text[text.index('static void migrate_fw_environment(void)'):]
        function = function[:function.index('\n#endif')]
        # Compile and execute the actual board migration with a memory env backend.
        harness = r'''
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include <assert.h>
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
struct entry { char key[64], value[1024]; } entries[100];
int count, saves;
const char *profile="tftp-nfs", *tftp="1", *nfs="1";
const char *env_get(const char *key) {
    for (int i=0;i<count;i++) if (!strcmp(entries[i].key,key)) return entries[i].value;
    return NULL;
}
int env_set(const char *key,const char *value) {
    int i; for (i=0;i<count;i++) if (!strcmp(entries[i].key,key)) break;
    if (i==count) count++;
    snprintf(entries[i].key,64,"%s",key); snprintf(entries[i].value,1024,"%s",value);
    return 0;
}
int env_get_default_into(const char *key,char *value,int size) {
    const char *def=!strcmp(key,"fw_env_version")?"10":!strcmp(key,"fw_boot_profile")?profile:
        !strcmp(key,"tftp_kernel")?tftp:!strcmp(key,"nfs_root")?nfs:"compiled script";
    snprintf(value,size,"%s",def); return strlen(def);
}
int env_set_default_vars(int length,char *const *names,int flags) {
    for(int i=0;i<length;i++) { char value[1024]; env_get_default_into(names[i],value,1024); env_set(names[i],value); }
    return 1;
}
int env_save(void) { saves++; return 0; }
'''
        main = r'''
int main(void) {
    env_set("fw_env_version","8"); env_set("tftp_kernel","0"); env_set("nfs_root","0");
    env_set("hwid","1010001000110000"); env_set("ethaddr","1c:63:49:22:c4:f7");
    env_set("serverip","192.0.2.1"); env_set("nfsroot","/custom/root");
    migrate_fw_environment(); assert(saves==1);
    assert(!strcmp(env_get("tftp_kernel"),"1") && !strcmp(env_get("nfs_root"),"1"));
    assert(!strcmp(env_get("hwid"),"1010001000110000"));
    assert(!strcmp(env_get("ethaddr"),"1c:63:49:22:c4:f7"));
    assert(!strcmp(env_get("serverip"),"192.0.2.1"));
    assert(!strcmp(env_get("nfsroot"),"/custom/root"));
    env_set("tftp_kernel","0"); migrate_fw_environment(); assert(saves==1);
    assert(!strcmp(env_get("tftp_kernel"),"0"));
    profile="mmc-nfs"; tftp="0"; migrate_fw_environment(); assert(saves==2);
    assert(!strcmp(env_get("tftp_kernel"),"0") && !strcmp(env_get("nfs_root"),"1"));
    profile="tftp-mmc"; tftp="1"; nfs="0"; migrate_fw_environment(); assert(saves==3);
    assert(!strcmp(env_get("tftp_kernel"),"1") && !strcmp(env_get("nfs_root"),"0"));
    profile="mmc"; tftp="0"; migrate_fw_environment(); assert(saves==4);
    assert(!strcmp(env_get("tftp_kernel"),"0") && !strcmp(env_get("nfs_root"),"0"));
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'migration.c'
            source.write_text(harness + function + main)
            executable = Path(directory) / 'migration'
            subprocess.run(['cc', '-o', str(executable), str(source)], check=True)
            subprocess.run([str(executable)], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()

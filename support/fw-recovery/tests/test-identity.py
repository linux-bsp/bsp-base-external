#!/usr/bin/env python3
"""Validate real release identities, factory records and U-Boot/Linux interoperability."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

WORKSPACE = Path(__file__).resolve().parents[4]
HOST = Path(os.environ.get('HOST_DIR', WORKSPACE/'output/am625/host'))
IMAGES = Path(os.environ.get('FW_TEST_IMAGES', WORKSPACE/'output/am625/images'))
MODULE = WORKSPACE/'edk/user/apps/fwctl'
FDT = WORKSPACE/'uboot/u-boot-2026.04/scripts/dtc/libfdt'
SANDBOX = WORKSPACE/'output/uboot-ota-sandbox/u-boot'
ENV = dict(os.environ, PATH=str(HOST/'bin')+':'+os.environ['PATH'])


def run(args, **kw):
    return subprocess.run(list(map(str, args)), env=ENV, check=True,
                          capture_output=True, text=True, **kw)


with tempfile.TemporaryDirectory(prefix='fw-identity-') as directory:
    root = Path(directory)
    source = root/'identity.c'
    source.write_text(r'''
#include "dm_fw_fit_priv.h"
#include "dm_fw_storage_priv.h"
#include "dm/hwid.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned char media[2][FW_METADATA_SIZE];
int dm_hwid_read(const char *config, struct dm_hwid_status *status)
{ (void)config; strcpy(status->text,"1010001000110000"); return 0; }
int fw_storage_read_metadata(struct fw_storage *s, unsigned c, void *p, size_t n)
{ (void)s; memcpy(p, media[c], n); return 0; }
int fw_storage_write_metadata(struct fw_storage *s, unsigned c, const void *p, size_t n)
{ (void)s; memcpy(media[c], p, n); return 0; }
int main(int argc, char **argv)
{
    assert(argc == 6);
    struct fw_layout layout = {0}; struct fw_fit fit; struct fw_release release;
    strcpy(layout.hwid_config, "test-hwid");
    if (fw_fit_open(&fit, argv[1], &layout)) return 1;
    int rc = fw_fit_verify_release(&layout, &fit, &release);
    fw_fit_close(&fit);
    if (rc || !release.identity.valid) return 1;
    for (unsigned i = 0; i < 2; i++) {
        struct fw_package package;
        if (fw_fit_open(&fit, argv[2 + i], &layout)) return 1;
        rc = fw_fit_verify_package(&layout, &fit, &package);
        if (!rc) rc = fw_fit_check_identity(&fit, FW_COMPONENT_KERNEL + i, &release.identity);
        fw_fit_close(&fit);
        if (rc) return 1;
        FILE *file = fopen(argv[4 + i], "rb");
        assert(file && fread(media[i], 1, FW_METADATA_SIZE, file) == FW_METADATA_SIZE);
        fclose(file);
    }
    struct fw_metadata metadata; struct fw_storage storage = {0};
    assert(!fw_metadata_load(&storage, &metadata));
    struct fw_identity *id = &metadata.deployment[0].identity;
    assert(id->valid && !strcmp(id->tag, release.identity.tag));
    assert(!memcmp(id->id, release.identity.id, 32));
    assert(!memcmp(id->hash, release.identity.hash, 64));
    assert(!memcmp(id->size, release.identity.size, sizeof(id->size)));
    assert(!fw_metadata_save(&storage, &metadata));
    for (unsigned i = 0; i < 2; i++) {
        FILE *file = fopen(argv[4 + i], "wb");
        assert(file && fwrite(media[i], 1, FW_METADATA_SIZE, file) == FW_METADATA_SIZE);
        assert(!fclose(file));
    }
    return 0;
}
''')
    binary = root/'identity'
    run(['cc', '-std=c11', '-D_POSIX_C_SOURCE=200809L', '-Wall', '-Wextra', '-Werror',
         '-I'+str(MODULE/'core'), '-I'+str(MODULE/'storage'), '-I'+str(MODULE/'include'), '-I'+str(WORKSPACE/'edk/user/lib/hwid/include'), '-I'+str(FDT), '-I'+str(HOST/'include'),
         source, MODULE/'core/dm_fw_fit.c', MODULE/'core/dm_fw_metadata.c',
         FDT/'fdt.c', FDT/'fdt_ro.c', '-L'+str(HOST/'lib'), '-Wl,-rpath,'+str(HOST/'lib'),
         '-lcrypto', '-o', binary])
    for i in range(2):
        shutil.copyfile(IMAGES/f'meta{i}.bin', root/f'meta{i}.bin')
    args = [binary, IMAGES/'release/release.itb', IMAGES/'release/kernel.itb',
            IMAGES/'release/rootfs.itb', root/'meta0.bin', root/'meta1.bin']
    run(args)
    # Reject valid FIT containers whose claimed tag, ID, size or digest is inconsistent.
    for prop, kind, values in [
        ('fw,tag', 's', ['v9.9.9']),
        ('fw,firmware-id', 's', ['0'*64]),
        ('fw,kernel-payload-sha256', 's', ['0'*64]),
        ('fw,rootfs-payload-bytes', 'i', ['0', '1']),
    ]:
        broken = root/'broken.itb'
        shutil.copyfile(args[1], broken)
        run([HOST/'bin/fdtput', '-t', kind, broken, '/configurations/conf-1', prop, *values])
        result = subprocess.run([str(binary), str(broken), *map(str, args[2:])], capture_output=True)
        assert result.returncode != 0, prop
    # A changed FIT header remains a valid package but must not retain the old content ID.
    broken_kernel = root/'changed-kernel.itb'
    shutil.copyfile(args[2], broken_kernel)
    run([HOST/'bin/fdtput', '-t', 's', broken_kernel, '/', 'description', 'changed content'])
    result = subprocess.run([str(binary), str(args[1]), str(broken_kernel), *map(str, args[3:])], capture_output=True)
    assert result.returncode != 0
    identity = json.loads((IMAGES/'firmware-identity.json').read_text())
    commands = ['mmc dev 0']
    for i in range(2):
        commands += [f'host load hostfs - 1000000 {root}/meta{i}.bin', f'mmc write 1000000 {i*8:x} 8']
    commands += ['fwctl status', 'fwctl mark-good 0', 'fwctl status']
    for i in range(2):
        commands += [f'mmc read 1000000 {i*8:x} 8', f'host save hostfs - 1000000 {root}/meta{i}.bin 1000']
    commands += ['poweroff']
    result = run([SANDBOX, '-T', '-c', '; '.join(commands)], cwd=root, timeout=60)
    assert f"tag={identity['tag']} id={identity['firmware_id'][:8]}" in result.stdout, result.stdout
    assert identity['firmware_id'] not in result.stdout
    run(args)  # Decode U-Boot's rewritten record with production Linux code.
    print('PASS: release tag/ID binding, payload mismatch rejection, factory metadata, Linux -> U-Boot -> Linux')

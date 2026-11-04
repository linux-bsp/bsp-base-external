"""Read-only RAW MMC A/B geometry gate. No configuration is generated here."""
import hashlib
import re
import subprocess

REGIONS = ['meta0', 'meta1'] + [name + '_' + slot
           for name in ('tiboot3', 'tispl', 'uboot', 'kernel', 'rootfs') for slot in 'ab']


def values(path):
    result = {}
    for line in path.read_text().splitlines():
        if not line or line.lstrip().startswith('#') or '=' not in line: continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if key in result and result[key] != value: raise ValueError(f'{path.name}: conflicting duplicate {key}')
        result[key] = value
    return result


def quantity(text):
    match = re.fullmatch(r'(0[xX][0-9a-fA-F]+|[0-9]+)([KMG]?)', text.strip())
    if not match: raise ValueError(f'unsupported layout quantity: {text}')
    value = int(match[1], 16 if match[1].lower().startswith('0x') else 10)
    value *= {'': 1, 'K': 1024, 'M': 1024**2, 'G': 1024**3}[match[2]]
    if value >= 2**64: raise ValueError('layout quantity overflow')
    return value


def regions(config):
    result = {name: (quantity(config[name+'-offset']), quantity(config[name+'-size'])) for name in REGIONS}
    end = 0
    for name, (start, size) in sorted(result.items(), key=lambda item: item[1][0]):
        if not size or start % 512 or size % 512 or start < end or start + size >= 2**64:
            raise ValueError(f'{name}: overlapping, empty, unaligned or overflowing region')
        end = start + size
    for component in ('tiboot3', 'tispl', 'uboot', 'kernel', 'rootfs'):
        if result[component+'_a'][1] != result[component+'_b'][1]:
            raise ValueError(f'{component}: A/B capacities differ')
    return result


def factory_regions(path):
    # ${IMAGE_VARIABLE} is an image filename, not a nested partition block.
    text = re.sub(r'\$\{[^}]+\}', 'IMAGE', path.read_text())
    text = re.sub(r'#[^\n]*', '', text)
    tables = re.findall(r'partition-table-type\s*=\s*"([^"]+)"', text)
    if tables != ['none']: raise ValueError('layout validation requires an explicit RAW factory image')
    result = {}
    for name, body in re.findall(r'\bpartition\s+(\w+)\s*\{(.*?)^\s*\}', text, re.M | re.S):
        if name in result: raise ValueError(f'factory: duplicate partition {name}')
        fields = {}
        for key in ('offset', 'size'):
            found = re.findall(r'^\s*'+key+r'\s*=\s*(\S+)\s*$', body, re.M)
            if len(found) != 1: raise ValueError(f'factory {name}: one explicit {key} required')
            fields[key] = quantity(found[0])
        result[name] = (fields['offset'], fields['size'])
    return result


def boot_regions(environment):
    parts = ','.join(environment[key] for key in ('fw_parts_a', 'fw_parts_b', 'fw_parts_os'))
    result, cursor = {}, 0
    for index, part in enumerate(parts.split(',')):
        match = re.fullmatch(r'(-|(?:0x[0-9a-fA-F]+|\d+)[KMG]?)(?:@((?:0x[0-9a-fA-F]+|\d+)[KMG]?))?\(([a-zA-Z0-9_]+)\)', part)
        if not match or match[3] in result: raise ValueError('invalid/duplicate blkdevparts entry')
        size, offset, name = match.groups()
        start = quantity(offset) if offset else cursor
        if start < cursor: raise ValueError(f'{name}: overlapping blkdevparts entry')
        if size == '-':
            if index != len(parts.split(','))-1: raise ValueError('remaining partition must be last')
            result[name] = (start, None)
        else:
            length = quantity(size)
            if not length or start % 512 or length % 512: raise ValueError(f'{name}: invalid block geometry')
            result[name] = (start, length)
            cursor = start + length
    return result


def validate(config, host, target, build):
    settings = config.data.get('validation')
    if not settings: return None
    if build is None: raise ValueError('layout validation requires BUILD_DIR')
    build = build.resolve()
    linux_path = config.board/settings['linux_layout']
    dtbs = [build/path for path in settings['uboot_dtbs']]
    factory_path = config.board/config.data['factory']['layout']
    env_path = target/config.data['factory']['environment']
    linux = values(linux_path)
    expected = regions(linux)
    factory = factory_regions(factory_path)
    env = values(env_path)
    boot = boot_regions(env)
    installed_path = target/'etc/device-manager/firmware.conf'
    installed = values(installed_path)
    if regions(installed) != expected or any(installed[key] != linux[key] for key in ('device', 'storage-type', 'hwid-config')):
        raise ValueError('installed Linux firmware layout differs from board configuration')
    def prop(node, name, kind='u'):
        try:
            return subprocess.check_output([str(host/'bin/fdtget'), '-t', kind, str(dtb), node, name],
                                           text=True, stderr=subprocess.PIPE).strip()
        except subprocess.CalledProcessError as error:
            raise ValueError(f'U-Boot DTB {node}/{name}: {error.stderr.strip()}') from error
    for dtb in dtbs:
        if prop('/firmware-manager', 'storage', 's') != 'mmc' or linux['storage-type'] != 'block':
            raise ValueError('RAW layout validation currently supports MMC block devices')
        device = int(prop('/firmware-manager', 'device'))
        if env.get('fw_mmcdev') != str(device) or linux.get('device') != f'/dev/mmcblk{device}':
            raise ValueError('Linux/U-Boot MMC device mismatch')
        for name, region in expected.items():
            actual = []
            for key in ('offset', 'size'):
                cells = prop('/firmware-manager/'+name, key).split()
                if len(cells) != 2: raise ValueError(f'U-Boot {name}/{key}: expected two cells')
                high, low = map(int, cells)
                if not 0 <= high < 2**32 or not 0 <= low < 2**32: raise ValueError('invalid DTB cell')
                actual.append((high << 32) | low)
            for source, candidate in [(str(dtb), tuple(actual)), ('blkdevparts', boot.get(name)),
                                       ('factory', factory.get(name))]:
                if candidate != region: raise ValueError(f'{name}: {source} {candidate} differs from Linux {region}')
    if 'data' not in factory or boot.get('data', (None,))[0] != factory['data'][0]:
        raise ValueError('data: factory and blkdevparts start differ')
    area = boot.get('env_area')
    env_regions = [factory.get('uboot_env0'), factory.get('uboot_env1')]
    if not area or not area[1] or any(region is None or region[0] < area[0] or
        region[0]+region[1] > area[0]+area[1] for region in env_regions):
        raise ValueError('factory environments exceed the reserved env_area')
    boot_configs = []
    for dtb in dtbs:
        found = next((parent/'.config' for parent in dtb.parents
                      if parent.is_relative_to(build) and (parent/'.config').is_file()), None)
        if found is None: raise ValueError(f'{dtb}: U-Boot build .config unavailable')
        kconfig = values(found)
        if (kconfig.get('CONFIG_ENV_IS_IN_MMC') != 'y' or
            kconfig.get('CONFIG_ENV_MMC_EMMC_HW_PARTITION') != '0' or
            kconfig.get('CONFIG_ENV_MMC_DEVICE_INDEX') != env.get('fw_mmcdev') or
            any(kconfig.get(key) == 'y' for key in ('CONFIG_ENV_MMC_USE_DT', 'CONFIG_ENV_MMC_USE_SW_PARTITION',
                'CONFIG_ENV_OFFSET_RELATIVE_END', 'CONFIG_ENV_OFFSET_REDUND_RELATIVE_END'))):
            raise ValueError(f'{found}: unsupported/different MMC environment backing')
        size = quantity(kconfig['CONFIG_ENV_SIZE'])
        locations = [(quantity(kconfig[key]), size) for key in ('CONFIG_ENV_OFFSET', 'CONFIG_ENV_OFFSET_REDUND')]
        if sorted(locations) != sorted(env_regions):
            raise ValueError(f'{found}: U-Boot environment offsets differ from factory')
        boot_configs.append(found)
    env_config_path = target/linux['hwid-config'].lstrip('/')
    env_locations = []
    for line in env_config_path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'): continue
        fields = line.split()
        if len(fields) != 3 or fields[0] != linux['device']:
            raise ValueError('MMC environment configuration has unsupported device/fields')
        env_locations.append((quantity(fields[1]), quantity(fields[2])))
    if sorted(env_locations) != sorted(env_regions):
        raise ValueError('HWID environment copies differ from factory layout')
    if env.get('hwid') not in config.data['hwids']:
        raise ValueError('factory HWID is absent from the firmware allowlist')
    all_factory = sorted(factory.items(), key=lambda item: item[1][0])
    end = 0
    for name, (start, size) in all_factory:
        if not size or start < end: raise ValueError(f'factory {name}: overlapping or empty partition')
        end = start + size
    components = config.data['components']
    limits = {'kernel': components['kernel'].get('max_size'),
              'rootfs': components['rootfs']['images'][0].get('max_size')}
    limits.update({image['name']: image.get('max_size') for image in components['bootloader']['images']})
    for name in ('tiboot3', 'tispl', 'uboot', 'kernel', 'rootfs'):
        if limits.get(name) is None or limits[name] > expected[name+'_a'][1]:
            raise ValueError(f'{name}: explicit firmware max_size must fit both slots')
    return {'schema_version': 1, 'result': 'consistent',
            'regions': {name: {'offset': pair[0], 'size': pair[1]} for name, pair in expected.items()},
            'sources': {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in (linux_path, *dtbs, *boot_configs, factory_path, env_path, installed_path, env_config_path)}}

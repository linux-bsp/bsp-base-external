"""Generate ordinary DTS/FIT sources from validated component descriptions."""
import json
import os


def quote(value):
    return json.dumps(value, ensure_ascii=False)


def strings(values):
    return ', '.join(quote(value) for value in values)


def cells(value, count=1):
    return '<' + ' '.join(f'0x{(value >> shift) & 0xffffffff:x}' for shift in reversed(range(0, count * 32, 32))) + '>'


def metadata(config, component, minutes):
    return [f'fw,type = {quote(component)};',
            f'fw,hwids = {strings(config.data["hwids"])};',
            f'fw,version = {cells(config.version)};',
            f'fw,rollback-index = {cells(config.data["rollback_index"])};',
            f'fw,build-time-minutes = {cells(minutes)};']


def container(description, images, properties, address_cells=1):
    conf = '\n'.join('            ' + line for line in properties)
    return ('/dts-v1/;\n\n/ {\n'
            f'    description = {quote(description)};\n'
            f'    #address-cells = <{address_cells}>;\n'
            '    images {\n' + '\n'.join(images) + '\n    };\n'
            '    configurations {\n        default = "conf-1";\n        conf-1 {\n'
            f'            description = {quote(description)};\n{conf}\n'
            '        };\n    };\n};\n')


def component(config, name, files, output, minutes):
    settings = config.data['components'][name]
    address_cells = 2 if any(image.get(key, 0) > 0xffffffff for image in settings['images'] for key in ('load', 'entry')) else 1
    images = []
    for image in settings['images']:
        lines = [f'        {image["name"]} {{',
                 f'            description = {quote(image["description"])};',
                 f'            data = /incbin/({quote(os.path.relpath(files[image["name"]], output.parent))});',
                 f'            type = {quote(image["type"])};',
                 f'            arch = {quote(image["architecture"])};',
                 f'            compression = {quote(image["compression"])};']
        if 'os' in image: lines.append(f'            os = {quote(image["os"])};')
        for key in ('load', 'entry'):
            if key in image: lines.append(f'            {key} = {cells(image[key], address_cells)};')
        lines += ['            hash-1 { algo = "sha256"; };', '        };']
        images.append('\n'.join(lines))
    properties = metadata(config, name, minutes)
    for role in ('firmware', 'kernel', 'fdt', 'ramdisk'):
        if role in settings: properties.append(f'{role} = {quote(settings[role])};')
    if settings.get('loadables'):
        properties.append(f'loadables = {strings(settings["loadables"])};')
    return container(settings['description'], images, properties, address_cells)


def release(config, identity, hashes, minutes):
    settings = config.data['release']
    images = ['        manifest {\n'
              '            description = "Firmware release manifest";\n'
              f'            data = {quote(settings["manifest"])};\n'
              '            type = "firmware";\n'
              f'            arch = {quote(config.data["architecture"])};\n'
              '            compression = "none";\n'
              '            hash-1 { algo = "sha256"; };\n        };']
    properties = metadata(config, 'release', minutes)
    properties += [f'fw,tag = {quote(identity["tag"])};',
                   f'fw,firmware-id = {quote(identity["firmware_id"])};',
                   f'fw,components = {strings(settings["components"])};']
    if 'bootloader' in settings['components']:
        properties.append('fw,allow-bootloader;')
    for name in ('kernel', 'rootfs'):
        properties += [f'fw,{name}-payload-bytes = {cells(identity[name + "_bytes"], 2)};',
                       f'fw,{name}-payload-sha256 = {quote(identity[name + "_sha256"])};']
    for name in settings['components']:
        properties += [f'fw,{name}-file = {quote(name + ".itb")};',
                       f'fw,{name}-sha256 = {quote(hashes[name])};']
    properties.append('firmware = "manifest";')
    return container(settings['description'], images, properties)

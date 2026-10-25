# SPDX-License-Identifier: Apache-2.0
"""The boot.scr image must pass U-Boot's checks, or U-Boot refuses to run it."""

import struct
import zlib

from mkscr import IH_ARCH_ARM, IH_COMP_NONE, IH_MAGIC, IH_TYPE_SCRIPT, make_script_image

HEADER = struct.Struct('>IIIIIIIBBBB32s')


def parse(image):
    fields = HEADER.unpack(image[:HEADER.size])
    magic, hcrc, _time, size, load, entry, dcrc, _os, arch, typ, comp, name = fields
    return dict(magic=magic, hcrc=hcrc, size=size, load=load, entry=entry, dcrc=dcrc,
                arch=arch, type=typ, comp=comp, name=name.rstrip(b'\0').decode(),
                data=image[HEADER.size:])


def test_header_fields():
    img = parse(make_script_image(b'echo hi\n', 'TE0715 Zephyr boot'))
    assert img['magic'] == IH_MAGIC
    assert (img['arch'], img['type'], img['comp']) == (IH_ARCH_ARM, IH_TYPE_SCRIPT, IH_COMP_NONE)
    assert img['name'] == 'TE0715 Zephyr boot'
    assert img['load'] == img['entry'] == 0


def test_header_crc_as_u_boot_checks_it():
    image = make_script_image(b'echo hi\n')
    img = parse(image)
    # U-Boot computes the header CRC with the CRC field itself set to zero
    zeroed = image[:4] + b'\0\0\0\0' + image[8:HEADER.size]
    assert img['hcrc'] == zlib.crc32(zeroed)


def test_data_is_a_multi_file_image_with_crc():
    script = b'fatload mmc 0 0x0 zephyr.bin\ngo 0x0\n'
    img = parse(make_script_image(script))
    data = img['data']
    assert img['size'] == len(data)
    assert img['dcrc'] == zlib.crc32(data)
    # Script images: a zero-terminated table of lengths, then the script
    assert struct.unpack('>II', data[:8]) == (len(script), 0)
    assert data[8:] == script


def test_long_name_is_truncated_and_terminated():
    img = parse(make_script_image(b'x', 'n' * 40))
    assert img['name'] == 'n' * 31


def test_repository_boot_cmd_builds():
    from sd_install import BOOT_CMD
    with open(BOOT_CMD, 'rb') as f:
        script = f.read()
    assert b'zephyr.bin' in script and b'go 0x100000' in script
    image = make_script_image(script)
    assert parse(image)['data'][8:] == script

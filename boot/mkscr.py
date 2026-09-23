#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Wrap a U-Boot script in a legacy image, like `mkimage -A arm -T script -C none`.

  mkscr.py boot.cmd boot.scr
"""
import struct
import sys
import time
import zlib

IH_MAGIC = 0x27051956
IH_OS_LINUX, IH_ARCH_ARM, IH_TYPE_SCRIPT, IH_COMP_NONE = 5, 2, 6, 0


def make_script_image(script: bytes, name: str = 'boot script') -> bytes:
    # Script images are multi-file images: a zero-terminated length table, then the data
    data = struct.pack('>II', len(script), 0) + script
    header = struct.pack('>IIIIIIIBBBB32s', IH_MAGIC, 0, int(time.time()), len(data), 0, 0,
                         zlib.crc32(data), IH_OS_LINUX, IH_ARCH_ARM, IH_TYPE_SCRIPT,
                         IH_COMP_NONE, name.encode()[:31])
    header = header[:4] + struct.pack('>I', zlib.crc32(header)) + header[8:]
    return header + data


if __name__ == '__main__':
    with open(sys.argv[1], 'rb') as f:
        script = f.read()
    with open(sys.argv[2], 'wb') as f:
        f.write(make_script_image(script, 'TE0715 Zephyr boot'))

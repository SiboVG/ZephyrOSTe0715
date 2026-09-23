# SPDX-License-Identifier: Apache-2.0
"""sd_install.py writes the board's only boot medium: check its safety rules with a fake U-Boot."""

import pytest

import sd_install
from sd_install import BACKUP, install, restore


class FakeUBoot:
    """Records commands; answers `fatls` with the files on the fake card."""

    def __init__(self, files, iminfo_ok=True):
        self.card = set(files)
        self.commands = []
        self.loaded = []
        self.iminfo_ok = iminfo_ok

    def run(self, cmd, timeout=30):
        self.commands.append(cmd)
        if cmd.startswith('iminfo'):
            return '   Verifying Checksum ... OK\n' if self.iminfo_ok else 'Bad Data CRC\n'
        if cmd.startswith('fatwrite'):
            self.card.add(cmd.split()[4])
        return ''

    def files(self):
        return '\n'.join(f'   100   {name}' for name in sorted(self.card))

    def load(self, path, addr):
        self.loaded.append((path, addr))

    def writes(self):
        return [c.split()[4] for c in self.commands if c.startswith('fatwrite')]


@pytest.fixture
def zephyr_bin(tmp_path):
    path = tmp_path / 'zephyr.bin'
    path.write_bytes(b'\0' * 1234)
    return str(path)


def test_first_install_backs_up_petalinux_boot_scr(zephyr_bin):
    ub = FakeUBoot(['BOOT.BIN', 'image.ub', 'boot.scr'])
    install(ub, zephyr_bin)
    assert ub.writes() == [BACKUP, 'zephyr.bin', 'boot.scr']
    # the backup is a copy of the original boot.scr, made before anything else
    assert ub.commands[:2] == [f'fatload mmc 0 {sd_install.SCR_ADDR:#x} boot.scr',
                               f'fatwrite mmc 0 {sd_install.SCR_ADDR:#x} {BACKUP} ${{filesize}}']


def test_reinstall_keeps_the_existing_backup(zephyr_bin):
    ub = FakeUBoot(['BOOT.BIN', 'boot.scr', BACKUP, 'zephyr.bin'])
    install(ub, zephyr_bin)
    assert BACKUP not in ub.writes()
    assert ub.writes() == ['zephyr.bin', 'boot.scr']


def test_nothing_is_written_if_the_script_image_is_bad(zephyr_bin):
    ub = FakeUBoot(['BOOT.BIN', 'boot.scr', BACKUP], iminfo_ok=False)
    with pytest.raises(SystemExit):
        install(ub, zephyr_bin)
    assert ub.writes() == []


def test_files_are_loaded_to_separate_addresses(zephyr_bin):
    ub = FakeUBoot(['boot.scr', BACKUP])
    install(ub, zephyr_bin)
    (bin_path, bin_addr), (_scr, scr_addr) = ub.loaded
    assert bin_path.endswith('zephyr.bin') and bin_addr == sd_install.BIN_ADDR
    assert scr_addr == sd_install.SCR_ADDR
    assert scr_addr - bin_addr > 1234, 'the image must not overlap the script'
    write_bin = next(c for c in ub.commands if c.startswith('fatwrite') and 'zephyr.bin' in c)
    assert write_bin.split()[-1] == hex(1234)


def test_restore_puts_the_backup_back():
    ub = FakeUBoot(['boot.scr', BACKUP])
    restore(ub)
    assert ub.commands[-2] == f'fatload mmc 0 {sd_install.SCR_ADDR:#x} {BACKUP}'
    assert ub.writes() == ['boot.scr']


def test_restore_refuses_without_a_backup():
    ub = FakeUBoot(['boot.scr'])
    with pytest.raises(SystemExit):
        restore(ub)
    assert ub.writes() == []


def test_config_text_is_what_the_board_parses():
    assert sd_install.config_text(6062, 8) == (
        b'# TE0715 board settings, read by boot.scr at every boot (sd_install.py config)\n'
        b'csp_node=6062\ncsp_prefix=8\n')
    assert b'csp_' not in sd_install.config_text().replace(b'# no settings', b'')
    for line in sd_install.config_text().decode().splitlines():
        assert line.startswith('#'), 'a defaults file holds comments only'


@pytest.mark.parametrize('node, prefix', [(0, None), (16382, None), (6061, 14), (6061, -1)])
def test_config_text_refuses_what_the_board_would_refuse(node, prefix):
    with pytest.raises(ValueError):
        sd_install.config_text(node, prefix)


def test_config_is_written_and_read_back():
    ub = FakeUBoot(['boot.scr', BACKUP])
    text = sd_install.config_text(6062)
    sd_install.write_config(ub, text)
    assert ub.writes() == ['te0715.txt']
    write = next(c for c in ub.commands if c.startswith('fatwrite'))
    assert write.split()[-1] == hex(len(text))
    assert any(c.startswith('fatload') and c.endswith('te0715.txt') for c in ub.commands)


def test_boot_script_hands_the_config_to_zephyr():
    from sd_install import BOOT_CMD
    script = open(BOOT_CMD).read()
    # Cleared before loading, so a removed file leaves no stale settings
    clear = script.index('mw.l 0x0f000000 0')
    load = script.index('fatload mmc 0 0x0f000100 te0715.txt')
    stamp = script.index('mw.l 0x0f000000 0x37304554')
    assert clear < load < stamp < script.index('go 0x0')
    # MMU and caches off before the jump, after everything is loaded
    assert script.index('fatload mmc 0 0x0 zephyr.bin') < script.index('dcache off') < script.index('go 0x0')
    assert 'icache off' in script


def test_boot_script_matches_the_firmware():
    import os
    import re
    from sd_install import BOOT_CMD
    bench = os.path.join(os.path.dirname(BOOT_CMD), '..', 'apps', 'fprime_csp_bench')
    script = open(BOOT_CMD).read()
    header = open(os.path.join(bench, 'bench_config.h')).read()
    kconfig = open(os.path.join(bench, 'Kconfig')).read()
    magic = re.search(r'#define BENCH_CONFIG_MAGIC\s+(0x[0-9A-Fa-f]+)', header).group(1)
    offset = int(re.search(r'#define BENCH_CONFIG_TEXT_OFFSET\s+(0x[0-9A-Fa-f]+)', header).group(1), 16)
    addr = int(re.search(r'config APP_BOOT_CONFIG_ADDR.*?default (0x[0-9a-f]+)', kconfig, re.S).group(1), 16)
    assert f'mw.l {addr:#010x} {magic.lower()}' in script
    assert f'fatload mmc 0 {addr + offset:#010x} te0715.txt' in script
    assert f'mw.l {addr + 4:#010x} ${{filesize}}' in script


class FakeSerial:
    def __init__(self):
        self.written = b''

    def reset_input_buffer(self):
        pass

    def write(self, data):
        self.written += data


def uboot_answering(answer):
    ub = object.__new__(sd_install.UBoot)  # no serial port, no xsdb
    ub.serial = FakeSerial()
    ub._read_until = lambda marker, timeout: answer
    return ub


def test_an_unconfirmed_fatwrite_stops_the_script():
    # A board that did not reach the U-Boot prompt answers nothing
    with pytest.raises(SystemExit):
        uboot_answering('').run('fatwrite mmc 0 0x3000000 boot.scr 0x431')
    ok = uboot_answering('1073 bytes written in 23 ms\nZynq> ')
    assert 'bytes written' in ok.run('fatwrite mmc 0 0x3000000 boot.scr 0x431')
    assert uboot_answering('').run('fatls mmc 0') == ''

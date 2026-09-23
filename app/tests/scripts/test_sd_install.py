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

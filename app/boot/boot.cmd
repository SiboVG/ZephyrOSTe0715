echo "=== TE0715: booting Zephyr from zephyr.bin (restore PetaLinux: see docs/guide/boot.md) ==="
# Board settings: te0715.txt from the card, handed to Zephyr in RAM at 0x0f000000
# (CONFIG_APP_BOOT_CONFIG_ADDR): magic and length at +0, the file at +0x100.
# The header is cleared first, so a missing file leaves no stale settings.
mw.l 0x0f000000 0 0x40
if test -e mmc 0 te0715.txt && fatload mmc 0 0x0f000100 te0715.txt 0xf00; then mw.l 0x0f000004 ${filesize}; mw.l 0x0f000000 0x37304554; echo "=== te0715.txt loaded (${filesize} bytes) ==="; fi
fatload mmc 0 0x0 zephyr.bin
# Start Zephyr as a JTAG load does: MMU and caches off. `dcache off` cleans the
# data cache to RAM (the te0715.txt header included) and turns the MMU off too.
# With U-Boot's MMU and caches left on, Zephyr's early boot failed depending on
# what was in RAM (3 of 4 boots after another image had run: a hang, or its own
# code overwritten), probably because it sets up its page tables through the
# cache; with them off, 6 of 6 passed.
icache off
dcache off
go 0x0

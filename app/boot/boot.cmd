echo "=== TE0715: booting Zephyr from zephyr.bin (restore PetaLinux: see docs/guide/boot.md) ==="
fatload mmc 0 0x0 zephyr.bin
go 0x0

/*
 * Copyright The Zephyr Project Contributors
 * SPDX-License-Identifier: Apache-2.0
 */

/*
 * TE0715 board code:
 * - software reset for sys_reboot(), which Zephyr does not implement for the
 *   Zynq-7000 (the default sys_arch_reboot() does nothing);
 * - CAN clock setup that the FSBL of the Trenz test_board reference design
 *   does not do: that design leaves the CAN controllers disabled.
 */

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/syscon.h>
#include <zephyr/init.h>
#include <zephyr/sys/util.h>

/* SLCR PSS_RST_CTRL (Zynq-7000 TRM, appendix B.28): SOFT_RST resets the whole PS */
#define SLCR_PSS_RST_CTRL          0x200
#define PSS_RST_CTRL_SOFT_RST      BIT(0)

void sys_arch_reboot(int type)
{
	ARG_UNUSED(type);

	/* The SLCR is unlocked by the SoC initialisation */
	(void)syscon_write_reg(DEVICE_DT_GET(DT_NODELABEL(slcr)), SLCR_PSS_RST_CTRL,
			       PSS_RST_CTRL_SOFT_RST);
}

#define CAN0_OKAY DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(can0))
#define CAN1_OKAY DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(can1))

#if CAN0_OKAY || CAN1_OKAY

/* SLCR registers (Zynq-7000 TRM, appendix B.28) */
#define SLCR_APER_CLK_CTRL   0x12C
#define SLCR_CAN_CLK_CTRL    0x15C
#define SLCR_CAN_MIOCLK_CTRL 0x160
#define SLCR_CAN_RST_CTRL    0x220

#define APER_CLK_CTRL_CAN0_CPU_1XCLKACT BIT(16)
#define APER_CLK_CTRL_CAN1_CPU_1XCLKACT BIT(17)

#define CAN_CLK_CTRL_DIVISOR1 GENMASK(25, 20)
#define CAN_CLK_CTRL_DIVISOR0 GENMASK(13, 8)
#define CAN_CLK_CTRL_SRCSEL   GENMASK(5, 4) /* 0: IO PLL */
#define CAN_CLK_CTRL_CLKACT1  BIT(1)
#define CAN_CLK_CTRL_CLKACT0  BIT(0)

/* CAN_REF_CLK = IO PLL (1000 MHz, set by ps7_init) / 5 / 2 = 100 MHz */
#define CAN_REF_CLK_HZ   100000000
#define CAN_REF_DIVISOR0 5
#define CAN_REF_DIVISOR1 2

#if CAN0_OKAY
BUILD_ASSERT(DT_PROP(DT_NODELABEL(can0), clock_frequency) == CAN_REF_CLK_HZ);
#endif
#if CAN1_OKAY
BUILD_ASSERT(DT_PROP(DT_NODELABEL(can1), clock_frequency) == CAN_REF_CLK_HZ);
#endif

static int te0715_can_clock_init(void)
{
	const struct device *slcr = DEVICE_DT_GET(DT_NODELABEL(slcr));
	uint32_t aper_mask = 0U;
	uint32_t clkact = 0U;
	uint32_t rst = 0U;
	uint32_t val;
	int err;

	if (CAN0_OKAY) {
		aper_mask |= APER_CLK_CTRL_CAN0_CPU_1XCLKACT;
		clkact |= CAN_CLK_CTRL_CLKACT0;
		rst |= BIT(2) | BIT(0); /* CAN0_REF_RST, CAN0_CPU1X_RST */
	}
	if (CAN1_OKAY) {
		aper_mask |= APER_CLK_CTRL_CAN1_CPU_1XCLKACT;
		clkact |= CAN_CLK_CTRL_CLKACT1;
		rst |= BIT(3) | BIT(1); /* CAN1_REF_RST, CAN1_CPU1X_RST */
	}

	if (!device_is_ready(slcr)) {
		return -ENODEV;
	}

	/* Hold the controllers in reset while their clocks are changed */
	err = syscon_read_reg(slcr, SLCR_CAN_RST_CTRL, &val);
	if (err == 0) {
		err = syscon_write_reg(slcr, SLCR_CAN_RST_CTRL, val | rst);
	}

	/* CAN reference clocks from the internal clock generator, not from MIO */
	if (err == 0) {
		err = syscon_write_reg(slcr, SLCR_CAN_MIOCLK_CTRL, 0U);
	}

	if (err == 0) {
		err = syscon_write_reg(slcr, SLCR_CAN_CLK_CTRL,
				       FIELD_PREP(CAN_CLK_CTRL_DIVISOR1, CAN_REF_DIVISOR1) |
					       FIELD_PREP(CAN_CLK_CTRL_DIVISOR0, CAN_REF_DIVISOR0) |
					       FIELD_PREP(CAN_CLK_CTRL_SRCSEL, 0U) | clkact);
	}

	if (err == 0) {
		err = syscon_read_reg(slcr, SLCR_APER_CLK_CTRL, &val);
	}
	if (err == 0) {
		err = syscon_write_reg(slcr, SLCR_APER_CLK_CTRL, val | aper_mask);
	}

	if (err == 0) {
		err = syscon_read_reg(slcr, SLCR_CAN_RST_CTRL, &val);
	}
	if (err == 0) {
		err = syscon_write_reg(slcr, SLCR_CAN_RST_CTRL, val & ~rst);
	}

	return err;
}

/* After the SLCR syscon device (PRE_KERNEL_1), before the CAN drivers (POST_KERNEL) */
SYS_INIT(te0715_can_clock_init, PRE_KERNEL_2, 0);

#endif /* CAN0_OKAY || CAN1_OKAY */

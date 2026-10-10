/*
 * Blink LED D4 (MIO7) and toggle a GPIO on the TE0701 Pmod J1 (MIO9), and
 * report on the UART what was set and what the MIO9 pin actually reads back.
 * MIO7 is one of the Zynq's output-only MIO pins, so its level cannot be read.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/device_mmio.h>
#include <zephyr/sys/printk.h>

#define TICK_MS 250

/* Zynq PS GPIO: DATA_RO of bank 0 holds the actual level of MIO0..31 */
#define PSGPIO_BASE     DT_REG_ADDR(DT_NODELABEL(psgpio))
#define PSGPIO_SIZE     DT_REG_SIZE(DT_NODELABEL(psgpio))
#define DATA_RO_0_OFF   0x60

static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);
static const struct gpio_dt_spec pmod = GPIO_DT_SPEC_GET(DT_PATH(zephyr_user), pmod_gpios);

static mm_reg_t psgpio_regs;

static int pad_level(const struct gpio_dt_spec *spec)
{
	return (int)((sys_read32(psgpio_regs + DATA_RO_0_OFF) >> spec->pin) & 1U);
}

/*
 * Read MIO9 as an input with its output latch set low. It has a pull-up and
 * nothing else on Pmod J1 drives it, so the pin itself should read high.
 */
static void input_check(void)
{
	gpio_pin_configure_dt(&pmod, GPIO_OUTPUT_LOW);
	gpio_pin_configure_dt(&pmod, GPIO_INPUT);
	k_msleep(10);

	printk("INPUT CHECK MIO9 (pull-up, output latch low): "
	       "gpio_pin_get_raw=%d, pin level (DATA_RO)=%d\n",
	       gpio_pin_get_raw(pmod.port, pmod.pin), pad_level(&pmod));
}

int main(void)
{
	if (!gpio_is_ready_dt(&led) || !gpio_is_ready_dt(&pmod)) {
		printk("GPIO device not ready\n");
		return 0;
	}
	device_map(&psgpio_regs, PSGPIO_BASE, PSGPIO_SIZE, K_MEM_CACHE_NONE);

	printk("TE0715 GPIO demo: LED D4 = MIO7, Pmod J1 GPIO = MIO9, tick %d ms\n", TICK_MS);
	input_check();

	gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);
	gpio_pin_configure_dt(&pmod, GPIO_OUTPUT_INACTIVE);

	bool led_on = false;
	bool pmod_high = false;
	uint32_t mismatches = 0;

	for (uint32_t tick = 0;; tick++) {
		/* MIO9 toggles every tick, the LED every other tick (1 Hz blink) */
		pmod_high = !pmod_high;
		if ((tick % 2) == 0) {
			led_on = !led_on;
		}
		gpio_pin_set_dt(&led, led_on);
		gpio_pin_set_dt(&pmod, pmod_high);
		k_busy_wait(10);

		int pmod_pad = pad_level(&pmod);

		if (pmod_pad != pmod_high) {
			mismatches++;
		}
		printk("[%7u ms] tick %4u: D4 %-3s MIO9 %-4s | MIO9 pin=%d | mismatches %u\n",
		       k_uptime_get_32(), tick, led_on ? "on" : "off", pmod_high ? "high" : "low",
		       pmod_pad, mismatches);

		k_msleep(TICK_MS);
	}
	return 0;
}

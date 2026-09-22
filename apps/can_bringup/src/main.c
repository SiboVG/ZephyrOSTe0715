/*
 * CAN bring-up for the TE0715 on a TE0701 with an external transceiver on
 * Pmod J1:
 * - frames with standard ID 0x100 are echoed back with ID 0x101;
 * - a heartbeat with ID 0x7F0 is sent every second:
 *   byte 0-3 counter (big endian), byte 4 TX errors, byte 5 RX errors,
 *   byte 6 bus state (enum can_state), byte 7 echoed frames (mod 256);
 * - bus state changes and every received frame are logged on the UART.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/can.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/printk.h>

#define ECHO_RX_ID   0x100
#define ECHO_TX_ID   0x101
#define HEARTBEAT_ID 0x7F0

static const struct device *const can_dev = DEVICE_DT_GET(DT_CHOSEN(zephyr_canbus));

CAN_MSGQ_DEFINE(rx_msgq, 32);

/*
 * Frames are sent asynchronously: without another node to acknowledge them,
 * a frame is retransmitted indefinitely and a blocking send would never return.
 */
static atomic_t tx_ok;
static atomic_t tx_failed;

static void tx_done_cb(const struct device *dev, int error, void *user_data)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(user_data);

	atomic_inc(error == 0 ? &tx_ok : &tx_failed);
}

static const char *state_name(enum can_state state)
{
	switch (state) {
	case CAN_STATE_ERROR_ACTIVE:
		return "error-active";
	case CAN_STATE_ERROR_WARNING:
		return "error-warning";
	case CAN_STATE_ERROR_PASSIVE:
		return "error-passive";
	case CAN_STATE_BUS_OFF:
		return "bus-off";
	case CAN_STATE_STOPPED:
		return "stopped";
	default:
		return "unknown";
	}
}

static void state_change_cb(const struct device *dev, enum can_state state,
			    struct can_bus_err_cnt err_cnt, void *user_data)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(user_data);

	printk("STATE %s (tx errors %u, rx errors %u)\n", state_name(state), err_cnt.tx_err_cnt,
	       err_cnt.rx_err_cnt);
}

static void print_frame(const char *dir, const struct can_frame *frame)
{
	printk("%s %s %0*x [%u]", dir, (frame->flags & CAN_FRAME_IDE) ? "ext" : "std",
	       (frame->flags & CAN_FRAME_IDE) ? 8 : 3, frame->id, frame->dlc);
	for (int i = 0; i < can_dlc_to_bytes(frame->dlc); i++) {
		printk(" %02x", frame->data[i]);
	}
	printk("\n");
}

int main(void)
{
	const struct can_filter all_std = {.id = 0, .mask = 0, .flags = 0};
	const struct can_filter all_ext = {.id = 0, .mask = 0, .flags = CAN_FILTER_IDE};
	struct can_frame frame;
	struct can_bus_err_cnt err_cnt;
	enum can_state state;
	uint32_t heartbeats = 0;
	uint32_t echoed = 0;
	int64_t next_heartbeat;
	int err;

	if (!device_is_ready(can_dev)) {
		printk("CAN device %s not ready\n", can_dev->name);
		return 0;
	}

	can_set_state_change_callback(can_dev, state_change_cb, NULL);

	if (can_add_rx_filter_msgq(can_dev, &rx_msgq, &all_std) < 0 ||
	    can_add_rx_filter_msgq(can_dev, &rx_msgq, &all_ext) < 0) {
		printk("failed to add RX filters\n");
		return 0;
	}

	err = can_start(can_dev);
	if (err != 0) {
		printk("failed to start CAN (err %d)\n", err);
		return 0;
	}

	printk("CAN bring-up on %s at %u bit/s: echo 0x%03x -> 0x%03x, heartbeat 0x%03x\n",
	       can_dev->name, DT_PROP(DT_CHOSEN(zephyr_canbus), bitrate), ECHO_RX_ID, ECHO_TX_ID,
	       HEARTBEAT_ID);

	next_heartbeat = k_uptime_get();

	while (true) {
		k_timeout_t wait = K_MSEC(MAX(next_heartbeat - k_uptime_get(), 0));

		if (k_msgq_get(&rx_msgq, &frame, wait) == 0) {
			print_frame("RX", &frame);

			if ((frame.flags & (CAN_FRAME_IDE | CAN_FRAME_RTR)) == 0U &&
			    frame.id == ECHO_RX_ID) {
				frame.id = ECHO_TX_ID;
				err = can_send(can_dev, &frame, K_MSEC(100), tx_done_cb, NULL);
				if (err == 0) {
					echoed++;
				} else {
					printk("echo failed (err %d)\n", err);
				}
			}
			continue;
		}

		(void)can_get_state(can_dev, &state, &err_cnt);

		frame = (struct can_frame){.id = HEARTBEAT_ID, .dlc = 8};
		sys_put_be32(heartbeats, &frame.data[0]);
		frame.data[4] = err_cnt.tx_err_cnt;
		frame.data[5] = err_cnt.rx_err_cnt;
		frame.data[6] = state;
		frame.data[7] = (uint8_t)echoed;

		err = can_send(can_dev, &frame, K_MSEC(100), tx_done_cb, NULL);
		printk("HEARTBEAT %u: %s, tx errors %u, rx errors %u, echoed %u, sent %ld, "
		       "failed %ld, ack errors %u (send %d)\n",
		       heartbeats, state_name(state), err_cnt.tx_err_cnt, err_cnt.rx_err_cnt, echoed,
		       atomic_get(&tx_ok), atomic_get(&tx_failed), can_stats_get_ack_errors(can_dev),
		       err);

		heartbeats++;
		next_heartbeat += MSEC_PER_SEC;
	}

	return 0;
}

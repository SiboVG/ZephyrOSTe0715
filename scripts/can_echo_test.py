#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host side of the apps/can_bringup test, over a Linux SocketCAN interface.

Sends frames with ID 0x100 and checks that the board echoes each one back
with ID 0x101 and the same payload, and that its 0x7F0 heartbeat arrives
about once per second and reports an error-active bus.

  sudo ip link set can0 type can bitrate 1000000 && sudo ip link set can0 up
  app/scripts/can_echo_test.py can0 --count 1000
"""

import argparse
import socket
import struct
import sys
import time

ECHO_RX_ID = 0x100
ECHO_TX_ID = 0x101
HEARTBEAT_ID = 0x7F0
CAN_FRAME = struct.Struct('=IB3x8s')  # struct can_frame: id, len, padding, data
CAN_STATES = ['error-active', 'error-warning', 'error-passive', 'bus-off', 'stopped']


def recv_frame(sock, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    sock.settimeout(remaining)
    try:
        can_id, dlc, data = CAN_FRAME.unpack(sock.recv(CAN_FRAME.size))
    except socket.timeout:
        return None
    return can_id & socket.CAN_EFF_MASK, data[:dlc]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('interface', help='SocketCAN interface, e.g. can0')
    parser.add_argument('--count', type=int, default=200, help='echo frames to send')
    parser.add_argument('--timeout', type=float, default=0.1,
                        help='seconds to wait for each echo')
    args = parser.parse_args()

    sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    sock.bind((args.interface,))

    heartbeats = []
    lost = mismatched = 0
    start = time.monotonic()

    for i in range(args.count):
        payload = struct.pack('>II', i, i ^ 0xA5A5A5A5)
        sock.send(CAN_FRAME.pack(ECHO_RX_ID, len(payload), payload))
        deadline = time.monotonic() + args.timeout
        while True:
            frame = recv_frame(sock, deadline)
            if frame is None:
                lost += 1
                break
            can_id, data = frame
            if can_id == HEARTBEAT_ID:
                heartbeats.append((time.monotonic(), data))
            elif can_id == ECHO_TX_ID:
                mismatched += data != payload
                break

    # Collect heartbeats for a little longer to judge their period
    deadline = time.monotonic() + 2.5
    while (frame := recv_frame(sock, deadline)) is not None:
        if frame[0] == HEARTBEAT_ID:
            heartbeats.append((time.monotonic(), frame[1]))

    elapsed = time.monotonic() - start
    print(f'echo: {args.count - lost - mismatched}/{args.count} ok, {lost} lost, '
          f'{mismatched} wrong payload in {elapsed:.1f} s')

    ok = lost == 0 and mismatched == 0
    if len(heartbeats) < 2:
        print(f'heartbeat: only {len(heartbeats)} received')
        ok = False
    else:
        period = (heartbeats[-1][0] - heartbeats[0][0]) / (len(heartbeats) - 1)
        counter, tec, rec, state, _ = struct.unpack('>IBBBB', heartbeats[-1][1])
        state_name = CAN_STATES[state] if state < len(CAN_STATES) else str(state)
        print(f'heartbeat: {len(heartbeats)} received, period {period:.3f} s, last counter '
              f'{counter}, {state_name}, tx errors {tec}, rx errors {rec}')
        ok &= 0.9 < period < 1.1 and state == 0

    print('PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())

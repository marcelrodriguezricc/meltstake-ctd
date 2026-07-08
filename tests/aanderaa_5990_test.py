#!/usr/bin/env python3
"""
Connectivity / communication test for an Aanderaa 5990 (5819/5990 family)
Conductivity Sensor over RS-232 -> RS232/TTL converter -> Pi 5 GPIO14/15 (/dev/ttyAMA0).

Uses the Aanderaa "Smart Sensor Terminal" ASCII protocol. Read-only:
sends no Set/Save, so it cannot change the sensor's configuration.

Protocol facts this script relies on (from the TD321 manual):
  - Commands are ASCII, terminated by CR+LF (\\r\\n).
  - Sensor sleeps to save power; any char wakes it (~500 ms to be ready).
    A run of '/' chars is the manual's recommended wake string (comment-lead,
    ignored by the parser, so it's harmless).
  - Valid command -> '#', error -> '*'. Wake-ready indicator -> '!'.
  - Get / Do Sample / Get All / Help are read-only (no passkey needed).
  - Factory default: 9600 baud, no flow control, 8N1.

Usage:
    python3 aanderaa_5990_test.py                 # default /dev/ttyAMA0 @ 9600
    python3 aanderaa_5990_test.py --port /dev/ttyAMA0 --baud 9600
    python3 aanderaa_5990_test.py --sweep         # try common baud rates
"""

import argparse
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial not found. Install with:  sudo apt install python3-serial")


def show(tag, data: bytes):
    """Print received bytes as both hex and a readable repr."""
    if not data:
        print(f"  [{tag}] (nothing)")
        return
    hexs = " ".join(f"{b:02X}" for b in data)
    try:
        txt = data.decode("ascii", errors="replace")
    except Exception:
        txt = repr(data)
    print(f"  [{tag}] {len(data)} bytes")
    print(f"        hex : {hexs}")
    print(f"        text: {txt!r}")


def wake(ser):
    """Send the manual's comment-lead wake string, then a CR, and drain."""
    # '/' lines are ignored by the parser but wake the electronics.
    ser.reset_input_buffer()
    ser.write(b"/" * 40 + b"\r\n")
    ser.flush()
    time.sleep(0.6)          # electronics need up to ~500 ms to come ready
    ser.write(b"\r\n")       # a bare Enter; ready sensor stays silent, sleeping one sends '!'
    ser.flush()
    time.sleep(0.4)
    show("wake", ser.read(256))


def send(ser, cmd: str, wait=1.2):
    """Send one ASCII command terminated with CR+LF and read the reply."""
    ser.reset_input_buffer()
    ser.write(cmd.encode("ascii") + b"\r\n")
    ser.flush()
    time.sleep(wait)
    # read whatever is there, then a moment more in case it's still trickling out
    buf = ser.read(4096)
    time.sleep(0.3)
    buf += ser.read(4096)
    print(f"> {cmd}")
    show("resp", buf)
    return buf


def run_once(port, baud):
    print(f"\n=== {port} @ {baud} 8N1, no flow control ===")
    try:
        ser = serial.Serial(
            port, baud, bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
            timeout=0.5, rtscts=False, xonxoff=False,
        )
    except serial.SerialException as e:
        print(f"  could not open port: {e}")
        return b""

    with ser:
        wake(ser)
        # Help is the safest liveness probe; then a real measurement.
        got = b""
        got += send(ser, "Help")
        got += send(ser, "Do Sample")
        got += send(ser, "Get All", wait=2.0)
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyAMA0")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--sweep", action="store_true",
                    help="try common baud rates instead of a single one")
    args = ap.parse_args()

    if args.sweep:
        for b in (9600, 4800, 57600, 115200, 2400, 1200, 300):
            got = run_once(args.port, b)
            # '#' ack, '!' ready, or any printable ASCII strongly implies a match
            if any(x in got for x in (b"#", b"!", b"Conductivity", b"5990", b"5819")):
                print(f"\n*** Promising response at {b} baud — likely the right rate. ***")
                break
    else:
        run_once(args.port, args.baud)

    print("\nInterpreting what you saw:")
    print("  '!'  -> sensor woke up and is ready (great — link works)")
    print("  '#'  -> command acknowledged (definitive proof of two-way comms)")
    print("  '*'  -> error reply (still proof of comms; just a bad command/state)")
    print("  ASCII numbers / 'Conductivity...' -> a real reading came back")
    print("  '<'  or XML-looking text -> sensor is in AADI Real-Time mode (still alive)")
    print("  steady garbage across a baud -> wrong baud; try --sweep")
    print("  total silence at every baud -> wiring / power / logic-level, not protocol")


if __name__ == "__main__":
    main()
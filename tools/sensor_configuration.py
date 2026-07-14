#!/usr/bin/env python3
"""
Standalone configuration tool for the Aanderaa 5990 Conductivity Sensor.

Run this to write deployment settings to the sensor over RS-232, then
exit.

Edit the USER SETTINGS block below, then run:

    python3 sensor_configuration.py

"""

import time
import serial

# ══════════════════════════════ USER SETTINGS ══════════════════════════════

# Connection
PORT = "/dev/ttyAMA0" # Sensor's serial device (/dev/ttyAMA0 is the default for Raspberry Pi's UART pins)
BAUD = 9600  # Sensor's baud rate (factory default 9600)

# Sensor Settings
INTERVAL_S = 2.0 # Sampling interval, seconds (allowed 1 – 15300)
PRESSURE_KPA = 0.0 # Fixed pressure for derived params, in kPa (only used if ENABLE_DERIVED is True)
ENABLE_DERIVED = False # Includes derived values for Salinity, Density and Speed of sound
ENABLE_POLLED_MODE = False # True = Sensor outputs only when polled by a "Do Sample" message, False = sensor free-runs at INTERVAL_S, this software assumes this is set to False

# System configuration
ENABLE_SLEEP = False # Sensor sleeps when left not queried 

# Site info
LOCATION = ""  # Free-text site name
GEOGRAPHIC_POSITION = ""  # "lat,lon" decimal degrees, e.g. "60.323605,5.37225"
VERTICAL_POSITION = ""  # Free-text depth/height note
REFERENCE = ""  # Free-text reference / notes

# Script Behavior
PASSKEY = 1000 # Access level for Set commands (1000 covers all user properties)
SAVE = True # Persist to sensor flash so settings survive a power cycle
VERIFY = True # After writing, read the values back and print them to confirm

# ════════════════════════════════════════════════════════════════════════════


def _wake(device, settle=0.7):
    """Rouse the sensor from sleep and prime the parser.
    """

    device.reset_input_buffer()
    device.write(b"/" * 60 + b"\r\n") # Wake the electronics
    device.flush()
    time.sleep(settle) # Allow ~500 ms startup
    device.write(b"//\r\n") # Throwaway primer line
    device.flush()
    time.sleep(0.2)
    device.reset_input_buffer() # Discard wake echo / '!' indicator

def _query(device, command, ack_wait=25.0, start_timeout=3.0):
    """Send one Smart Sensor Terminal command and return (text, status).
    """

    # Clear the serial input buffer
    device.reset_input_buffer()

    # Send a primer line and clear the serial buffer
    device.write(command.encode("ascii") + b"\r\n")
    device.flush()

    # Initialize raw byte holder variable and timer
    raw = bytearray()
    start = time.time()

    while True:

        # Grab everything available in the serial input buffer
        chunk = device.read(device.in_waiting or 1)
        if chunk:
            raw.extend(chunk)

        # Strip flow-control bytes (XON/XOFF) from the reply, then look for '#'/'*' only at the very start or immediately after a CR/LF
        clean = bytes(raw).replace(b"\x11", b"").replace(b"\x13", b"")
        if (clean.startswith(b"#") or clean.startswith(b"*")
                or b"\n#" in clean or b"\r#" in clean
                or b"\n*" in clean or b"\r*" in clean):
            break

        # Record the time
        now = time.time()

        # Validate the reply
        if not raw and now - start > start_timeout:
            break # Nothing came back
        if now - start > ack_wait:
            break # Terminator never arrived

    # Convert to human-readable text
    text = bytes(raw).replace(b"\x11", b"").replace(b"\x13", b"").decode(
        "ascii", errors="replace")
    
    # Split into lines
    lines = [ln.strip() for ln in text.splitlines()]

    # Parse status character
    status = ("ok" if "#" in lines
              else "error" if any(ln.startswith("*") for ln in lines)
              else "nak")
    
    return text, status


def _fmt(v):
    """Keep numbers tidy in the command string."""
    f = float(v)
    return str(int(f)) if f.is_integer() else f"{f:g}"


def _yesno(flag):
    """Booleans are written to the sensor as Yes/No, not True/False."""
    return "Yes" if flag else "No"


def configure(device):
    """Write all settings to the sensor. Returns True only if every command (and the Save, if enabled) was acknowledged."""

    # Prepare array of commands from above user settings
    commands = [
        f"Set Passkey({PASSKEY})",
        f"Set Enable Sleep({_yesno(ENABLE_SLEEP)})",
        f"Set Pressure({_fmt(PRESSURE_KPA)})",
        f"Set Enable Derived Parameters({_yesno(ENABLE_DERIVED)})",
        f"Set Enable Polled Mode({_yesno(ENABLE_POLLED_MODE)})",
        f"Set Interval({_fmt(INTERVAL_S)})",
    ]

    # If a value is provided, prepare an array with the metadata strings from above user settings and append to the commands array
    for prop, value in (
        ("Location", LOCATION),
        ("Geographic Position", GEOGRAPHIC_POSITION),
        ("Vertical Position", VERTICAL_POSITION),
        ("Reference", REFERENCE),
    ):
        if value:
            commands.append(f"Set {prop}({value})")

    # For each command...
    for cmd in commands:

        # Send it to the device
        text, status = _query(device, cmd)

        if status != "ok":
            print(f"FAILED TO WRTITE: {cmd} [status={status}] {text.strip()}")
            return False
        print(f"SUCCESSFULLY WROTE: {cmd}")

    # If user specifies they want the settings saved to flash so they don't restart on power cycle...
    if SAVE:
        print("Writing flash, up to ~20s...")

        # Message the device to save
        text, status = _query(device, "Save")

        # If save fails, throw warning
        if status != "ok":
            print(f"FAILED TO SAVE: [status={status}] {text.strip()}")
            return False
        print("Saved successfully, settings persisted to flash")

    return True

def verify(device):
    """Read the configured properties back and print them for confirmation."""
    for prop in ("Enable Sleep", "Interval", "Pressure",
                 "Enable Derived Parameters", "Enable Polled Mode",
                 "Location", "Geographic Position",
                 "Vertical Position", "Reference"):
        text, _ = _query(device, f"Get {prop}")
        value = next((ln.strip() for ln in text.splitlines()
                      if ln.strip() and ln.strip() != "#"), "(no response)")
        print(f"  {value}")


def main():
    print(f"Opening {PORT} at {BAUD} baud ...")

    # Try to initialize serial connection, or else throw error
    try:
        device = serial.Serial(
            PORT, BAUD, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE, timeout=0.2)
    except serial.SerialException as e:
        print(f"ERROR: could not open port: {e}")
        return

    with device:
        # Wake device
        _wake(device)

        # Write configuration
        print("Writing configuration:")
        ok = configure(device)

        # If configuration is successful, verify settings
        if ok and VERIFY:
            print("Reading back:")
            verify(device)

    print("Done." if ok else "Finished with errors — see above.")


if __name__ == "__main__":
    main()
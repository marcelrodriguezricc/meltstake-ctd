import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from . import utils

_DATA_PATH = None


def _wake(device, settle=0.7):
    """Rouse the sensor from sleep and prime the parser. The sensor powers down between samples; any character wakes it, but the first real command after waking can lose a leading byte while the UART starts up (~500 ms). The '/' lines below are ignored by the command parser, so they harmlessly absorb that byte loss before the first real command.
    """

    # Clear the serial input buffer
    device.reset_input_buffer()

    # Wake electronics out of sleep mode with primer line
    device.write(b"/" * 60 + b"\r\n")

    # Wait for the operating system's outbound buffer to drain
    device.flush()

    # Allow half a second for startup
    time.sleep(settle)

    # Throwaway primer line
    device.write(b"//\r\n")
    device.flush()
    time.sleep(0.2)

    # Discard wake echo
    device.reset_input_buffer()


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


def _extract(text: str, tag: str):
    """Slice a single XML element out of a raw sensor response, discarding the surrounding '#' ack and any stray bytes."""

    close = f"</{tag}>"
    start, end = text.find(f"<{tag}"), text.find(close)
    return text[start:end + len(close)] if start != -1 and end != -1 else None


def set_data_path(data_path):
    """Set global data path variable for "scan" module."""

    global _DATA_PATH
    _DATA_PATH = data_path


def write_properties_to_log(device) -> None:
    """Append a one-time record of the sensor's configuration and output parameters to the log.
    """

    # Wake the sensor and halt the data stream so replies come back clean
    _wake(device)
    _, stop_status = _query(device, "Stop")
    if stop_status != "ok":
        utils.append_log(f"WARNING: Stop not acknowledged (status={stop_status})")
    time.sleep(0.3)                  

    # Get property values and write them to the log
    cfg_text, cfg_status = _query(device, "Get All")
    if cfg_status != "ok":
        utils.append_log(f"WARNING: could not read Get All (status={cfg_status})")
    else:
        utils.append_log("Sensor configuration record (Get All):")
        for line in cfg_text.splitlines():
            line = line.strip()
            if not line or line == "#":
                continue 
            utils.append_log(f"  {line}")

    # Get DataXML for the output parameters and parse
    data_text, data_status = _query(device, "Get DataXML")
    data_xml = _extract(data_text, "SensorData")
    if data_xml is None:
        utils.append_log(f"WARNING: could not read DataXML (status={data_status})")
        return
    try:
        droot = ET.fromstring(data_xml)
        utils.append_log("  Output parameters:")
        for pt in droot.iter("Point"):
            line = f"    {pt.get('Descr', '?')}"
            if pt.get("Unit"):
                line += f" [{pt.get('Unit')}]"
            rmin, rmax = pt.get("RangeMin"), pt.get("RangeMax")
            if rmin is not None and rmax is not None:
                line += f", range {rmin} to {rmax}"
            utils.append_log(line)
    except ET.ParseError as e:
        utils.append_log(f"WARNING: could not parse DataXML ({e})")


def record_data_stream(device, stop_event=None, heartbeat=60.0) -> None:
    """Listen to the sensors output and append each raw MEASUREMENT line, timestamped, to a .txt file in _DATA_PATH. Sends Start to begin the stream, listens, and sends Stop on exit. The sample rate is set by the sensor's Interval property. Runs until `stop_event` is set or Ctrl-C. Logs a heartbeat with the sample count every `heartbeat` seconds.
    """

    # If data path is not set, write error to log and terminate
    if _DATA_PATH is None:
        utils.append_log("WARNING: _DATA_PATH not set; cannot record data")
        return

    # Set data path for raw data file
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    txt_path = Path(_DATA_PATH) / f"raw_{stamp}.txt"
    utils.append_log(f"Recording raw data to {txt_path.name} (free-running)")

    # Wake the device
    _wake(device)

    # Send the start message to the device to begin recording, throw a warning if failed
    _, start_status = _query(device, "Start")
    if start_status != "ok":
        utils.append_log(f"WARNING: Start not acknowledged (status={start_status})")

    # Initialize number of samples
    samples = 0

    # Instantiate a buffer to hold incoming bytes
    buf = bytearray()

    # Skip the first fragment to sync, in case we begin receiving the incoming stream mid-line
    synced = False

    # Instantiate the timer
    last_beat = time.monotonic()

    # Clear buffer before listening
    device.reset_input_buffer()

    # Write to the raw text file and...
    with txt_path.open("a", encoding="utf-8") as f:
        try:

            # While loop runs unless stop event is received by user input
            while stop_event is None or not stop_event.is_set():

                # Read whatever has arrived, throw an error if unable to read
                try:
                    chunk = device.read(device.in_waiting or 1)
                except OSError as e:
                    utils.append_log(f"WARNING: serial read error while recording ({e})")
                    break

                # If chunk is read.
                if chunk:

                    # Drop XON/XOFF, normalise CR -> LF
                    buf.extend(chunk.replace(b"\x11", b"").replace(b"\x13", b"").replace(b"\r", b"\n"))

                    while b"\n" in buf:

                        # Split into discrete lines based on termination character
                        raw_line, _, buf = buf.partition(b"\n")
                        
                        # Confirms we're not mid line
                        if not synced:
                            synced = True
                            continue

                        # Convert bytes to ASCII
                        line = raw_line.decode("ascii", errors="replace").strip()
                        
                        # Discard everything before "MEASUREMENT"
                        idx = line.find("MEASUREMENT")
                        if idx == -1:
                            continue

                        # Get datetime and append to line
                        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                        f.write(f"{ts}\t{line[idx:]}\n")

                        # Flush input buffer
                        f.flush()

                        # Count sample
                        samples += 1

                # Periodic "still alive" confirmation
                if time.monotonic() - last_beat >= heartbeat:
                    utils.append_log(f"Recording OK — {samples} samples written")
                    last_beat = time.monotonic()

        # Stop if user interrupts
        except KeyboardInterrupt:
            _query(device, "Stop")
            utils.append_log(f"Stopped recording ({samples} samples written)")
            pass

    # Halt the stream now that we're done listening
    _query(device, "Stop")
    utils.append_log(f"Stopped recording ({samples} samples written)")
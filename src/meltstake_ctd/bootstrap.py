import tomllib
import serial
import json
from serial.tools import list_ports
from datetime import datetime, timezone
from pathlib import Path

from . import utils
from . import record

_DATA_PATH = None

_DEFAULT_CONNECTION: dict[str, object] = {
    "device_name": "/dev/ttyAMA0",
    "port": None,
}

_DEFAULT_SETTINGS: dict[str, float] = {
    "interval": 1.0,
    "pressure": 0.0,
}

import math

def _norm_optional_str(val: object) -> str | None:
    """Checks for an input; if it's a string, strips whitespace from string if present."""

    # If no input is given, return None
    if val is None:
        return None
    
    # Strip whitespace, return none if all whitespace
    if isinstance(val, str):
        s = val.strip()
        return None if s == "" else s
    
    return str(val).strip() or None

def _set_default(dst: dict, key: str, default: object, why: str) -> None:
    """Sets input key to default value."""

    utils.append_log(f"Config '{key}' invalid ({why}); using default {default!r}")

    # Set input key to default
    dst[key] = default

def _coerce_float(raw):
    """Return a finite float, or None if raw can't be read as one."""

    if isinstance(raw, bool):
        return None
    try:
        n = float(raw)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(n):
        return None
    return n


def _clamp_float(dst: dict, key: str, default: float, lo: float, hi: float) -> None:
    """Coerce dst[key] to a float in [lo, hi]; fall back to default if it isn't a valid float."""

    # Get value from key
    raw = dst.get(key, None)

    # Set to float
    n = _coerce_float(raw)

    # If None is returned, set to default
    if n is None:
        _set_default(dst, key, default, f"not a float: {raw!r}")
        return

    # Clamp into range and write back
    dst[key] = max(lo, min(n, hi))

def _auto_detect_port(device_name: str) -> str | None:
    """Automatic serial port detection, compatible with macOS and Raspberry Pi."""

    ports = list_ports.comports()

    # Log detected ports for debugging
    for p in ports:
        utils.append_log(f"Detected port: {p.device} | Description: {p.description} | Manufacturer: {p.manufacturer}")

    # Match against device, description, and manufacturer
    for p in ports:
        fields = [
            (p.device or "").lower(),
            (p.description or "").lower(),
            (p.manufacturer or "").lower(),
        ]
        if any(device_name.lower() in field for field in fields):
            return p.device

    # Fallback: return first available port
    if ports:
        utils.append_log(f"No port matched '{device_name}', falling back to first available: {ports[0].device}")
        return ports[0].device

    return None

def _load_config(config: str) -> dict:
    """Load configuration file from ROOT/configs directory.

    Falls back to default_config.toml if the requested config can't be loaded.
    """

    # Establish configuration path
    ROOT = Path(__file__).resolve().parents[2]
    configs_dir = ROOT / "configs"
    primary_path = configs_dir / Path(config)
    fallback_path = configs_dir / "default_config.toml"

    # Function to load configuration .toml file at given path as a dictionary
    def _try_load(path: Path) -> dict:
        with path.open("rb") as f:
            return tomllib.load(f)

    # Try requested config
    try:
        cfg = _try_load(primary_path)

    # If it fails, fallback to default_config.toml
    except (FileNotFoundError, tomllib.TOMLDecodeError, OSError) as e1:
        utils.append_log(f"Failed to load configuration file at {primary_path}: {e1}")

        # If primary already is the fallback, don't loop
        if primary_path.resolve() == fallback_path.resolve():
            raise

        utils.append_log(f"Falling back to default configuration at {fallback_path}")

        # Try default_config.toml
        try:
            cfg = _try_load(fallback_path)
        except (FileNotFoundError, tomllib.TOMLDecodeError, OSError) as e2:
            utils.append_log(f"Failed to load fallback configuration at {fallback_path}: {e2}")
            raise RuntimeError(
                f"Failed to load config {primary_path} and fallback {fallback_path}"
            ) from e2
        else:
            utils.append_log(f"Fallback configuration file loaded: {fallback_path}")
            return cfg
    else:
        utils.append_log(f"Configuration file loaded: {primary_path}")
        return cfg
    
def init_data_dir(data_dir: str) -> None:
    """Initialize data directory for storage of files generated during runtime."""

    # Get datetime and format for file naming
    utc_dt = datetime.now(timezone.utc)
    dt_formatted = utc_dt.strftime("%Y-%m-%d_%H.%M.%S")
    data_path = f"{data_dir}/{dt_formatted}"
 
    # Set path to data directory as global variable in all modules
    global _DATA_PATH 
    _DATA_PATH = data_path
    utils.set_data_path(data_path)
    record.set_data_path(data_path)

def create_config_json(config: dict) -> None:
    """Write configuration to a json file for parsing."""

    # Set path
    json_path = Path(f"{_DATA_PATH}/configuration.json")

    # Create json file
    try:
        json_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        utils.append_log(f"Failed to create configuration.json at {json_path}: {e}")
    else:
        utils.append_log(f"Created configuration.json at {json_path}")

    # Append configuration dictionary to json
    try:
        with json_path.open("w", encoding="utf-8") as f:
            json.dump({"scan": config}, f, indent=2, sort_keys=True)
            f.write("\n")
    except Exception as e:
        utils.append_log(f"Failed to write config dictionary to configuration.json at {json_path}: {e}")
    else:
        utils.append_log(f"Wrote config dictionary to configuration.json at {json_path}")

def parse_config(config: str) -> tuple[dict, dict]:
    """Parse configuration .toml file and return connection + switch parameters as dicts."""

    # Load configuration from .toml file
    cfg = _load_config(config)

    # Try to get connection and config keys, if it fails, set to default
    try:
        connection = dict(cfg.get("connection", {}))
        settings = dict(cfg.get("settings ", {}))
    except Exception as e:
        utils.append_log(f"Failed to parse configuration from config.toml: {e}, setting to default.")
        settings = _DEFAULT_SETTINGS
        raise
    
    # Fill missing connection keys with defaults
    for k, v in _DEFAULT_CONNECTION.items():
        connection.setdefault(k, v)

    # Validate connection parameters
    connection["port"] = _norm_optional_str(connection.get("port"))
    connection["device_name"] = _norm_optional_str(connection.get("device_name"))

    # If both are missing, force a sane device_name default for auto-detect
    if connection["port"] is None and connection["device_name"] is None:
        _set_default(connection, "device_name", _DEFAULT_CONNECTION["device_name"], "both port and device_name missing/blank")

    # Fill missing switch command keys with defaults
    for k, v in _DEFAULT_SETTINGS.items():
        settings.setdefault(k, v)

    # Validate switch command parameters
    _clamp_float(settings, "interval", _DEFAULT_SETTINGS["interval"], 1.0, 15300.0)
    _clamp_float(settings, "pressure", _DEFAULT_SETTINGS["pressure"], 0, 110000.0)

    utils.append_log(f"Configuration file parsed - {settings}")

    return connection, settings

def create_log_file() -> None:
    """Create log file and write an init line."""

    # Create a log file at directory "logs"
    log_path = utils.make_file("ctd.log")

    utils.append_log(f"Melt Stake Aanderaa 5990 CTD deployment log initialized")
    utils.append_log(f"Path to log: {log_path}")

def init_serial(connection: dict, baud: int = 9600, timeout: float = 1.0) -> serial.Serial:
    """Initialize and return a serial connection.

    Args:
        connection: Dictionary containing port and device name strings as set in configuration file (from `parse_config()`).
        timeout: Read/write timeout in seconds.

    Returns:
        An opened `serial.Serial` instance.

    Raises:
        serial.SerialException: If no port is available or the port cannot be opened.
        OSError: If the OS refuses access to the device (permissions/in-use).
    """
    
    # Get variables from connection configuration
    port = connection["port"]
    device_name = connection["device_name"]

    # If no port is specified, auto-detect which port the device is on
    if port is None:
        port = _auto_detect_port(device_name)

    # If no port, raise an error
    if port is None or str(port).strip() == "":
        utils.append_log("No serial port provided and auto-detection failed, exiting program.")
        raise serial.SerialException("No serial port provided and auto-detection failed, exiting program.")
    
    # Try to connect to device
    try:
        ser = serial.Serial(
            port = port,
            baudrate = baud,
            bytesize = serial.EIGHTBITS,
            parity = serial.PARITY_NONE,
            stopbits = serial.STOPBITS_ONE,
            timeout = timeout,
            write_timeout = timeout,
        )
    except (serial.SerialException, OSError) as e:
        utils.append_log(f"Failed to open serial port {port!r} at {baud} baud: {e}")
        raise
    else:
        utils.append_log(f"Serial port opened: {port!r} @ {baud} baud")

    # Reset read and write buffers
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    return ser
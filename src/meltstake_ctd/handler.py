import serial
import threading
import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

class Handler:
    config: str | Path
    data_dir: Path
    data_path: Path
    init_time: str
    connection: dict
    device: serial.Serial

    # Runs on object initialization
    def __init__(self, config: str = "default_config.toml", data_dir: str | None = None):

        # Store inputs
        self.config = config
        self.data_dir = data_dir

    # Begins the scanning process
    def start_record(self, stop_event: threading.Event | None = None) -> None:
        print("recording")
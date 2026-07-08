import serial
import threading
import logging
import threading
from pathlib import Path

from . import bootstrap

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

        # Initialize data directory and log file
        bootstrap.init_data_dir(self.data_dir)
        bootstrap.create_log_file()

        # From configuration file - populate connection and switch command dictionaries
        self.connection, self.switch_cmd = bootstrap.parse_config(self.config)

    # Begins the scanning process
    def start_record(self, stop_event: threading.Event | None = None) -> None:
        print("recording")
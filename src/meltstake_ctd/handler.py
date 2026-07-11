import serial
import threading
import logging
import threading
from pathlib import Path

from . import bootstrap
from . import record

log = logging.getLogger(__name__)

class Handler:
    config: str | Path
    data_dir: Path
    init_time: str
    connection: dict
    device: serial.Serial
    interval: float

    # Runs on object initialization
    def __init__(self, config: str = "default_config.toml", data_dir: str | None = None):

        # Store inputs
        self.config = config
        self.data_dir = data_dir

        # Initialize data directory and log file
        bootstrap.init_data_dir(self.data_dir)
        bootstrap.create_log_file()

        # From configuration file - populate connection and switch command dictionaries
        self.connection = bootstrap.parse_config(self.config)

        # Initialize the serial connection
        self.device = bootstrap.init_serial(self.connection)

    # Begins the scanning process
    def start_record(self, stop_event: threading.Event | None = None) -> None:
        record.write_properties_to_log(self.device)
        record.record_data_stream(self.device, stop_event=None)
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import utils

_DATA_PATH = None

def set_data_path(data_path):
    """Set global data path variable for "scan" module."""

    global _DATA_PATH
    _DATA_PATH = data_path
#!/usr/bin/env python3
"""
Parse a raw Aanderaa 5990 capture (raw_*.txt) into a human-readable CSV.

Edit the paths below and run: python3 parse_raw.py
"""

import csv
from pathlib import Path

# ══════════════════════════════ USER SETTINGS ══════════════════════════════
INPUT_PATH  = "raw_data.txt" # Raw capture to read
OUTPUT_PATH = "" # leave "" to write next to the input as <input>.csv
# ════════════════════════════════════════════════════════════════════════════


def _plain(value):
    """Scientific notation -> plain decimal, e.g. '2.931845E-03' -> '0.002931845'.
    Non-numeric values pass through unchanged."""
    try:
        return f"{float(value):.7g}"
    except ValueError:
        return value


def main():

    # Set input and output paths
    in_path = Path(INPUT_PATH)
    out_path = Path(OUTPUT_PATH) if OUTPUT_PATH else in_path.with_suffix(".csv")

    # If path does not exist, throw an error and terminate
    if not in_path.exists():
        print(f"ERROR: input file not found: {in_path}")
        return

    # Initialize loop counter / boolean variables
    header_written = False
    rows = skipped = 0

    # Open input file
    with in_path.open(encoding="utf-8") as fin, out_path.open("w", newline="", encoding="utf-8") as fout:

        # Create the .csv
        writer = csv.writer(fout)

        # For each line in the input file...
        for raw in fin:

            # Strip termination bytes to get fields
            fields = raw.rstrip("\n").split("\t")

            # Valid line: timestamp, then a MEASUREMENT record somewhere after it.
            if "MEASUREMENT" not in fields or len(fields) < 5:
                skipped += 1
                continue

            # Get the fields
            ts = fields[0]

            # Starting at MEASUREMENT, skip first three metadata fields, so the rest are alternating indices where odd are measurements and even are field names
            m = fields.index("MEASUREMENT")
            body = fields[m + 3:]

            # Get field labels
            labels = body[0::2] 
            values = [_plain(v) for v in body[1::2]]

            # Write the header once before first line
            if not header_written:
                writer.writerow(["time_utc"] + labels)
                header_written = True
            
            # Write value to current row
            writer.writerow([ts] + values)
            rows += 1

    note = f" ({skipped} lines skipped)" if skipped else ""
    print(f"Wrote {rows} rows to {out_path}{note}")


if __name__ == "__main__":
    main()
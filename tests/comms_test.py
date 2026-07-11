import serial, time
d = serial.Serial("/dev/ttyAMA0", 9600, timeout=0.2)
d.reset_input_buffer()
d.write(b"/" * 60 + b"\r\n"); d.flush(); time.sleep(0.8)
d.reset_input_buffer()
d.write(b"Get Interval\r\n"); d.flush(); time.sleep(1.0)
print("reply:", repr(d.read(500)))
d.close()
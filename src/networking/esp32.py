"""USB serial transport for the managed controller's absolute-pulse protocol."""

import time


def pair_line(pan_us, tilt_us):
    """Encode one atomic target pair; the firmware validates BOTH before moving."""
    if type(pan_us) is not int or type(tilt_us) is not int:
        raise ValueError("Pulse commands must be integers")
    return f"m {pan_us} {tilt_us}\n".encode("ascii")


class SerialLink:
    def __init__(self, port, baud=115200, serial_factory=None):
        if serial_factory is None:
            import serial

            serial_factory = serial.Serial
        self.serial = serial_factory(
            port, baudrate=baud, timeout=0.02, write_timeout=0.2
        )
        self._receive = bytearray()
        # Opening some boards resets them. Query until the version banner is
        # observed; do not send motion into a board whose firmware is unknown.
        deadline = time.monotonic() + 5.0
        next_query = 0.0
        ready = False
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_query:
                self.serial.write(b"?\n")
                next_query = now + 0.25
            if any(line.startswith("PROTO 1 ") for line in self.read_lines()):
                ready = True
                break
            time.sleep(0.01)
        if not ready:
            self.serial.close()
            raise RuntimeError(
                "No PROTO 1 reply: upload this release's TurretController firmware"
            )

    def send_targets(self, pan_us, tilt_us):
        payload = pair_line(pan_us, tilt_us)
        if self.serial.write(payload) != len(payload):
            raise OSError("Incomplete serial command write")

    def stop(self):
        self.serial.write(b"x\n")

    def read_lines(self):
        """Bound receive memory even if a device sends malformed/no-newline data."""
        waiting = min(self.serial.in_waiting, 4096)
        if waiting:
            self._receive.extend(self.serial.read(waiting))
        lines = []
        while b"\n" in self._receive:
            raw, _, rest = self._receive.partition(b"\n")
            self._receive = bytearray(rest)
            lines.append(raw.decode("ascii", errors="replace").strip())
        if len(self._receive) > 4096:
            self._receive.clear()
        return lines

    def close(self):
        try:
            self.stop()
        finally:
            self.serial.close()

import unittest
from networking.esp32 import SerialLink, pair_line


class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.incoming = bytearray()
        self.writes = []
        self.closed = False

    @property
    def in_waiting(self):
        return len(self.incoming)

    def write(self, payload):
        self.writes.append(payload)
        if payload == b"?\n":
            self.incoming.extend(b"PROTO 1 pulse_us managed_pair watchdog_500ms\n")
        return len(payload)

    def read(self, count):
        result = bytes(self.incoming[:count])
        del self.incoming[:count]
        return result

    def close(self):
        self.closed = True


class SerialTests(unittest.TestCase):
    def test_pair_order_and_units(self):
        self.assertEqual(pair_line(1270, 1370), b"m 1270 1370\n")
        with self.assertRaises(ValueError):
            pair_line(1270.5, 1370)
        with self.assertRaises(ValueError):
            pair_line(True, 1370)

    def test_handshake_commands_and_close(self):
        link = SerialLink("fake", serial_factory=FakeSerial)
        link.send_targets(1500, 1200)
        self.assertIn(b"m 1500 1200\n", link.serial.writes)
        link.close()
        self.assertTrue(link.serial.closed)
        self.assertEqual(link.serial.writes[-1], b"x\n")

    def test_fragmented_lines_and_memory_bound(self):
        link = SerialLink("fake", serial_factory=FakeSerial)
        link.serial.incoming.extend(b"hello")
        self.assertEqual(link.read_lines(), [])
        link.serial.incoming.extend(b" world\n")
        self.assertEqual(link.read_lines(), ["hello world"])
        link.serial.incoming.extend(b"a" * 5000)
        link.read_lines()
        link.read_lines()
        self.assertLessEqual(len(link._receive), 4096)

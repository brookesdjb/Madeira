from pathlib import Path
import struct

from automation.generate_exit42 import executable, header


def test_committed_fixture_is_reproducible_executable_ELF():
    data = executable()
    eh = struct.unpack("<16sHHIQQQIHHHHHH", data[:64])
    ph = struct.unpack("<IIQQQQQQ", data[64:120])
    assert eh[0][:7] == b"\x7fELF\x02\x01\x01" and eh[1:3] == (2, 62)
    assert ph[0:3] == (1, 5, 0)  # PT_LOAD, readable/executable, file offset zero
    assert ph[5] == ph[6] == len(data)
    assert ph[3] <= eh[4] < ph[3] + ph[6]
    assert eh[4] - ph[3] == 120  # Entry points to code, after ELF headers
    path = Path(__file__).resolve().parents[2] / "app/Madeira/automation_exit42.h"
    assert path.read_text() == header()

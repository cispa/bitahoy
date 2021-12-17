import pytest

from watchdog.network.utils import p16, u16


def test_u16():
    # check endianness
    assert u16(b"\x00\x01") == 1
    assert u16(b"\x10\x00") == 4096
    # check size assertions
    with pytest.raises(Exception):
        u16(b"sss")


def test_p16():
    # check endianness
    assert p16(1) == b"\x00\x01"
    assert p16(4096) == b"\x10\x00"
    # check size assertions
    with pytest.raises(Exception):
        p16(-1)
    with pytest.raises(Exception):
        p16(65536)

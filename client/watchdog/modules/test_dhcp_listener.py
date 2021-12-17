import asyncio
from binascii import unhexlify

import pytest
from mockito import mock, unstub

from watchdog.modules.dhcp_listener import DHCPServer

captured_request = unhexlify(
    "01010600913702c6000000000000000000000000000000000000000"
    "0b283b9298fcb000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000000000000638253633501033d0701b28"
    "3b9298fcb3204c0a801783604c0a80101390205dc3c0f616e64726f"
    "69642d646863702d3131370b0103060f1a1c333a3b2b72ff00"
)

event = ""


@pytest.mark.asyncio
async def test_dhcp_server_packet_parsing(monkeypatch):
    global event

    def p(ev, **kwargs):
        global event
        print(ev)
        event = ev
        f = asyncio.Future()
        f.set_result(None)
        return f

    obj = mock({"name": "mocked_module", "put": p, "logger": mock({"info": print})})

    s = DHCPServer(obj)
    await s.handle_income_packet(captured_request, "")
    options = event.data
    try:
        assert "ip" in options
        assert options["ip"] is not None
        assert "requested_addr" in options
        assert options["requested_addr"] is not None
        assert 50 in options
    finally:
        unstub()

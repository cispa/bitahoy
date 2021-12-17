from bitahoy_sdk.addon.emulator.emulator import run_interceptor
from exampleinterceptor import dnsInterceptor
import asyncio


"""
This file is not really a test, but this file uses the sdk emulator to execute the addon in a similar way the client does. 

"""


if __name__ == "__main__":
    
    p1 = b"\x38\x10\xd5\x1d\xb8\x64\xb4\x2e\x99\xf6\xa0\x01\x08\x00\x45\x00\x00\x3f\x7c\xdb\x00\x00\x80\x11\x00\x00\xc0\xa8\xb2\x1e\xc0\xa8\xb2\x01\xe1\xb7\x00\x35\x00\x2b\xe5\xad\x71\x08\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x0d\x73\x74\x61\x63\x6b\x6f\x76\x65\x72\x66\x6c\x6f\x77\x03\x63\x6f\x6d\x00\x00\x01\x00\x01"

    async def generate_packets(send):
        for i in range(50):
            await send(p1)
            await asyncio.sleep(1)



    run_interceptor(dnsInterceptor, generate_packets)
from bitahoy_sdk.addon.scanner import DeviceScanner 
import asyncio

"""
Some useless module to use as an example.
"""

class NopScanner(DeviceScanner):
    
    async def scan(self, device, options):
        await self.logger.info("Hello world!")
        await asyncio.sleep(1)
        await self.report_result(device.result("Some vuln/port", "Open port at ip {}".format(device.ip)))
        await asyncio.sleep(1)
        await self.report_result(device.result("Other vuln", "why not a second result? " + 80*"A", link="https://www.youtube.com/watch?v=dQw4w9WgXcQ"))


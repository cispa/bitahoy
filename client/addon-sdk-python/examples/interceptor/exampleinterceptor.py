
from bitahoy_sdk.addon.interceptor import InterceptorAddon
from bitahoy_sdk.filter import TrafficFilter, Ethernet, IPv4, UDP
import asyncio

"""
Some useless addon to use as an example.
"""

class dnsInterceptor(InterceptorAddon):

    async def main(self):
        self.requests = 0
        self.responses = 0
        filter_dns_requests = TrafficFilter(Ethernet.assert_ipv4 & IPv4.assert_udp & (UDP.src_port == 53))
        filter_dns_responses = TrafficFilter(Ethernet.assert_ipv4 & IPv4.assert_udp & (UDP.dst_port == 53))
        rf1 = await self.API.register_listener(self.on_request, filter_dns_requests, exclusive=False, avg_delay=20)
        rf2 = await self.API.register_listener(self.on_response, filter_dns_responses, exclusive=False, avg_delay=20)
        try:
            while True:
                await asyncio.sleep(5)
                await self.API.logger.info("devices:\n", "\n".join([device.debug() for device in await self.API.devices.get_devices()]))
                await self.API.logger.info("dns requests:", self.requests)
                await self.API.logger.info("dns responses:", self.responses)
                await self.API.logger.info("blocking dns traffic...")
                rf3 = await self.API.block_traffic(TrafficFilter(Ethernet.assert_ipv4 & IPv4.assert_udp & ((UDP.dst_port == 53) | (UDP.src_port == 53))))
                await asyncio.sleep(5)
                await self.API.logger.info("dns requests:", self.requests)
                await self.API.logger.info("dns responses:", self.responses)
                await self.API.logger.info("unblocking dns traffic...")
                await rf3.remove()
        finally:
            await rf1.remove()
            await rf2.remove()

    async def on_request(self, packet):
        self.requests += 1
        await self.API.logger.info("Received dns request")

    async def on_response(self, packet):
        self.responses += 1
        await self.API.logger.info("Received dns response")

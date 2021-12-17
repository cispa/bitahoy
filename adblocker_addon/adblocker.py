
from bitahoy_sdk.addon.interceptor import InterceptorAddon
from bitahoy_sdk.filter import TrafficFilter, Ethernet, IPv4, UDP
import asyncio
from scapy.all import Ether, DNS, raw
from urllib3.util import connection
import requests
import re
import time
import aiohttp



class Blacklist:

    def __init__(self, name, url, regex, group=1):
        self.regex = re.compile(regex)
        self.url = url
        self.group = group
        self.name = name

    def download(self):
        return requests.get(self.url).text

    def add(self, blacklist):
        data = self.download()
        added = 0
        for m in self.regex.finditer(data):
            key = m.group(self.group) +"."
            blacklist[key] = self.name
            added += 1
        return blacklist, added
    

HOSTS_REGEX = "(^|\n)\d+.\d+.\d+.\d+\s+([^\n\s]+)"

class DoH():

    def __init__(self):
        self.session = requests.session()
        self.async_session = aiohttp.ClientSession()
        _orig_create_connection = connection.create_connection
        self.hostname = "dns.digitale-gesellschaft.ch"
        self.url = f"https://{self.hostname}/dns-query"
        self.ip = "185.95.218.42"


        def patched_create_connection(address, *args, **kwargs):
            host, port = address
            if host == self.hostname:
                host = self.ip
            return _orig_create_connection((host, port), *args, **kwargs)

        connection.create_connection = patched_create_connection
        self.session.get(self.url)

    def sync_tunnel(self, query):
        return self.session.post(self.url, data=query, headers={"Content-Type": "application/dns-message", "Accept": "application/dns-message"}).content

    async def tunnel(self, query):
        async with self.async_session.post(self.url, data=query, headers={"Content-Type": "application/dns-message", "Accept": "application/dns-message"}) as resp:
            return await resp.read()

class DNSResolver(asyncio.DatagramProtocol):

    def __init__(self, interceptor):
        self.data_queue = asyncio.Queue(loop=asyncio.get_event_loop())
        asyncio.ensure_future(self.respond())
        self.interceptor = interceptor

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        asyncio.ensure_future(self.handler(data, addr), loop=asyncio.get_event_loop())

    async def respond(self):
        while True:
            data, addr = await self.data_queue.get()
            response = await self.interceptor.process_request(data, "DNS-Resolver", addr[0])
            self.transport.sendto(raw(response), addr)

    async def handler(self, data, caller):
        await self.data_queue.put((data, caller))



class adblockerInterceptor(InterceptorAddon):

    
    async def update_blacklist(self):

        self.blacklist = {}
        sources = [
            #Blacklist("Gambling", "http://sbc.io/hosts/alternates/gambling/hosts", HOSTS_REGEX, 2),
            #Blacklist("Facebook", "https://raw.githubusercontent.com/anudeepND/blacklist/master/facebook.txt", HOSTS_REGEX, 2),
            Blacklist("Malware", "http://sbc.io/hosts/hosts", HOSTS_REGEX, 2),
            #Blacklist("Porn", "http://sbc.io/hosts/alternates/porn/hosts", HOSTS_REGEX, 2),
            #Blacklist("Advertisement", "https://hosts.anudeep.me/mirror/adservers.txt", HOSTS_REGEX, 2),
            Blacklist("Advertisement", "https://adaway.org/hosts.txt", HOSTS_REGEX, 2),
            Blacklist("Tracker", "https://v.firebog.net/hosts/Easyprivacy.txt", "([^\n]+)", 1),
            #Blacklist("Tracker", "https://hostfiles.frogeye.fr/firstparty-trackers-hosts.txt", HOSTS_REGEX, 2),
        ]
        oldlen = len(self.blacklist)
        for blacklist in sources:
            await self.API.logger.info("Downloading blacklist '{}'... ({})".format(blacklist.name, blacklist.url))
            self.blacklist, entries = blacklist.add(self.blacklist)
            newlen = len(self.blacklist)
            await self.API.logger.info("Downloaded blacklist '{}'. {} entries, {} new".format(blacklist.name, entries, newlen-oldlen))
            oldlen = newlen

        await self.API.send_notifications([{
                        "level": 30,
                        "time": time.time(),
                        "sender": "Adblocker",
                        "message": f"Updated blacklists. {entries} Entries.",
        }])
        await self.API.logger.info("Updated blacklist. {} entries".format(oldlen))

    def is_blacklisted(self, domain):
        try:
            d = domain.decode()
        except:
            return "invalid domain"
        try:
            return self.blacklist[d]
        except KeyError:
            return None

    async def main(self):
        self.doh = DoH()
        self.requests = 0
        self.blocked = 0
        self.resolver = DNSResolver(self)
        self.stats = {}
        await self.API.send_notifications([{
                        "level": 30,
                        "time": time.time(),
                        "sender": "Adblocker",
                        "message": "Started",
        }])
        filter_dns_requests = TrafficFilter(Ethernet.assert_ipv4 & IPv4.assert_udp & (UDP.dst_port == 53))
        filter_dns_responses = TrafficFilter(Ethernet.assert_ipv4 & IPv4.assert_udp & (UDP.src_port == 53))
        rf1 = await self.API.register_listener(self.on_request, filter_dns_requests, exclusive=True, avg_delay=20)
        rf2 = await self.API.register_listener(self.on_response, filter_dns_responses, exclusive=False, avg_delay=20)
        try:
            await asyncio.gather(self.update_loop(), self.run_dns_server(), self.statistics_loop())
        finally:
            await rf1.remove()

    async def update_loop(self):
        while True:
            await self.API.logger.info("Updating blacklists")
            await self.update_blacklist()
            await asyncio.sleep(3600)


    async def statistics_loop(self):
        while True:
            await self.API.logger.info("Updating stats")
            stats = self.stats
            self.stats = {}
            for key, value in stats.items():
                report = ""
                total = 0
                for reason, number in value.items():
                    report += f"{reason}: {number}\n"
                    total += number
                if key == "0.0.0.0":
                    await self.API.send_notifications([{
                                    "level": 20,
                                    "time": time.time(),
                                    "sender": "Privacy",
                                    "message": f"Bitahoy blocked {total} ads and trackers in the past 5 minutes.\n{report}",
                    }])
                else:
                    await self.API.send_notifications([{
                                    "level": 20,
                                    "time": time.time(),
                                    "sender": "Privacy",
                                    "message": f"On device {key}, Bitahoy blocked {total} ads and trackers in the past 5 minutes.\n{report}",
                    }])
            await asyncio.sleep(60*5)

    async def add_to_stats(self, src_ip, reason, number=1):
        if src_ip not in self.stats:
            self.stats[src_ip] = {reason: number}
        else:
            d = self.stats[src_ip]
            if reason in d:
                d[reason] += number
            else:
                d[reason] = number
            self.stats[src_ip] = d

    async def process_request(self, dns, traffic_source, src_ip):
        p2 = await self.doh.tunnel(dns)
        response = DNS(p2)
        newan = []
        loop = asyncio.get_event_loop()
        for i in range(response.ancount):
                dnsrr = response.an[i]
                blacklist_reason = self.is_blacklisted(dnsrr.rrname)
                if blacklist_reason:
                    if dnsrr.type == 5:
                        key = dnsrr.rdata.decode()
                        #if key not in self.blacklist:
                        #    self.blacklist[key] = f"{blacklist_reason} ({dnsrr.rrname.decode()}) -> {dnsrr.rdata.decode()}"
                        rdata = dnsrr.rdata
                    elif dnsrr.type == 1:
                        rdata = "0.0.0.0"
                    elif dnsrr.type == 28:
                        rdata = "::"
                    else:
                        rdata = ""
                    self.blocked += 1
                    await self.add_to_stats(src_ip, blacklist_reason.split(' (', 1)[0])
                    await self.add_to_stats("0.0.0.0", blacklist_reason.split(' (', 1)[0])
                    
                    loop.create_task(self.API.send_notifications([{
                                    "level": 50,
                                    "time": time.time(),
                                    "sender": "Adblocker",
                                    "message": f"blocked ad #{self.blocked}: {dnsrr.rrname} # Reason: {blacklist_reason.split(' (', 1)[0]}",
                    }]))
                    loop.create_task(self.API.logger.warn(f"{traffic_source} ({src_ip}) blocked ad #{self.blocked}: {dnsrr.rrname} -({dnsrr.type})-> {dnsrr.rdata} # Reason: {blacklist_reason}"))
                    dnsrr.rdata = rdata
                else:
                    #await self.API.logger.verbose("benign dns request: ", dnsrr.rrname)
                    pass
                newan += [dnsrr]
        if response.ancount:
            response.an = newan
        return response

    async def on_request(self, packet_tuple):
        packet, _ = packet_tuple
        self.requests += 1
        p = Ether(packet)

        response = await self.process_request(raw(p["DNS"]), "interceptor", p["IP"].src)

        p.getlayer(2).remove_payload()
        p["IP"].src, p["IP"].dst, p["Ether"].src, p["Ether"].dst, p["UDP"].sport, p["UDP"].dport, p["IP"].len, p["UDP"].len = p["IP"].dst, p["IP"].src, p["Ether"].dst, p["Ether"].src, p["UDP"].dport, p["UDP"].sport, None, None
        p = p / response

        await self.API.send_packets([raw(p)])

    async def on_response(self, packet_tuple):
        packet, _ = packet_tuple
        await self.API.send_packets([packet])

    async def run_dns_server(self):
        loop = asyncio.get_event_loop()
        try:
            await loop.create_datagram_endpoint(lambda: self.resolver, local_addr=('0.0.0.0', 53))
        except IOError as e:
            await self.API.logger.warn("Failed to start DNS server:", e)


# DeviceIdentifier
This repo includes a python package to crawl information of the devices in the client's network.
We currently support MDNS, SSDP and NETBIOS. A dict of the form `{ip:{'name':name, 'model':model, 'manufacturer': manufacturer}}` is produced.
There may also be the `mdns_raw` and `ssdp_raw` keys to allow evaluating the parsing capabilities if the `add_raw_to_output` flag is set.
Since netbios does not support broadcasting a list of devices should be passed to the scan function.
Here is an example usage:
```python
import asyncio

from device_identifier import NetDiscoScanner
from bitahoy_sdk.network_utils import IPv4

loop = asyncio.get_event_loop()
devices = loop.run_until_complete(NetDiscoScanner().scan([IPv4('192.168.1.104')]))
for ip, info in devices.items():
    print("Parsed result for IP {}: found a device called {} with the model-name {} manufactured by {}".format(ip,
                                                                                                               info['name'],
                                                                                                               info['model'],
                                                                                                               info['manufacturer']))
```
The above script will return all devices and *not* just *192.168.1.104*.
This argument just allows an optional list for specific targets of non-boradcasting protocols like netbios.

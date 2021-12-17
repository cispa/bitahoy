import asyncio
from dataclasses import dataclass
from typing import List, Union


@dataclass
class Event:
    to: Union[str, List[str]]
    sender: str
    type: int  # noqa: A003, VNE003
    data: Union[dict, list]


class EventListener:  # noqa: SIM119
    def __init__(self, queue, logger):
        self.events_in_queue = queue
        self.on_event = {}
        self.logger = logger
        pass

    async def listen(self):
        loop = asyncio.get_event_loop()
        async with self.events_in_queue.open() as get_event:
            while True:
                event = await get_event()
                if event.type in self.on_event:
                    loop.create_task(self.on_event[event.type](event))
                else:
                    await self.logger.warn(
                        "Unhandled event: sender='{}', to='{}', type='{}', data='{}'".format(event.sender, event.to, event.type, event.data)
                    )


#  Different types of Events
UNKNOWN = None
NODECONFIG = 1
PACKETSTATS = 2
LOG = 4
CLOUDLOGGING = 5
ML = 6
ADDONLIST = 7
START_MODULE = 8
STOP_MODULE = 9
WHITELIST = 10
DEVICEIDDATA_DHCP = 11
DEVICEIDDATA_NETDISCO = 12
ADDONFILTERS = 13
ADDONQUEUE = 14
DEVICEID_DEVICELIST = 15
DEVICEID_NEWDEVICE = 16
INTERCEPTION_DEVICELIST = 17
ADDONCONFIG = 18
NOTIFICATION = 19

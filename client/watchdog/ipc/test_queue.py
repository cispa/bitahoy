import asyncio
import os
import signal
import time
from dataclasses import dataclass
from multiprocessing import Barrier, Process, Value

import pytest

from watchdog.ipc.queue import QueueReceiver, ZMQueueManager


@pytest.fixture
def queues():
    manager = ZMQueueManager("pytest - Carlos Matos")
    queue = manager.__enter__()
    sender = queue.sender()
    tmp_sender = sender.open()
    send = tmp_sender.__enter__()
    receiver = queue.receiver()
    yield manager, queue, sender, send, receiver
    tmp_sender.__exit__(0, 0, 0)
    manager.__exit__(0, 0, 0)


@dataclass
class AsyncEventSucker:
    def __init__(self, recv_queue: QueueReceiver, event_counter):
        self.q: QueueReceiver = recv_queue
        self.c = event_counter

    async def run(self):
        async with self.q.open() as get_event:
            while True:
                await get_event()
                with self.c.get_lock():
                    self.c.value += 1


class EventSucker:
    def __init__(self, recv_queue: QueueReceiver, event_counter):
        self.q: QueueReceiver = recv_queue
        self.c = event_counter

    def run(self):
        with self.q.open() as get_event:
            while True:
                get_event()
                with self.c.get_lock():
                    self.c.value += 1


class BernieSender:
    def __init__(self, sender, to_send: list, barrier):
        self.s = sender
        self.to_send = to_send
        self.barrier = barrier

    def run(self):
        self.barrier.wait()
        with self.s.open() as put:
            for elem in self.to_send:
                put(elem)


class SingleReceiver:
    def __init__(self, recv_queue, counter, barrier):
        self.q = recv_queue
        self.c = counter
        self.barrier = barrier

    def run(self):
        self.barrier.wait()
        with self.q.open() as get_event:
            get_event()
            with self.c.get_lock():
                self.c.value += 1


class CountingEventSucker:
    """Feed it increasing ints. If this is not the case no more events are drained"""

    def __init__(self, recv_queue: QueueReceiver, event_counter):
        self.q: QueueReceiver = recv_queue
        self.c = event_counter

    def run(self):
        with self.q.open() as get_event:

            counter = 0
            while True:
                event = get_event()
                if event != counter:
                    break
                counter += 1
                with self.c.get_lock():
                    self.c.value += 1


def test_two_consecutively_sent_events_arrive_async(queues):
    _, _, sender, send, receiver = queues

    counter = Value("i", 0)

    def multiprocess(recv_queue, ctr):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        sucker = AsyncEventSucker(recv_queue, ctr)
        loop.run_until_complete(sucker.run())

    proc = Process(target=multiprocess, args=(receiver, counter))
    proc.start()
    send("HeyHeyHeyyyyyy")
    send("BITCONNNEEEEEEEEEEEEEEECT")
    time.sleep(0.5)
    try:
        with counter.get_lock():
            assert counter.value == 2
    finally:
        # TEARDOWM
        if proc.is_alive():
            os.kill(proc.pid, signal.SIGKILL)


def test_three_consecutively_sent_events_arrive_sync(queues):
    _, _, sender, send, receiver = queues

    counter = Value("i", 0)

    def multiprocess(recv_queue, ctr):
        sucker = EventSucker(recv_queue, ctr)
        sucker.run()

    proc = Process(target=multiprocess, args=(receiver, counter))
    proc.start()
    send("HeyHeyHeyyyyyy")
    send("middle whatsupwhatsupwhatsup")
    send("BITCONNNEEEEEEEEEEEEEEECT")
    time.sleep(0.5)
    try:
        with counter.get_lock():
            assert counter.value == 3
    finally:
        # TEARDOWM
        if proc.is_alive():
            os.kill(proc.pid, signal.SIGKILL)


@pytest.mark.asyncio
async def test_three_consecutively_asynchronously_sent_events_arrive_async():
    manager = ZMQueueManager("pytest - Carlos Matos")
    queue = manager.__enter__()
    sender = queue.sender()
    receiver = queue.receiver()

    counter = Value("i", 0)

    def multiprocess(recv_queue, ctr):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        sucker = AsyncEventSucker(recv_queue, ctr)
        loop.run_until_complete(sucker.run())

    proc = Process(target=multiprocess, args=(receiver, counter))
    proc.start()
    async with sender.open() as put:
        await put("ASYNC HeyHeyHeyyyyyy")
        await put("ASYNC Whats up Whats up Whats up")
        await put("ASYNC BITCONNNEEEEEEEEEEEEEEECT")
    time.sleep(0.3)
    try:
        with counter.get_lock():
            assert counter.value == 3
    finally:
        # TEARDOWM
        if proc.is_alive():
            os.kill(proc.pid, signal.SIGKILL)
        manager.__exit__(0, 0, 0)


# @pytest.mark.skip(reason="not working rn and teardown after timeout does not work")
@pytest.mark.timeout(10)
@pytest.mark.performancetest
def test_order_preservance_and_dynamic_capacity_large(queues):
    _, _, _, send, receiver = queues
    ELEMENTS = 100_000
    counter = Value("i", 0)

    def multiprocess(recv_queue, ctr):
        sucker = CountingEventSucker(recv_queue, ctr)
        sucker.run()

    for i in range(ELEMENTS):
        send(i)

    proc = Process(target=multiprocess, args=(receiver, counter))
    proc.start()

    time.sleep(7)

    try:
        with counter.get_lock():
            assert ELEMENTS == counter.value
    finally:
        # TEARDOWM
        if proc.is_alive():
            os.kill(proc.pid, signal.SIGKILL)


def test_multiple_sender_and_receivers(queues):
    manager, queue, sender, send, receiver = queues
    SENDERS = RECEIVERS = 5

    sender_barrier = Barrier(SENDERS)
    receiver_barrier = Barrier(RECEIVERS)

    def mp_sender(sender, to_send, barrier):
        sender = BernieSender(sender, to_send, barrier)
        sender.run()

    def mp_receiver(receiver, counter, barrier):
        receiver = SingleReceiver(receiver, counter, barrier)
        receiver.run()

    counter = Value("i", 0)

    senders = [Process(target=mp_sender, args=(queue.sender(), [i], sender_barrier)) for i in range(SENDERS)]
    receivers = [Process(target=mp_receiver, args=(queue.receiver(), counter, receiver_barrier)) for _ in range(RECEIVERS)]

    [r.start() for r in receivers]
    [s.start() for s in senders]

    time.sleep(0.2)
    with counter.get_lock():
        assert counter.value == SENDERS

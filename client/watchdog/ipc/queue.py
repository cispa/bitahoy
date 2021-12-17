import asyncio
import collections
import os
import random
import signal
import socket
import time
from contextlib import suppress
from io import UnsupportedOperation

import watchdog.core.processes
from watchdog.ipc.serializers import PickleSerializer, Serializer


class DeserializationError(Exception):
    __slots__ = "exception", "msg"

    def __init__(self, exception, msg):
        self.exception = exception
        self.msg = msg


class QueueClosed(Exception):
    pass


class BaseQueue:
    def __init__(self, name, no_loss=False):
        self.uds = "/tmp/arpjetqueue_" + str(time.time()) + str(random.randint(10000, 100000))  # nosec
        with suppress(FileNotFoundError):
            os.unlink(self.uds)
        self.name = name

    def close(self):
        with suppress(FileNotFoundError):
            os.unlink(self.uds)


class QueueContext:
    def __init__(self, bq, qcargs, generator, async_generator):
        self.bq = bq
        self._qc = QueueClient(*qcargs)
        self.generator = generator
        self.async_generator = async_generator

    def __enter__(self):
        assert not self._qc.socket
        self._qc.connect_sync(self.bq.uds)
        return self.generator(self._qc)

    async def __aenter__(self):
        assert not self._qc.socket
        await self._qc.connect(self.bq.uds)
        return self.async_generator(self._qc)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._qc.disconnect_sync()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._qc.disconnect()


class QueueSender:
    def __init__(self, bq: BaseQueue, serializer=PickleSerializer):
        self.bq = bq
        self.qcargs = (b"s", serializer)

    def open(self):  # noqa: A003
        def do(qc):
            def put(data, timeout=-1):
                if timeout != -1:
                    raise UnsupportedOperation("Timeout is not supported for sync queues")
                else:
                    return qc.put_sync(data)

            return put

        def doasync(qc):
            async def put(data, timeout=-1):
                if timeout != -1:
                    return asyncio.wait_for(await qc.put(data), timeout)
                else:
                    return await qc.put(data)

            return put

        return QueueContext(self.bq, self.qcargs, do, doasync)


class QueueReceiver:
    def __init__(self, bq: BaseQueue, serializer=PickleSerializer):
        self.bq = bq
        self.qcargs = (b"r", serializer)

    def open(self):  # noqa: A003
        def do(qc):
            get_gen = qc.get_sync()

            def get(timeout=-1):
                if timeout != -1:
                    raise UnsupportedOperation("Timeout is not supported for sync queues")
                else:
                    return next(get_gen)

            return get

        def doasync(qc):
            get_gen = qc.get()

            async def get(timeout=-1):
                if timeout != -1:
                    return asyncio.wait_for(await get_gen.__anext__(), timeout)
                else:
                    return await get_gen.__anext__()

            return get

        return QueueContext(self.bq, self.qcargs, do, doasync)


class QueueClient:
    def __init__(self, mode, serializer: Serializer):
        self.mode = mode
        self.serializer = serializer
        self.need_data = True
        self.socket = None
        self.loop = None
        self.lock = asyncio.Lock()
        self.buf: bytes = b""

    async def connect(self, uds, timeout=0.5):
        assert self.socket is None
        self.uds = uds
        self.loop = asyncio.get_event_loop()
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.setblocking(False)
        while not os.path.exists(uds) and timeout > 0:
            await asyncio.sleep(0.01)
            timeout - 0.01
        try:
            await self.loop.sock_connect(self.socket, uds)
        except ConnectionRefusedError:
            await asyncio.sleep(0.01)
            await self.loop.sock_connect(self.socket, uds)

        await self.loop.sock_sendall(self.socket, self.mode)
        self.need_data = True

    def connect_sync(self, uds, timeout=0.5):
        assert self.socket is None
        self.uds = uds
        self.loop = None
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.setblocking(True)
        while not os.path.exists(uds) and timeout > 0:
            time.sleep(0.01)
            timeout - 0.01
        self.socket.connect(uds)
        self.socket.sendall(self.mode)
        self.need_data = True

    async def get(self):
        assert self.socket is not None
        assert self.loop is not None
        assert self.mode == b"r"
        async with self.lock:
            while True:
                try:
                    data = await self.loop.sock_recv(self.socket, 16384)
                except BrokenPipeError as e:
                    raise QueueClosed(e)
                if data == b"":
                    raise QueueClosed("connection closed")
                self.buf += data
                while self.buf:
                    inp = self.buf
                    packet, self.buf = Serializer.parse(self.buf)
                    if packet is not None:
                        self.need_data = False
                        try:
                            yield self.serializer.deserialize(packet)
                        except Exception as e:
                            with open("./failed_payload" + str(time.time()) + "_inp.txt", "wb") as f:
                                f.write(inp)
                                f.flush()
                            with open("./failed_payload" + str(time.time()) + "_buf.txt", "wb") as f:
                                f.write(self.buf)
                                f.flush()
                            raise e

                    else:
                        break

    def get_sync(self):
        assert self.socket is not None
        assert self.loop is None
        assert self.mode == b"r"
        while True:
            try:
                data = self.socket.recv(16384)
            except BrokenPipeError as e:
                raise QueueClosed(e)
            if data == b"":
                raise QueueClosed("connection closed")
            self.buf += data
            while self.buf:
                packet, self.buf = Serializer.parse(self.buf)
                if packet is not None:
                    self.need_data = False
                    yield self.serializer.deserialize(packet)
                else:
                    break

    async def put(self, obj):
        assert self.socket is not None
        if self.loop is None:
            self.loop = asyncio.get_event_loop()
        async with self.lock:
            assert self.mode == b"s"
            data = self.serializer.serialize(obj)
            try:
                await self.loop.sock_sendall(self.socket, data)
            except BrokenPipeError as e:
                raise QueueClosed(e)

    def put_sync(self, obj):
        assert self.socket is not None
        assert self.mode == b"s"
        data = self.serializer.serialize(obj)
        try:
            self.socket.sendall(data)
        except BrokenPipeError as e:
            raise QueueClosed(e)

    async def disconnect(self):
        self.disconnect_sync()

    def disconnect_sync(self):
        if self.socket is not None:
            self.socket.close()
        self.socket = None
        self.loop = None


class QueueServer:  # noqa: SIM119
    def __init__(self, debug):
        self.to_send = collections.deque()
        self.debug = debug

    async def start(self, uds):
        self.sem = asyncio.Semaphore(0)
        self.loop = asyncio.get_event_loop()
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.setblocking(False)
        self.socket.bind(uds)
        self.socket.listen(10)
        while True:
            sock, addr = await self.loop.sock_accept(self.socket)
            asyncio.create_task(self._handshake(sock))

    async def _handshake(self, socket):
        try:
            mode = await self.loop.sock_recv(socket, 1)
            if self.debug:
                print("connected " + mode.decode())  # noqa: T001
            if mode == b"s":
                await self._sender(socket)
            elif mode == b"r":
                await self._receiver(socket)
        except BrokenPipeError:
            pass
        finally:
            if self.debug and mode:
                print("disconnected " + mode.decode())  # noqa: T001
            socket.close()

    async def send_packet(self, packet):
        self.to_send.append(packet)
        self.sem.release()

    async def _receiver(self, socket):
        while True:
            await self.sem.acquire()
            packet = self.to_send.popleft()
            try:
                await self.loop.sock_sendall(socket, packet)
                await asyncio.sleep(0)  # load balancing
                packet = None
            except BrokenPipeError:
                return
            finally:
                if packet:
                    self.to_send.appendleft(packet)
                    self.sem.release()

    async def _sender(self, socket):
        buf = b""
        while True:
            data = await self.loop.sock_recv(socket, 16384)
            if data == b"":
                return
            buf += data
            while buf:
                packet, buf = Serializer.parse(buf)
                if packet:
                    await self.send_packet(packet)
                else:
                    break


class ZMQueue:
    """
    Base class for Queues.
    Kill ZMQueues by sending a SIGKILL or calling __exit__()
    """

    def __init__(self, name, debug):
        self.debug = debug
        self.bq = BaseQueue(name)

        def run():
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            try:
                qs = QueueServer(debug)
                asyncio.run(qs.start(self.bq.uds))
            except KeyboardInterrupt:
                return
            finally:
                self.bq.close()

        self.process = watchdog.core.processes.Process(target=run, name="queue-" + name)
        self.process.start()

    def receiver(self) -> QueueReceiver:
        if self.debug:
            import traceback

            traceback.print_stack()
        return QueueReceiver(self.bq)

    def sender(self) -> QueueSender:
        res = QueueSender(self.bq)
        return res

    def close(self):
        self.bq.close()
        if self.process and self.process.is_alive():
            os.kill(self.process.pid, signal.SIGKILL)


class ZMQueueManager:
    def __init__(self, name, debug=False):
        self.queue: ZMQueue = None
        self.name: str = name
        self.debug = debug

    def __enter__(self):
        self.queue = ZMQueue(self.name, self.debug)
        return self.queue

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.queue.close()


class MultiQueueManager:
    def __init__(self, name):
        self.queue: ZMQueue = None
        self.name: str = name

    def __enter__(self):
        self.queue = ZMQueue(self.name)
        return self.queue

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.queue.close()


def script_main():
    queue = ZMQueue("x")

    with queue.sender() as put:
        put("Hello world!")
    with queue.receiver():
        pass
    with queue.receiver() as get:
        print(get(True))  # noqa: T001

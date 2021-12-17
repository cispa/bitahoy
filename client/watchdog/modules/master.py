import asyncio
import contextlib
import multiprocessing
import os
import signal
import time
import traceback
from typing import Dict, List, Type, Union

import watchdog.core.processes
import watchdog.modules.addon_manager
import watchdog.modules.arp_listener
import watchdog.modules.arp_probe
import watchdog.modules.bridge
import watchdog.modules.deviceid
import watchdog.modules.devicescanner
import watchdog.modules.dhcp_listener
import watchdog.modules.interceptor
import watchdog.modules.logger
import watchdog.modules.spoofer
from watchdog.core.config import Config
from watchdog.core.modules import Module
from watchdog.core.processes import set_proc_name
from watchdog.ipc.event import ADDONQUEUE
from watchdog.ipc.queue import (
    QueueClosed,
    QueueReceiver,
    QueueSender,
    ZMQueue,
    ZMQueueManager,
)


class Worker:
    """Abstraction for modules
    The worker class is used to populate and start a module.
    A worker should be killed by sending a SIGINT and calling .kill() afterwards
    """

    process = None
    name = None
    queue = None

    def __init__(
        self,
        module: Type[Module],
        queues: Dict[str, Union[QueueSender, QueueReceiver]],
        name: str,
        logger_queue: QueueSender,
        master_queue: ZMQueue,
    ):
        async def do(self):
            self.module = module
            self.name = name
            self.queue_manager = ZMQueueManager("worker_queue (%s)" % (name,))
            self.queue = self.queue_manager.__enter__()
            self._sender = self.queue.sender().open()
            self.send = await self._sender.__aenter__()
            logger = watchdog.core.logging.Logger(logger_queue, name)

            def starter(*args, **kwargs):

                """Entry point for new module process. This function is basically the wrapper function of each module"""
                logger = kwargs["logger"]
                module_instance = None

                def terminate():
                    """SIGINT is passed to the child processes. Hence we terminate here by running the on_terminate
                    and breaking the restart loop"""
                    signal.signal(signal.SIGINT, signal.SIG_IGN)
                    task: asyncio.Task = loop.create_task(module_instance.on_terminate())
                    loop.run_until_complete(task)

                while module_instance is None or module_instance.restart_on_error:
                    logger.info("starting module", kwargs["name"])
                    try:
                        if kwargs["name"] == "logger":
                            signal.signal(signal.SIGINT, signal.SIG_IGN)
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            kwargs["loop"] = loop
                            module_instance = self.module(*args, **kwargs)
                            module_instance.restart_on_error = True
                            loop.run_until_complete(module_instance.run())
                        else:
                            with contextlib.redirect_stdout(logger.get_file()), contextlib.redirect_stderr(logger.get_file(logger.ERROR)):
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                kwargs["loop"] = loop
                                module_instance = self.module(*args, **kwargs)
                                module_instance.restart_on_error = True
                                loop.run_until_complete(module_instance.run())
                    except KeyboardInterrupt:
                        terminate()
                        break
                    except Exception:
                        try:
                            try:
                                logger.error(traceback.format_exc())
                            except QueueClosed:
                                traceback.print_exc()
                            time.sleep(3)
                        except KeyboardInterrupt:  # Catch SIGINT during sleep
                            terminate()
                            break

            self.process: multiprocessing.Process = watchdog.core.processes.Process(
                target=starter,
                args=[],
                kwargs={
                    "name": name,
                    "logger": logger,
                    "events_in_queue": self.queue.receiver(),
                    "events_out_queue": master_queue.sender(),
                    "queues": queues,
                },
                name=name,
            )

        self.start = lambda: do(self)

    async def kill(self):
        """We only kill the queues since the actual shutdown is handled by the SIGINT catch in starter(*args, **kwargs)"""
        await self._sender.__aexit__(0, 0, 0)
        self.queue_manager.__exit__(0, 0, 0)

    def __bool__(self):
        """True if the process is still alive"""
        return self.process.is_alive()

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return f"Worker(module={self.module}, name={self.name})"


class Master:
    def __init__(self):
        self.workers: List[Worker] = []
        self.lookup_worker: Dict[Worker] = {}

        self.master_queue: ZMQueue = None
        self.packets_queue: ZMQueue = None
        self.logger_queue: ZMQueue = None
        self.packet_out_queue: ZMQueue = None
        self.packets_out_queues = []
        self.WORKERS = multiprocessing.cpu_count()
        self.RECEIVERS = 4
        assert self.RECEIVERS in [2 ** i for i in range(1, 8)]
        self.SENDERS_PER_WORKER = 2
        self.processors = []
        self.senders = []
        self.addons = {}
        self.config = Config()
        self.packets_out_queues_managers: List[ZMQueueManager] = []
        self.receivers: List[Worker] = []
        self.logger_module: Worker = None

    def workers_up(self):
        return all(self.workers)

    async def kill_workers(self):
        """Kill all the modules and give them time to finish up their work.

        This is achieved by the modules catching the KeyboardInterrupt from the terminal,
        which is Pythons way of invoking the SIGINT signal.
        Then each module runs its on_terminate method in order to do important work like restoring arp tables,
        cloud syncing etc. The logger process is killed at the end to enable logging for the other modules.

        :return: None
        """
        if self.config.get("master.kill_workers_on_shutdown", True):
            for worker in filter(lambda w: w.name != "logger", self.workers):
                await worker.kill()
            await asyncio.sleep(self.config.get("master.process_shutdown_timeout", 5))
            # If Processes are still alive kill them forcefully with SIGKILL instead of SIGINT
            for worker in filter(lambda w: w.name != "logger", self.workers):
                if worker.process.is_alive():
                    os.kill(worker.process.pid, signal.SIGKILL)
            await asyncio.sleep(0.5)
            # Check that all processes except the logger are actually dead
            killed = sum([not w.process.is_alive() for w in self.workers])
            assert killed == len(self.workers) - 1, f"Expected {len(self.workers) - 1} but was {killed}"
            logger = self.lookup_worker["logger"]
            await logger.kill()
            os.kill(logger.process.pid, signal.SIGKILL)
            await asyncio.sleep(0.2)
            # Check that all processes were terminated properly
            killed = sum([not w.process.is_alive() for w in self.workers])
            assert killed == len(self.workers), f"Expected {len(self.workers) - 1} but was {killed}"

    async def new_worker(self, run: Module, queues: Dict[str, Union[QueueSender, QueueReceiver]], name: str):
        worker = Worker(run, queues, name, self.logger_queue.sender(), self.master_queue)
        await worker.start()
        return worker

    async def start_workers(self):
        self.packets_out_queues_managers = []
        self.packets_out_queues = [q.__enter__() for q in self.packets_out_queues_managers]
        self.receivers = [
            await self.new_worker(
                watchdog.modules.interceptor.InterceptorModule,
                {"id": i, "total_ids": self.RECEIVERS},
                "interceptor_{}".format(i),
            )
            for i in range(self.RECEIVERS)
        ]
        self.logger_module = await self.new_worker(
            watchdog.modules.logger.LoggerModule, {"logger_queue": self.logger_queue.receiver()}, "logger"
        )
        self.workers = [
            await self.new_worker(watchdog.modules.bridge.Bridge, {}, "bridge"),
            await self.new_worker(watchdog.modules.spoofer.SpooferModule, {}, "spoofer"),
            await self.new_worker(watchdog.modules.arp_listener.ArpListenerModule, {}, "arp-listener"),
            await self.new_worker(watchdog.modules.dhcp_listener.DhcpListenerModule, {}, "dhcp-listener"),
            await self.new_worker(watchdog.modules.arp_probe.ArpProbeModule, {}, "arp-probe"),
            await self.new_worker(watchdog.modules.addon_manager.AddonManagerModule, {}, "addon_manager"),
            await self.new_worker(watchdog.modules.deviceid.DeviceIdModule, {}, "deviceid"),
            await self.new_worker(watchdog.modules.devicescanner.DeviceScannerModule, {}, "devicescanner"),
        ]
        self.workers += self.processors
        self.workers += self.receivers
        self.workers += self.senders
        self.workers += [self.logger_module]
        for worker in self.workers:
            self.lookup_worker[worker.name] = worker
            self.logger.verbose("starting {}".format(worker.name))
            worker.process.start()
            self.logger.debug("started {}".format(worker.name))

    async def route_addons_event(self, event, namefilter=None):
        for addon in list(self.addons):  # list because self.addons can change size in loop
            if namefilter is None or addon.startswith(namefilter):
                event.to = addon
                try:
                    await self.addons[addon][0](event)
                except QueueClosed:
                    del self.addons[addon]

    async def route_event_list(self, event, lst):
        for sender in lst:
            event.to = sender.name
            await sender.send(event)

    async def route_event(self, event):
        if type(event.to) != list:
            dsts = [event.to]
        else:
            dsts = event.to
        for dst in dsts:
            if dst == "master" and event.type == ADDONQUEUE:
                if event.sender in self.addons:
                    queue_context = self.addons[event.sender][1]
                    del self.addons[event.sender]
                    await queue_context.__aexit__(0, 0, 0)
                queue_context = event.data.open()
                self.addons[event.sender] = (await queue_context.__aenter__(), queue_context)
            elif dst in self.lookup_worker:
                event.to = dst
                await self.lookup_worker[dst].send(event)
            elif dst == "addons":
                await self.route_addons_event(event)
            elif dst.startswith("addon."):
                await self.route_addons_event(event, dst)
            elif dst == "proxy-receivers":
                await self.route_event_list(event, self.receivers)
            elif dst == "proxy-senders":
                await self.route_event_list(event, self.senders)
            elif dst == "proxy-processors":
                await self.route_event_list(event, self.processors)
            else:
                self.logger.error(
                    "unknown recipient {} (from {}, to {}, type {}, data {})".format(
                        repr(dst),
                        repr(event.sender),
                        repr(dsts),
                        repr(event.type),
                        repr(event.data),
                    )
                )

    async def runasync(self):
        with ZMQueueManager("master_queue") as self.master_queue, ZMQueueManager("packets_queue") as self.packets_queue, ZMQueueManager(
            "logger_queue"
        ) as self.logger_queue, ZMQueueManager("packet_out_queue") as self.packet_out_queue:
            self.logger = watchdog.core.logging.Logger(self.logger_queue.sender(), "modulemaster")
            await self.start_workers()
            try:
                set_proc_name(b"modulemaster")
                async with self.master_queue.receiver().open() as get:
                    while self.workers_up():
                        event = await get()
                        try:
                            await self.route_event(event)
                        except Exception as e:
                            print(  # noqa: T001
                                "latest event:",
                                event.to,
                                event.sender,
                                event.data,
                                flush=True,
                            )
                            raise e
            except KeyboardInterrupt:
                return
            finally:
                for queue in self.packets_out_queues_managers:
                    queue.__exit__(0, 0, 0)
                await self.kill_workers()

    def run(self):
        asyncio.run(self.runasync())

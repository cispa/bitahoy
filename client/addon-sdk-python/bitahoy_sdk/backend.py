import asyncio
import json
import sys

import websockets


class BackendWS:

    # class to interact with bitahoy websocket backends. its a bit more specific than websockets in general, but also includes some convenient wrappers such as request or register_callback
    def __init__(self, url, get_token, logger=None):
        # url: url of the websocket
        proto, url = url.split("://", 1)
        self.ws_url = (proto + "://").replace("https://", "wss://").replace("http://", "ws://") + url
        self.mgr = websockets.connect(self.ws_url)
        if callable(get_token) and not asyncio.iscoroutinefunction(get_token):
            async def get_token_wrapper():
                return get_token()

            self.get_token = get_token_wrapper
        else:
            self.get_token = get_token
        self.ws = None
        self.logger = logger
        self.__callbacks = {}
        self.__callback_list = {}
        self.lock = asyncio.Lock()
        self.authenticated = False

        # used for both timeout and keepalive_interval which derives from timeout
        self.auth_condition = asyncio.Condition()
        #  ws_condition and auth_condition are different because we send the auth action via ws before being authenticated
        self.ws_condition = asyncio.Condition()

        self.register_callback("auth", self.auth_callback)
        self.register_callback("keepalive", self.keepalive_callback)
        self.listen_task = asyncio.create_task(self.listen())
        self.keepalive_task = asyncio.create_task(self.keepalive())

        self.timeout = None
        # keepalive_interval is timeout - something, see calculate_keepalive_interval
        self.keepalive_interval = None

    def calculate_keepalive_interval(self, timeout):
        # timeout should be >= 5 but just to be safe
        if 0 < timeout <= 2:
            return timeout / 1.2
        # timeout between 2 and 6 seconds
        elif 2 < timeout <= 10:
            return timeout - 1
        elif 10 < timeout:
            return timeout - 2
        else:
            raise ValueError("timeout must be greater than 0")

    async def keepalive_callback(self, data):
        future = self.logger.verbose(data)
        if future:
            await future

    async def auth_callback(self, resp):
        if resp["success"] is True:
            async with self.auth_condition:
                self.authenticated = True
                if "timeout" in resp:
                    self.timeout = resp["timeout"]
                else:
                    self.timeout = 30
                    if self.logger:
                        future = self.logger.verbose("No timeout in auth response, defaulting to 30 seconds")
                        if future:
                            await future
                self.keepalive_interval = self.calculate_keepalive_interval(self.timeout)
                self.auth_condition.notify_all()
            if self.logger:
                future = self.logger.verbose("Authenticated!")
                if future:
                    await future

    async def authenticate(self):
        if self.ws is not None or not self.authenticated:
            async with self.lock:
                if not self.ws or not self.authenticated:
                    async with self.ws_condition:
                        self.ws = await self.mgr.__aenter__()
                        self.ws_condition.notify_all()
                    if self.get_token:
                        await self.send({"action": "auth", "token": await self.get_token()})
                        # if self.logger:
                        #     future = self.logger.verbose("Sent auth request to " + self.ws_url)
                        #     if future:
                        #         await future
        async with self.auth_condition:
            if not self.authenticated:
                await self.auth_condition.wait()

    async def __action(self, fun, retries):
        async with self.ws_condition:
            if self.ws is None:
                await self.ws_condition.wait()
        assert self.ws is not None
        try:
            return await fun()
        except Exception as e:
            if self.logger:
                future = self.logger.warn("exception ('{}')".format(e))
                if future:
                    await future
            if self.ws:
                await self.mgr.__aexit__(*sys.exc_info())
                async with self.ws_condition:
                    self.ws = None
                async with self.auth_condition:
                    self.authenticated = False
                    self.timeout = None
            x = []
            for key in self.__callback_list:
                x += list(self.__callback_list[key])
            # x += self.__callbacks.values()
            # self.__callbacks = {}
            self.__callback_list = {}
            for cb in x:
                await cb(None)
            if type(e) in [websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosedError,
                           websockets.exceptions.InvalidStatusCode]:
                if self.logger:
                    future = self.logger.verbose("connection lost ('{}'). reconnecting...".format(e))
                    if future:
                        await future
                if retries > 1:
                    return await self.__action(fun, retries - 1)
            else:
                raise e

    async def send(self, data: dict, retries=3):
        assert type(data) == dict
        assert "action" in data or "token" in data

        async def callback():
            return await self.ws.send(json.dumps(data))

        return await self.__action(callback, retries=retries)

    def register_callback(self, name, callback):
        if callable(callback) and not asyncio.iscoroutinefunction(callback):
            async def async_wrapper(data):
                return callback(data)

            self.__callbacks[name] = async_wrapper
        else:
            self.__callbacks[name] = callback

    async def request(self, data):
        assert type(data) == dict
        assert "action" in data
        fut = asyncio.get_running_loop().create_future()

        async def on_receive_callback(resp):
            if resp is None:
                # connection died, will be retried
                return
            fut.set_result(resp)

        async def send_callback():
            self.add_callback(data["action"], on_receive_callback)
            assert self.__callback_list[data["action"]]
            return await self.ws.send(json.dumps(data))

        await self.__action(send_callback, retries=3)
        return await fut

    def add_callback(self, name, callback):
        if name not in self.__callback_list:
            self.__callback_list[name] = []
        if callable(callback) and not asyncio.iscoroutinefunction(callback):
            async def async_wrapper(data):
                return callback(data)

            self.__callback_list[name] += [async_wrapper]
        else:
            self.__callback_list[name] += [callback]

    def pop_callback(self, name):
        if name not in self.__callback_list:
            return None
        callback = self.__callback_list[name][0]
        self.__callback_list[name] = self.__callback_list[name][1:]
        if len(self.__callback_list[name]) == 0:
            del self.__callback_list[name]
        return callback

    def unregister_callback(self, name):
        del self.__callbacks[name]

    async def listen(self, retries=3):
        async def _callback():
            return json.loads(await self.ws.recv())

        tasks = []
        while True:
            try:
                response = await self.__action(_callback, retries=retries)
                if response is None:
                    raise TimeoutError("failed to connect to backend")
                elif "action" not in response:
                    future = self.logger.warn("Server sent invalid data: {}".format(response))
                    if future:
                        await future
                elif response["action"] in self.__callback_list:
                    callback = self.pop_callback(response["action"])
                    await callback(response)
                elif response["action"] in self.__callbacks:
                    tasks += [asyncio.create_task(self.__callbacks[response["action"]](response))]
                elif "default" in self.__callbacks:
                    tasks += [asyncio.create_task(self.__callbacks["default"](response))]
                elif self.logger:
                    future = self.logger.warn(
                        "No callback registered for '{}'. ({})".format(response["action"], response))
                    if future:
                        await future
            finally:
                active_tasks = []
                for task in tasks:
                    if task.done():
                        await task
                    else:
                        active_tasks += [task]
                tasks = active_tasks

    async def sleep_wrapper(self):
        async with self.auth_condition:
            if self.timeout is None:
                await self.auth_condition.wait()
        assert self.timeout is not None
        await asyncio.sleep(self.keepalive_interval)

    async def keepalive_wrapper(self):
        async with self.auth_condition:
            if self.timeout is None:
                await self.auth_condition.wait()
        await self.send({"action": "keepalive"})

    async def keepalive(self):
        # send first keepalive only after sleep
        await self.sleep_wrapper()
        while True:
            await asyncio.gather(
                self.sleep_wrapper(),
                self.keepalive_wrapper(),
            )

    async def close(self):
        if self.ws:
            async with self.ws_condition:
                self.ws = None
            async with self.auth_condition:
                self.authenticated = False
                self.timeout = None
            self.listen_task.cancel()
            self.keepalive_task.cancel()
            await self.mgr.__aexit__(None, None, None)
            self.mgr = None

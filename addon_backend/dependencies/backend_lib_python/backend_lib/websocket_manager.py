import asyncio
import json
import os
import random
import socket

import time
from copy import deepcopy

from jsonschema import validate, ValidationError
from starlette.websockets import WebSocket, WebSocketState, WebSocketDisconnect
from slack import WebClient
import traceback

from backend_lib.auth import Auth, Expired, InvalidToken, VerificationFailed

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
slack = WebClient(SLACK_BOT_TOKEN)
TIMEOUT = 30


class UnknownActionException(Exception):

    def __init__(self, action):
        self.action = action
        super().__init__()


# single websocket to send and receive messages
class Websocket_Wrapper:

    def __init__(self, websocket: WebSocket, timeout):
        self.websocket = websocket
        # TODO: change for deployment
        self.timeout = timeout
        self.auth = Auth()

        self.wdcode = None
        self.uid = None
        self.wdcodes = None
        self.isUser = None

        # isUser? uid : code
        self.id = None

    async def authenticate(self):
        await self.websocket.accept()
        ws = self.websocket
        try:
            # First packet must contain the authentication, else we won't accept the connection!
            data = await asyncio.wait_for(ws.receive_json(),
                                          self.timeout)  # If after 5 seconds no packet, drop connection!
            assert data["action"] == "auth"
            token = data["token"]
            try:
                authenticatedClient = self.auth.verify(token)
            except Expired:
                await ws.send_json({"success": False, "action": "auth", "comment": "Expired"})
                await ws.close()
                return False
            except InvalidToken:
                await ws.send_json({"success": False, "action": "auth", "comment": "Invalid token"})
                await ws.close()
                return False
            except VerificationFailed as e:
                print("Invalid signature", e)
                await ws.send_json({"success": False, "action": "auth", "comment": "Invalid signature"})
                await ws.close()
                return False
            except Exception as err:
                print(err)
                await ws.send_json({"success": False, "action": "auth"})
                await ws.close()
                return False

            # Connection is now authenticated

            self.code = authenticatedClient.code
            self.uid = authenticatedClient.uid
            self.wdcodes = authenticatedClient.belongs  # Either a tuple of wdcodes owned by the uid or None
            self.isUser = authenticatedClient.isUser

            if not self.isUser:
                self.id = self.code
            else:
                self.id = self.uid

            await ws.send_json({"success": True, "action": "auth"})

            return True
        except (asyncio.TimeoutError, WebSocketDisconnect) as err:
            print("Client timed out during authentication!")
            await self.close()
            return False
        except Exception as err:
            tb = traceback.format_exc()
            print("Internal Server Error in callback: ", err)
            try:
                await ws.send_json({"success": False, "action": action, "comment": f"Error from endpoint: '{tb}'"})
            except:
                #Connection is dead!
                pass
            #Now post to slack
            try:
                slack.chat_postMessage(channel='#stacktraces', text="Exception in websocket_manager!+\n"+tb)
            except Exception as err:
                print("Could not notify via Slack!")
            finally:
                print(tb)
            return False

    async def listen(self, registered_actions, debug=False):
        ws = self.websocket
        try:
            data = await asyncio.wait_for(ws.receive_json(), self.timeout)
            if debug:
                print("WS-{} received: {}".format(str(self.id), str(data)))
                await asyncio.sleep(0.1)
            action = data["action"]
            
            if action not in registered_actions.keys():
                raise UnknownActionException(action)

            callback, schema = registered_actions[action]

            # validate if json fits registered schema
            validate(instance=data, schema=schema)
            callback_return = await callback(data, self.id)
            if isinstance(callback_return, tuple):
                success, optional_data = callback_return
            else:
                success = callback_return
                optional_data = None
            if optional_data is None:
                await ws.send_json({"success": success, "action": action})
            elif not isinstance(optional_data, dict):
                await ws.send_json({"success": success, "action": action,
                                    "comment": "Could not add optional data. Server did not return dict. Returned {}".format(
                                        type(optional_data))})
            else:
                answer = {"success": success, "action": action}
                answer.update(optional_data)
                await ws.send_json(answer)
            return True
            
        except ValidationError as err:
            await ws.send_json({"success": False, "action": action, "comment": str(err)})
            return True
        except UnknownActionException as err:
            print("Unknown action: ", err.action)
            await ws.send_json({"success": False, "action": err.action, "comment": "Unknown Action"})
            return True
        except asyncio.TimeoutError as err:
            print("Client connection timed out: "+str(err))
            return False
        except WebSocketDisconnect as err:
            print("Connection terminated: "+str(err))
            return False
        # except RuntimeError as err:
        #     print("Runtime error: "+str(err))
        #     print("Terminating connection...")
        #     return False
        except Exception as err:
            tb = traceback.format_exc()
            if "1006" in str(err):
                print("Connection closed abnormally! (1006)")
                return False
            print("Internal Server Error in callback: ", err)
            try:
                await ws.send_json({"success": False, "action": action, "comment": f"Error from endpoint: '{tb}'"})
            except:
                #Connection is dead!
                pass
            #Now post to slack
            try:
                slack.chat_postMessage(channel='#stacktraces', text="Exception in websocket_manager!+\n"+tb)
            except Exception as err:
                print("Could not notify via Slack!")
            finally:
                print(tb)
            return False

    async def send(self, msg):
        try:
            await self.websocket.send_json(msg)
            return True
        except:
            return False

    async def close(self):
        return await self.websocket.close()


# manager to manage multiple websocket connections
class WebsocketManager:

    def __init__(self, debug=False, zmq=False, timeout=TIMEOUT):
        self.slack = WebClient(SLACK_BOT_TOKEN)
        self.ws = None
        self.active_connections = dict()  # Maps id -> websocket

        self.registered_actions = dict()

        # somehow 'lambda data, code: None' does not work because you can not await None :(
        self.register("ping", lambda data, code: self.nop())

        self.debug = debug
        self.zmq = zmq
        self.timeout = timeout

        print("Initializing ConnectionManager...")
        self.active_connections = dict()  # Maps id -> [websockets]
        self.pendingResponses = {}
        self.socket = None
        self.connected = False
        self.loop = None

    async def init(self):
        self.loop = asyncio.get_running_loop()
        if not self.connected and self.zmq:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setblocking(False)
            self.socket.settimeout(5)
            try:
                await self.loop.sock_connect(self.socket, (os.getenv("ZMQ_HOST"), 9000))
            except:
                if self.debug:
                    print("Could not connect to ZMQ server!", (os.getenv("ZMQ_HOST"), 9000))
                self.connected = False
                return
            if self.debug:
                print("Connected to ZMQ server!")
            self.connected = True
            return

    async def work(self):
        # loop = asyncio.get_running_loop()
        while self.zmq:
            while not self.connected:
                await self.init()
                if not self.connected:
                    # Was not connected, still is not... sleep some time before trying again!
                    print("still not connected...")
                    await asyncio.sleep(5)
            msg = ""
            cc = 0
            while msg == "" or cc != 0:
                s = await self.loop.sock_recv(self.socket, 1)
                if not s:
                    s = None
                    break
                s = s.decode("utf-8")
                for c in s:
                    if c == "{":
                        cc += 1
                    if c == "}":
                        cc -= 1
                msg += s

            else:
                if self.debug:
                    print("ZMQ queried us with: " + str(msg))

                data = json.loads(msg)
                type = data["type"]

                if type == "req":
                    # Server requests if we have a client connected to us?
                    id = data["id"]
                    uid = data["uid"]
                    message = data["msg"]

                    try:
                        wss = self.active_connections[uid]
                    except KeyError:
                        # Not for us!
                        await self.loop.sock_sendall(self.socket,
                                                     json.dumps({"success": False, "id": id, "type": "rep"}).encode(
                                                         "utf-8"))
                        continue
                    # We have at least 1 connected client!
                    for ws in wss:
                        await ws.send(message)
                    await self.loop.sock_sendall(self.socket,
                                                 json.dumps({"success": True, "id": id, "type": "rep"}).encode("utf-8"))
                elif type == "rep":
                    # Server replies to a request that we made!
                    id = data["id"]
                    success = data["success"]

                    if success:
                        self.pendingResponses[id] = True
                    else:
                        self.pendingResponses[id] = False

                else:
                    print("Strange type: " + type)

    #remove from  mapping and close websocket
    async def disconnect(self, id):
        if isinstance(id, Websocket_Wrapper):
            try:  # Treats id as a websocket wrapper
                for key, value in self.active_connections.items(): #id -> websocket wrapper
                    if id in value:
                        self.active_connections[key].remove(id)
                        if len(self.active_connections[key]) <= 0:
                            del self.active_connections[key]
                        break
                await id.close()
                return True, None
            except Exception as err:
                print("terminate Websocket_Wrapper:")
                traceback.print_exc()
                return False, {"comment": str(err)}
        else:
            # Treats id as a code (closes all connections)
            wss = self.active_connections.pop(id)
            for ws in wss:
                await ws.close()
            return True, None

    # connects and authenticates
    async def connect(self, websocket: WebSocket):
        ws = Websocket_Wrapper(websocket, self.timeout)
        authenticated = await ws.authenticate()

        id = None
        if authenticated:
            id = ws.id
            try:
                self.active_connections[id].append(ws)
            except KeyError:
                self.active_connections[id] = [ws]

        return id, ws

    async def send(self, msg, id):
        if self.zmq:
            return await self.send_zmq(msg, id)
        else:
            return await self.send_no_zmq(msg, id)

    async def send_no_zmq(self, msg, id):  # Returns true on success, if at least 1 message was sent successfully
        success = False
        try:
            for wrapper in self.active_connections[id]:
                try:
                    await wrapper.send(msg)
                    success = True
                except:
                    pass
        except KeyError:
            return False
        return success

    async def send_zmq(self, msg, uid):  # Returns true on success. uid may also be a wd code
        # loop = asyncio.get_running_loop()
        # request notification via ZMQ
        if not self.connected:
            # Could not connect! We cant query ZMQ!
            if self.debug:
                print("Can't query ZMQ: not connected!")
            return False

        if self.debug:
            print("Querying ZMQ for uid: " + str(uid))
        id = str(uid) + "-" + str(random.randrange(0, 1000))

        req = {"type": "req", "uid": uid, "msg": msg, "id": id}
        try:
            await self.loop.sock_sendall(self.socket, json.dumps(req).encode("utf-8"))
        except BrokenPipeError:  # We should wait on the self.connected object
            self.connected = False
            # We could try to reconnect here directly instead of via the work method, but that could result in concurrency issues and multiple open sockets!
            # So for now we just don't send the message. It will work again for the next one!
            if self.debug:
                print("Can't query ZMQ: BrokenPipe! Should be reconnected within 10 seconds...")
            return False

        st = time.time()
        if self.debug:
            print("Starting wait at: " + str(st))
        while time.time() - st < 2:  # 2 seconds
            # TODO wait on pendingResponses instead of this mess
            if id in self.pendingResponses.keys():
                if self.pendingResponses[id]:
                    # Successfully delivered!
                    if self.debug:
                        print("Successfully delivered via ZMQ! " + str(time.time()))

                    del self.pendingResponses[id]
                    return True
                else:
                    if self.debug:
                        print("pendingResponses[" + str(id) + "] = " + str(self.pendingResponses[id]))
                    break
            await asyncio.sleep(0.2)

        # Delivery failed, uid is not connected!
        if self.debug:
            print("Delivery failed via ZMQ! " + str(time.time()))
        try:
            del self.pendingResponses[id]
        except:
            if self.debug:
                print("ZMQ did not reply in time!")
                # TODO Now if ZMQ replies after this, the entry will never be deleted from pendingResponses.
                # We should introduce a timestamp in the pendingResponses as well!
        return False

    def register(self, action, function, schema=None):
        if schema is None:
            # s.t. validate() always returns True
            schema = True
        else:
            # update schema to allow "action"
            dc_schema = deepcopy(schema)
            dc_schema["properties"].update({"action": {"type": "string"}})
            schema.update(dc_schema)

        self.registered_actions[action] = (function, schema)

    async def listen(self, wrapper):
        success = await wrapper.listen(self.registered_actions, self.debug)

        if not success:
            await self.disconnect(wrapper)
            return False
        return success

    def is_connected(self, id):
        #Id can be EITHER a uid/wdcode or a wrapper instance.
        try:
            return id.websocket.application_state == WebSocketState.CONNECTED
        except:
            pass
        #Okay, not a wrapper. Now check if at least 1 connection is there and connected.
        #This should become legacy code.
        try:
            return self.active_connections[id][0].websocket.application_state == WebSocketState.CONNECTED
        except:
            return False

    def isUser(self, id):
        return self.active_connections[id][0].isUser

    def get_websocket(self, id):
         # Is only used to get information about an id, so it is irrelevant which wrapper we return, as they all have the same info
        try:
            return self.active_connections[id][0]
        except:
            return None

    async def nop(self):
        return True, None

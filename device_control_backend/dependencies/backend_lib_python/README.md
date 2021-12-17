# Backend Python Lib

## setup

```
python setup.py install
```

## General
The importing service needs environment variables, e.g.:
```
AUTH_BACKEND_SERVICE_HOST=auth.bitahoy.cloud
AUTH_BACKEND_SERVICE_PORT=80
ZMQ_HOST=backend_zmq_server_service_1
SLACK_BOT_TOKEN='[redacted-8]'
```

## auth

```python
from backend_lib import Auth, Expired, VerificationFailed, InvalidToken
auth = Auth() # optionally, it is possible to pass the auth backend url as an argument for testing purposes
try:
    authenticatedClient = auth.verify({'code': 'user@testing.bitahoy.com', 'id': 1091127815, 'perm': 0, 'time': 1622729833, 'belongs': ['xxxxxxxxxxxxxxxx'], 'signature': 'i88wLzXPhPo5aAxffLtvOCvh7dd8/SQzBQle2pnFBi4xP8MlKH8oK8px7A+R9Q+iA1aiqnwT771FSakYVkutMT7kiT+i2XsYHfvOXzypH64ko9J74jg6XP6BWdPIS2WZC4fvyqDzIwW6qDn0UUI0gvaTGjCHZ6YlXtyhz6ZqaCYZWKxuG1Am9DG7mO1LtMkVX0s2TvpSwu9qoAuESgtYhB+PKjN/yIvKbh/YUAbdkITcUn3my4I35T7Fln3TkB7qU2psMjzbxSAyWnXhI9pInDSPF1OtZ6MrE8/yMmdrnxn0oNp1XvqQmaY5ew+tPBbGmS5GoYUZRgJmL6UdwqEX7Q=='})
except Expired:
    print("token expired")
except VerificationFailed:
    print("signature verification failed")
except InvalidToken:
    print("invalid token")
assert authenticatedClient
assert authenticatedClient.code == "user@testing.bitahoy.com"
assert authenticatedClient.uid == 1091127815
assert authenticatedClient.belongs == ['xxxxxxxxxxxxxxxx']
assert authenticatedClient.isUser == True
assert authenticatedClient.permissions == 0
```


## Websocket_Manager
Handles Websocket_Connections.

Every message has to contain a known (= registered action).

The first message always has to be {"action": "auth", "token", token}.

To declare the websocket endpoint:
```
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    id = await websocket_manager.connect(websocket)
    # authentication failed
    if not id:
        return

    while websocket_manager.is_connected(id):
        # while ws.application_state == WebSocketState.CONNECTED:
        success = await websocket_manager.listen(id)
        if not success:
            break
``` 

Previously register some endpoints and import the Websocket_Manager:
```
# returns Tuple (sucess, <optinal json dict>)
async def example(data, id):
    if valid(data):
        success = do_whatevery_you_want()
        return True, None
    else:
        return False, {"comment": "invalid data you scum"} 

# debug prints some stuff, zmq uses send via zmq and timeout default is 30
websocket_manager = WebsocketManager(debug=True, zmq=True, timeout=TIMEOUT)
websocket_manager.register("example", example)
```
Every callback is wrapped in exception handlers that will send the occured exception via the ws.

Every callback function has to return a Tuple that contains

 `(sucess, <optinal json dict>)`.

The websocket will answer with

 `{"action": "example", "success": success, <optinal json dict>}`

### JSON Schema
`register()` takes a json schema as optional argument for input validation. 

See
- https://github.com/Julian/jsonschema
- https://json-schema.org/learn/getting-started-step-by-step

If no schema is specified, every input will always be accepted. 

A schema might look like
```
newAlarmDetected_schema = {
    "type": "object",
    "properties": {
        "info": {
            "type": "object",
            "properties": {
                "modelName" : {"type": "string"},
                "version": {"type": "number"},
                "deviceName": {"type": "string"},
                "timestamp": {"type": "number"},
            },
            "required": ["modelName", "version", "deviceName", "timestamp"],
            "additionalProperties": False,
        },
    },
    "required": ["info"],
    "additionalProperties": False,
}
```
If one uses `"additionalProperties": False,` for stricter validation, "action" does not need to be specified and is
handled by the backend_lib.
 
 ## Websocket_Client
 This is a websocket client that can be used in tests as alternative to the FastAPI TestClient provided websocket.
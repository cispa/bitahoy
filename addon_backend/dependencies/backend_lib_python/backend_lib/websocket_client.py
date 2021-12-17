import json
from websocket import create_connection


# little wrapper to get send_json and receive_json for python websocket clients
# can be used by tests
class WebsocketClient():
    def __init__(self, url):
        # super(websocket_client, self).__init__()
        self.ws = create_connection(url)

    def send_json(self, msg):
        self.ws.send(json.dumps(msg))

    def receive_json(self):
        return json.loads(self.ws.recv())

    def close(self):
        self.ws.close()
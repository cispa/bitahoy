import zmq
import json

#Test it
context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("tcp://192.168.178.24:9000")

repsocket = context.socket(zmq.REP)
repsocket.bind("tcp://127.0.0.1:9000")


repsocket2 = context.socket(zmq.REP)
repsocket2.bind("tcp://127.0.0.1:9000") #This must be a different IP to the first one!


print("Connected!")


socket.send(b"PING1")
print("Sent ping")
msg = socket.recv()
print("Received reply: %s" % msg)


req = {"type":"con","ip":"127.0.0.1:9000"}
socket.send_json(req)
print("Sent con")
msg = socket.recv()
print("Received reply: %s" % msg)


req = {"type":"req","id":"9","msg":{"comment":"hello world"}}
socket.send_json(req)
print("Sent req")

rec = repsocket.recv()
print("Response socket received: ")
print(rec)
repsocket.send(b"OK")
print("Response socket replied!")

msg = socket.recv()
print("Received reply: %s" % msg)


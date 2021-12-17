import os
import random
import sys
import time

import psycopg2
import requests
from app import app
from fastapi import FastAPI
from fastapi.testclient import TestClient

AUTH_URL = "http://{}".format(os.getenv("AUTH_BACKEND_SERVICE_HOST"))
testmail = "marius@bitahoy.com"
wdcode = "xxxxxxxxxxxxxxxx"
secret = "[redacted-7]"
password = "[redacted-9]"
TEST_EMAIL = "marius@bitahoy.com"
log = False

token = None
usertoken = None

random.seed(6021966)

# dis-/connect WS help functions - used in insert-/getconfig
def connect_WS():
    # old? Auth? taken form below...
    client = TestClient(app)
    response = requests.get(AUTH_URL + "/authenticateWatchdog",
                            json={"wdcode": wdcode, "secret": secret})
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["token"] != None

    websocket = client.websocket_connect("/ws")
    websocket.send_json({"action": "auth", "token": response.json()["token"]})
    data = websocket.receive_json()
    assert data["success"]
    # Authenticated!
    return websocket

def disconnect_WS(wd_websocket):
    wd_websocket.send_json({"action": "disconnect"})
    data = wd_websocket.receive_json()
    assert data["success"]

    time.sleep(0.1)
    wd_websocket.close()

def testInsertConfig():
    # setup WS
    wd_websocket = connect_WS()

    # ping test, sanity check
    wd_websocket.send_json({"action": "ping"})
    data = wd_websocket.receive_json()
    assert data["success"]

    time.sleep(0.5)

    # sanity check, no config supplied
    wd_websocket.send_json(
        {"action": "insertConfig", "info":
            {"timestamp": int(time.time()),
             }
         })

    data = wd_websocket.receive_json()
    # print("tst WSgetConfig: wd received: " + str(data))
    assert not data["success"]
    assert data["comment"] == "No config supplied. Please check inputs."

    time.sleep(0.5)

    non_existing_config = {'ports': [21, 22, 23], 'flag': True, 'foo': 'bar'}

    wd_websocket.send_json(
        {"action": "insertConfig", "info":
             {"timestamp": int(time.time()),
              "config": non_existing_config}
         })

    data = wd_websocket.receive_json()
    assert data["success"]

    assert non_existing_config == data["config"]
    assert data["comment"] == "No config exists for this WD code. Created new entry."

    time.sleep(0.5)

    new_config = {'ports': [666], 'flag': False, 'foo': 'bar'}

    # now try to overwrite it
    wd_websocket.send_json(
        {"action": "insertConfig", "info":
            {"timestamp": int(time.time()),
             "config": new_config}
         })

    data = wd_websocket.receive_json()
    # print("tst WSgetConfig: wd received: " + str(data))
    assert data["success"]

    assert new_config == data["config"]
    assert data["comment"] == "Found an existing config for this WD code. Overwriting existing with new."

    time.sleep(0.5)

    disconnect_WS(wd_websocket)

def testGetConfig():
    # setup WS
    wd_websocket = connect_WS()

    # ping test, sanity check
    wd_websocket.send_json({"action": "ping"})
    data = wd_websocket.receive_json()
    assert data["success"]

    time.sleep(0.5)

    existing_config = {'ports': [666], 'flag': False, 'foo': 'bar'}

    # just get the config already
    wd_websocket.send_json(
        {"action": "getConfig", "info":
            {"timestamp": int(time.time()),
             }
         })

    data = wd_websocket.receive_json()
    # print("tst WSgetConfig: wd received: " + str(data))
    assert data["success"]
    assert existing_config == data["config"]

    time.sleep(0.5)

    disconnect_WS(wd_websocket)

def testStatistics1():
    client = TestClient(app)
    
    response = client.get("/publicStatistics")
    if log:
        print("Received public statistics: ")
        print(response.json()["statistics"])
    assert response.json()["success"] == True
    assert response.json()["statistics"]["clients"] == 0
    assert response.json()["statistics"]["uids"] == 0
    assert response.json()["statistics"]["devices"] == 0


    response = requests.get(AUTH_URL+"/authenticateWatchdog",json={"wdcode":wdcode, "secret":secret})
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["token"] != None
    token = response.json()["token"]
    if log:
        print("CLIENT LOGGED IN")
        
    response = client.get("/submitStatistics",json={"wdcode":wdcode,"token":token,"deviceid":1,"statistic":"DDoS","value":1})
    assert response.json()["success"] == True
    
    response = client.get("/publicStatistics")
    if log:
        print("Received public statistics: ")
        print(response.json()["statistics"])
    assert response.json()["success"] == True
    assert response.json()["statistics"]["clients"] == 1
    assert response.json()["statistics"]["uids"] == 1
    assert response.json()["statistics"]["devices"] == 1
    assert response.json()["statistics"]["DDoS"] == 1
    
    response = client.get("/submitStatistics",json={"wdcode":wdcode,"token":token,"deviceid":1,"statistic":"traffic","value":5})
    assert response.json()["success"] == True
    
    response = client.get("/publicStatistics")
    if log:
        print("Received public statistics: ")
        print(response.json()["statistics"])
    assert response.json()["success"] == True
    assert response.json()["statistics"]["clients"] == 1
    assert response.json()["statistics"]["uids"] == 1
    assert response.json()["statistics"]["devices"] == 1
    assert response.json()["statistics"]["DDoS"] == 1
    assert response.json()["statistics"]["traffic"] == 5
    
    response = requests.post(AUTH_URL+"/login",json={"email":testmail, "password": password})
    assert response.json()["success"] == True
    assert response.json()["token"] != None
    usertoken = response.json()["token"]
    if log:
        print("USER LOGGED IN")
    
    response = client.get("/privateStatistics",json={"token":usertoken,"time":24})
    if log:
        print("Received private statistics: ")
        print(response.json()["statistics"])
    assert response.json()["success"] == True
    assert len(response.json()["statistics"]) == 2

def testLogs1():
    client = TestClient(app)
    response = requests.get(AUTH_URL + "/authenticateWatchdog",
                            json={"wdcode": wdcode, "secret": secret})
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["token"] != None

    websocket = client.websocket_connect("/ws")
    websocket.send_json({"action": "auth", "token": response.json()["token"]})
    data = websocket.receive_json()
    assert data["success"]


    generate_logs = 30
    senders = ["testa", "testb", "testc"]
    messages = ["We're no strangers to love", "You know the rules and so do I", "A full commitment's what I'm thinking of", "You wouldn't get this from any other guy"]
    send_logs = []
    for i in range(0, generate_logs):
        wd_log = {"level": random.randint(0, 100), "time": time.time(), "sender": random.choice(senders), "message": random.choice(messages)}
        websocket.send_json({"action": "uploadLogs", "logs": [wd_log]})
        data = websocket.receive_json()
        assert data["success"]
        send_logs.append(wd_log)

    websocket.send_json({"action": "getLogs", "timewindow": 10})
    data = websocket.receive_json()
    assert data["success"]
    # latest message comes first
    send_logs.reverse()
    for i in range(0, len(send_logs)):
        log = data["logs"][i]
        sender, message, level = log
        assert sender == send_logs[i]["sender"]
        assert message == send_logs[i]["message"]
        assert level == send_logs[i]["level"]

    websocket.send_json({"action": "disconnect"})
    data = websocket.receive_json()
    assert data["success"]

def testLogs2():
    client = TestClient(app)
    response = requests.get(AUTH_URL + "/authenticateWatchdog",
                            json={"wdcode": wdcode, "secret": secret})
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["token"] != None

    websocket = client.websocket_connect("/ws")
    websocket.send_json({"action": "auth", "token": response.json()["token"]})
    data = websocket.receive_json()
    assert data["success"]


    generate_logs = 25
    senders = [".Z:}uu=3L$iSdNk{Yj8K", "%n_uZ89XJ42Y{?g2k}yP", "3rG;:[758a(*=urPQ)fp", "V/:?){Pi/iX[64;BYPvg", "2fu=75H476KAE{!D:f9]"]
    messages = ["I just wanna tell you how I'm feeling", "Gotta make you understand", "Never gonna give you up", "Never gonna let you down",
                "Never gonna run around and | desert you", "Never gonna make you cry", "Never gonna say goodbye", "Never gonna tell a lie and hurt you"]
    send_logs = []
    for i in range(0, generate_logs):
        wd_log = {"level": random.randint(0, 100), "time": time.time(), "sender": random.choice(senders), "message": random.choice(messages)}
        websocket.send_json({"action": "uploadLogs", "logs": [wd_log]})
        data = websocket.receive_json()
        assert data["success"]
        send_logs.append(wd_log)


    specific_sender = random.choice(send_logs)["sender"]
    websocket.send_json({"action": "getLogs", "timewindow": 10, "sender": specific_sender})
    data = websocket.receive_json()
    assert data["success"]
    assert len(data["logs"]) > 0
    for i in range(0, len(data["logs"])):
        log = data["logs"][i]
        sender, message, level = log
        assert sender == specific_sender


    specific_level = random.choice(send_logs)["level"]
    websocket.send_json({"action": "getLogs", "timewindow": 10, "level": specific_level})
    data = websocket.receive_json()
    assert data["success"]
    assert len(data["logs"]) > 0
    for i in range(0, len(data["logs"])):
        log = data["logs"][i]
        sender, message, level = log
        assert level <= specific_level


    specific_log = random.choice(send_logs)
    specific_level = specific_log["level"]
    specific_sender = specific_log["sender"]
    websocket.send_json({"action": "getLogs", "timewindow": 10, "sender": specific_sender, "level": specific_level})
    data = websocket.receive_json()
    assert data["success"]
    assert len(data["logs"]) > 0
    for i in range(0, len(data["logs"])):
        log = data["logs"][i]
        sender, message, level = log
        assert level <= specific_level
        assert sender == specific_sender

    websocket.send_json({"action": "disconnect"})
    data = websocket.receive_json()
    assert data["success"]

def testLogsCleanUp():
    client = TestClient(app)
    response = requests.get(AUTH_URL + "/authenticateWatchdog",
                            json={"wdcode": wdcode, "secret": secret})
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["token"] != None

    websocket = client.websocket_connect("/ws")
    websocket.send_json({"action": "auth", "token": response.json()["token"]})
    data = websocket.receive_json()

    assert data["success"]

    generate_logs = 10
    senders = ["testa", "testb", "testc"]
    messages = ["We're no strangers to love", "You know the rules and so do I", "A full commitment's what I'm thinking of", "You wouldn't get this from any other guy"]
    send_logs = []
    for i in range(0, generate_logs):
        wd_log = {"level": random.randint(0, 100), "time": time.time(), "sender": random.choice(senders), "message": random.choice(messages)}
        send_logs.append(wd_log)

    websocket.send_json({"action": "uploadLogs", "logs": send_logs})

    data = websocket.receive_json()
    assert data["success"]

    # User interaction
    response = requests.post(AUTH_URL + "/login", json={"email": TEST_EMAIL, "password": "[redacted-9]"})
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["token"] != None

    user_ws = client.websocket_connect("/ws")
    user_ws.send_json({"action": "auth", "token": response.json()["token"]})
    data = user_ws.receive_json()

    assert data["success"]

    user_ws.send_json({"action": "getLogs", "timewindow": 10})
    data = user_ws.receive_json()
    assert data["success"]
    # latest message comes first
    send_logs.reverse()
    for i in range(0, len(send_logs)):
        log = data["logs"][i]
        sender, message, level = log
        assert sender == send_logs[i]["sender"]
        assert message == send_logs[i]["message"]
        assert level == send_logs[i]["level"]


    latest_message_timestamp = send_logs[0]["time"]
    logs_timewindow = int(os.getenv("LOGS_TIMEWINDOW"))
    cleanup_interval = int(os.getenv("CLEANUP_INTERVAL"))
    # wait till cleanup removes last entry and query again
    while time.time() < latest_message_timestamp + logs_timewindow + cleanup_interval:
        user_ws.send_json({"action": "ping"})
        data = user_ws.receive_json()
        assert data["success"]

        websocket.send_json({"action": "ping"})
        data = websocket.receive_json()
        assert data["success"]
        time.sleep(5)
    user_ws.send_json({"action": "getLogs", "timewindow": logs_timewindow*2})
    data = user_ws.receive_json()
    # now there should be no logs
    assert data["success"]
    assert len(data["logs"]) == 0

    user_ws.send_json({"action": "disconnect"})
    data = user_ws.receive_json()
    assert data["success"]

    websocket.send_json({"action": "disconnect"})
    data = websocket.receive_json()
    assert data["success"]



try:
    try:
        if sys.argv[1] == "verbose" or sys.argv[1] == "v":
            log = True
    except:
        pass
    
    print("Running tests...\n")

    testInsertConfig()
    print("Successfully completed testInsertConfig\n")
    testGetConfig()
    print("Successfully completed testGetConfig\n")

    testStatistics1()
    print("Successfully completed testStatistics1\n")
    testLogs1()
    print("Successfully completed testLogs1\n")
    testLogs2()
    print("Successfully completed testLogs2\n")
    testLogsCleanUp()
    print("Successfully completed testLogsCleanUp\n")

    print("\nTESTS COMPLETED SUCCESSFULLY!")
finally:
    #Clean up the database:
    conn = psycopg2.connect("dbname='db' user='db' host='db' [redacted-2]")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM statistics WHERE wdcode='{}'".format(wdcode))
    cursor.execute("DELETE FROM logs WHERE wdcode='{}'".format(wdcode))
    cursor.execute("DELETE FROM configs WHERE wdcode='{}'".format(wdcode))
    conn.commit()
    cursor.close()
    conn.close()
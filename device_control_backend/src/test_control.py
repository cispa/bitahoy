import time
import psycopg2
import requests
import sys
import os
from enums import *
import pytest
import pip
import random

def install(package):
    if hasattr(pip, 'main'):
        pip.main(['install', package])
    else:
        pip._internal.main(['install', package])

try:
    addon_sdk_python_path = 'dependencies/addon-sdk-python/'
    # assert os.path.isfile(addon_sdk_python_path)
    # subprocess.call(['pip3', 'install',  addon_sdk_python_path])
    install(addon_sdk_python_path)
    backend_lib_python_path = 'dependencies/backend_lib_python/'
    # assert os.path.isfile(backend_lib_python_path)
    # subprocess.call(['pip3', 'install',  backend_lib_python_path])
    install(backend_lib_python_path)
    from bitahoy_sdk.backend import BackendWS
    from backend_lib.websocket_client import WebsocketClient
except Exception as e:
    print("Could not install dependencies.")
    print(e)

AUTH_URL = "https://auth.bitahoy.cloud"
TEST_EMAIL = "marius@bitahoy.com" #TODO fill in (This is where the test emails get send to)
TEST_PW = "[redacted-9]"
TEST_SECRET = "[redacted-7]"
log = True
WS_URL = "ws://localhost:9000/ws"

deviceid = random.randint(0, 2**16)
deviceid2 = random.randint(0, 2**16)
deviceid3 = random.randint(0, 2**16)


def testSystem1():
    # async with AsyncClient(app=app) as client: #This opens an additional 9th connection to the ZMQ server

        # client = TestClient(app)
        print("start test")
        response = requests.get(AUTH_URL+"/authenticateWatchdog",json={"wdcode":"xxxxxxxxxxxxxxxx","secret":TEST_SECRET})
        assert response.status_code == 200
        assert response.json()["success"] == True
        assert response.json()["token"] != None
        if log:
            print("CLIENT LOGGED IN")
        # await asyncio.sleep(10)
        # websocket = client.websocket_connect("/ws")

        ws = WebsocketClient(WS_URL)
        # WebsocketClient.create_connection("ws://127.0.0.1")
        ws.send_json({"action": "auth", "token": response.json()["token"]})
        data = ws.receive_json()
        if log:
            print("wd received: "+str(data))
        # print(data)
        assert data["success"]
        #Authenticated!
        ws.send_json({"action":"registerDevice","deviceid": deviceid,"devicetype":DeviceType.UNKNOWN.value})
        data = ws.receive_json()
        if log:
            print("wd received: "+str(data))
        assert data["action"] == "registerDevice"
        data = ws.receive_json()
        if log:
            print("wd received: "+str(data))
        assert data["success"]
        assert data["action"] == "registerDevice"
        ws.send_json({"action": "requestInfo"})
        data = ws.receive_json()
        if log:
            print("wd received: "+str(data))
        assert data["success"]
        assert data["data"] != None
        assert data["action"] == "requestInfo"
        # async with TestClient(app) as user_client:
        #User interaction
        response = requests.post(AUTH_URL+"/login",json={"email":TEST_EMAIL, "password": TEST_PW})
        assert response.status_code == 200
        assert response.json()["success"] == True
        assert response.json()["token"] != None
        if log:
            print("USER LOGGED IN")
        # user_ws = user_client.websocket_connect("/ws")
        user_ws = WebsocketClient(WS_URL)
        user_ws.send_json({"action": "auth", "token": response.json()["token"]})
        data = user_ws.receive_json()
        if log:
            print("user received: "+str(data))
        assert data["success"]
        #Authenticated!
        user_ws.send_json({"action":"requestInfo"})
        data = user_ws.receive_json()
        if log:
            print("user received: "+str(data))
        assert data["success"]
        assert data["data"] != None
        assert data["action"] == "requestInfo"
        #User creates alias
        user_ws.send_json({"action":"updateOption","wdcode":"xxxxxxxxxxxxxxxx","deviceid":deviceid,"key":"alias","value":"MY ALIAS"})
        data = user_ws.receive_json() #User confirm
        print(data)
        assert data["action"] == "updateOption"
        data = user_ws.receive_json() #User confirm
        print(data)
        assert data["success"]
        assert data["action"] == "updateOption"
        if log:
            print("user received: "+str(data))
        data = ws.receive_json() #Watchdog notification
        if log:
            print("wd received: "+str(data))
        assert data["action"] == "updateOption"
        if log:
            print("multi notification OK")
        #Watchdog updates device type
        ws.send_json({"action":"updateType","deviceid":deviceid,"devicetype":DeviceType.OTHER.value})
        data = ws.receive_json()
        assert data["action"] == "updateType"
        data = ws.receive_json()
        assert data["success"]
        assert data["action"] == "updateType"
        if log:
            print("wd received: "+str(data))
        data = user_ws.receive_json() #User notification
        if log:
            print("user received: "+str(data))
        assert data["action"] == "updateType"
        ws.send_json({"action":"requestInfo"})
        data = ws.receive_json()
        if log:
            print("wd received: "+str(data)) #Updated data!
        assert data["success"]
        assert data["action"] == "requestInfo"
        ws.send_json({"action":"ping"})
        data = ws.receive_json()
        if log:
            print("user received: "+str(data))
        assert data["action"] == "ping"
        #Register 2nd device while user is active to receive notification
        ws.send_json({"action":"registerDevice","deviceid":deviceid2,"devicetype":DeviceType.UNKNOWN.value})
        data = ws.receive_json()
        if log:
            print("wd received: "+str(data))
        assert data["action"] == "registerDevice"
        data = ws.receive_json()
        if log:
            print("wd received: "+str(data))
        assert data["success"]
        assert data["action"] == "registerDevice"
        data = user_ws.receive_json()
        if log:
            print("user received: "+str(data))
        assert data["action"] == "registerDevice"
        #Disconnect the user
        user_ws.close()
        time.sleep(0.1) #Just for better printing, does not influence logic!
        #Register 3rd device while user is offline to push email
        ws.send_json({"action":"registerDevice","deviceid":deviceid3,"devicetype":DeviceType.UNKNOWN.value})
        data = ws.receive_json()
        if log:
            print("wd received: "+str(data))
        assert data["action"] == "registerDevice"
        data = ws.receive_json()
        if log:
            print("wd received: "+str(data))
        assert data["success"]
        assert data["action"] == "registerDevice"
        ws.send_json({"action":"requestInfo"})
        data = ws.receive_json()
        if log:
            print("wd received: "+str(data)) #Updated data!
        assert data["data"][str(deviceid)]["alias"] == "MY ALIAS"
        assert data["data"][str(deviceid2)]["type"] == DeviceType.UNKNOWN.value
        assert data["data"][str(deviceid3)]["status"] == Status.NORMAL.value
        time.sleep(0.1)
        ws.close()
        time.sleep(0.1)
 



def testNegative1():
    # client = TestClient(app)
    response = requests.post(AUTH_URL+"/login",json={"email":TEST_EMAIL, "password": TEST_PW})
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["token"] != None
    if log:
        print("USER LOGGED IN")
    
    # user_ws = client.websocket_connect("/ws")
    user_ws = WebsocketClient(WS_URL)
    user_ws.send_json({"action": "auth", "token": response.json()["token"]})
    data = user_ws.receive_json()
    print(data)
    if log:
        print("user received: "+str(data))
    assert data["success"]
    
    #Authenticated!
    user_ws.send_json({"action":"updateOption","wdcode":"xxxxxxxxxxxxxxxx","deviceid":deviceid,"key":"W_eiRd_keY","value":"myValue"})
    data = user_ws.receive_json()
    if log:
        print("user received: "+str(data))
    assert not data["success"]
    assert data["action"] == "updateOption"


def testChangeEmailSetting():
    # client = TestClient(app)
    response = requests.post(AUTH_URL+"/login",json={"email":TEST_EMAIL, "password": TEST_PW})
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["token"] != None

    # user_ws = client.websocket_connect("/ws")
    user_ws = WebsocketClient(WS_URL)
    user_ws.send_json({"action": "auth", "token":response.json()["token"]})
    data = user_ws.receive_json()
    assert data["success"]
    
    user_ws.send_json({"action":"updateOption","wdcode":"xxxxxxxxxxxxxxxx","deviceid":deviceid,"key":"mailPolicy","value":MailPolicy.NEVER.value})
    data = user_ws.receive_json()
    assert data["action"] == "updateOption"
    data = user_ws.receive_json()
    assert data["success"]
    assert data["action"] == "updateOption"
    user_ws.close()
    
    #Now the watchdog changes the status of the device and we expect to NOT receive an email (we have set email to NEVER!)
    response = requests.get(AUTH_URL+"/authenticateWatchdog",json={"wdcode":"xxxxxxxxxxxxxxxx","secret":TEST_SECRET})
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["token"] != None
    
    # websocket = client.websocket_connect("/ws")
    ws = WebsocketClient(WS_URL)
    ws.send_json({"action": "auth", "token":response.json()["token"]})
    data = ws.receive_json()
    assert data["success"]
 
    ws.send_json({"action":"updateStatus","deviceid":deviceid,"status":Status.QUARANTINED.value})
    data = ws.receive_json()
    assert data["action"] == "updateStatus"
    data = ws.receive_json()
    assert data["success"]
    assert data["action"] == "updateStatus"
    
    ws.send_json({"action":"requestInfo"})
    data = ws.receive_json()
    assert data["success"]
    assert data["action"] == "requestInfo"
    assert data["data"][str(deviceid)]["mailPolicy"] == "-1"
    ws.close()
 

# # timeout in auth results in auth failure
# def testWebsocketTimeout1():
#     ws = WebsocketClient(WS_URL)
#     time.sleep(TIMEOUT + 1)
#     data = ws.receive_json()
#     assert data["success"] is False

# timeout after auth
# def testWebsocketTimeout2():
#     response = requests.post(AUTH_URL+"/login",json={"email":TEST_EMAIL, "password": TEST_PW})
#     assert response.status_code == 200
#     assert response.json()["success"] == True
#     assert response.json()["token"] != None

#     # user_ws = client.websocket_connect("/ws")
#     user_ws = WebsocketClient(WS_URL)
#     user_ws.send_json({"action": "auth", "token":response.json()["token"]})
#     data = user_ws.receive_json()
#     assert data["success"]

#     time.sleep(TIMEOUT + 1)
#     user_ws.send_json({"action": "updateOption", "wdcode": "xxxxxxxxxxxxxxxx", "deviceid": 1234, "key": "mailPolicy",
#                        "value": MailPolicy.NEVER.value})

#     data = user_ws.receive_json()
#     assert not data["success"]

    
    
def main():
    try:
        try:
            if sys.argv[1] == "verbose" or sys.argv[1] == "v":
                log = True
        except:
            pass

        print("Running tests...\n")

        # asyncio.get_event_loop().run_until_complete(testSystem1())
        testSystem1()
        print("Successfully completed testSystem1\n")
        testNegative1()
        print("Successfully completed testNegative1\n")
        testChangeEmailSetting()
        print("Successfully completed testChangeEmailSetting\n")
        testWebsocketTimeout1()
        print("Successfully completed testWebsocketTimeout1\n")
        testWebsocketTimeout2()
        print("Successfully completed testWebsocketTimeout2\n")

        print("\nTESTS COMPLETED SUCCESSFULLY!")
    finally:
        #Clean up the database:
        conn = psycopg2.connect("dbname='db' user='db' host='db' [redacted-2]")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM devices WHERE wdcode='xxxxxxxxxxxxxxxx'")
        # cursor.execute("DELETE FROM wdcodes WHERE wdcode='xxxxxxxxxxxxxxxx'")
        cursor.execute("DELETE FROM users WHERE email='"+TEST_EMAIL+"'")
        cursor.execute("DELETE FROM optionals WHERE wdcode='xxxxxxxxxxxxxxxx'")
        conn.commit()
        cursor.close()
        conn.close()

# @pytest.fixture(autouse=True)
# def run_around_tests():
#     # Code that will run before your test, for example:
#     pass
#     # A test function will be run at this point
#     yield
#     # Code that will run after your test, for example:
#     # Clean up the database:
#     conn = psycopg2.connect("dbname='db' user='db' host='db' [redacted-2]")
#     cursor = conn.cursor()
#     cursor.execute("DELETE FROM devices WHERE wdcode='xxxxxxxxxxxxxxxx'")
#     # cursor.execute("DELETE FROM wdcodes WHERE wdcode='xxxxxxxxxxxxxxxx'")
#     cursor.execute("DELETE FROM users WHERE email='" + TEST_EMAIL + "'")
#     cursor.execute("DELETE FROM optionals WHERE wdcode='xxxxxxxxxxxxxxxx'")
#     conn.commit()
#     cursor.close()
#     conn.close()


if __name__ == '__main__':
    main()
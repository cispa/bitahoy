from fastapi.testclient import TestClient
from app import app
from enums import DeviceType
import requests
import psycopg2
import sys
import base64
import time
import random
import copy

random.seed(42)

client = TestClient(app)
conn = psycopg2.connect("dbname='ml_db' user='ml_db' host='ml_db' [redacted-2]")
cursor = conn.cursor()

# Sample entry to store and retrieve
deviceName = "Smart Fridge Vendor Type XFD1337-420B"
# client sends DeviceType as string (could also be the enum)
deviceType = {"string": "misc", "enum_value": DeviceType.MISC.value}
model_file = "sample_model.pckl"
modelName = "Sample model from " + model_file
# increment for testing after every /storeModel call. reset to 0 after every table drop
version = 0

AUTH_URL = "https://auth.bitahoy.cloud"

# get auth token for wd
wdcode = "xxxxxxxxxxxxxxxx"
# wdcode = "xxxxxxxxxxxxxxxx"
secret= "[redacted-7]"
# comment in in case of database table drop
# response = requests.post(AUTH_URL + "/register", json={"wdcode": wdcode, "email": "marius-1@testing.bitahoy.com",
#                                                       "password": "Password1"})
# print(response.json())
response = requests.get(AUTH_URL + "/authenticateWatchdog", json={"wdcode": wdcode, "secret": secret})
# print(response.json())
AUTH_TOKEN = response.json()["token"]
# print(AUTH_TOKEN)
# get auth token for admin
# admin_code = "xxxxxxxxxxxxxxxx"
admin_code = "xxxxxxxxxxxxxxxx"
# comment in in case of database table drop
# response = requests.post(AUTH_URL + "/register", json={"wdcode": admin_code, "email": "marius-admin@testing.bitahoy.com",
#                                                       "password": "Password1"})
response = requests.get(AUTH_URL + "/authenticateWatchdog", json={"wdcode": admin_code, "secret": secret})
ADMIN_AUTH_TOKEN = response.json()["token"]

admin_client = TestClient(app)


def test():
    response = client.get("/")
    assert response.status_code == 200
    # assert response.json()["success"] == True


# Store a model
def testStoreModel():
    with open("resources/" + model_file, "rb") as file:
        modelBinary = file.read()
    response = client.post("/storeModel", json={"token": AUTH_TOKEN, "modelName": modelName, "deviceName": deviceName,
                                                "deviceType": deviceType["string"],
                                                "modelBinary": base64.b64encode(modelBinary).decode('utf-8')})
    assert response.status_code == 200
    assert response.json()["success"]
    cursor.execute("SELECT * FROM devices WHERE deviceName=%s", (deviceName,))
    result = cursor.fetchone()
    assert result[0] == deviceName
    # the db contains only the value of the enum, not the string
    assert result[1] == deviceType["enum_value"]

    cursor.execute("SELECT * FROM models WHERE modelID=%s", (result[2],))
    result = cursor.fetchone()

    # version number
    assert isinstance(result[2], int)
    # binary
    assert sys.getsizeof(modelBinary) == sys.getsizeof(bytes(result[3]))
    # TODO: compare if two binaries are equal

    # return version for other tests
    return result[2]


# Invalid Authentication Signature Test
# auth will be replaced with shared library that all API endpoints use so 1 test is enough
def testAuthNegative():
    with open("resources/" + model_file, "rb") as file:
        modelBinary = file.read()

    # alter signature somehow to check for an invalid signature
    invalid_auth_token = copy.deepcopy(AUTH_TOKEN)
    index_to_replace = random.randint(1, len(invalid_auth_token["signature"]))
    replace_char = "="
    assert invalid_auth_token["signature"][index_to_replace] != replace_char
    invalid_auth_token["signature"] = invalid_auth_token["signature"][:index_to_replace] + \
                                      replace_char + invalid_auth_token["signature"][index_to_replace + 1:]
    assert invalid_auth_token["signature"][index_to_replace] == replace_char

    response = client.post("/storeModel",
                           json={"token": invalid_auth_token, "modelName": modelName, "deviceName": deviceName,
                                 "deviceType": deviceType["string"],
                                 "modelBinary": base64.b64encode(modelBinary).decode('utf-8')})

    assert response.status_code == 200
    assert response.json()["success"] == False


# /getModelByDeviceName
# get by DeviceName and Version Number
def testGetModelByDeviceNamePositive():
    response = client.get("/getModelByDeviceName",
                          json={"token": AUTH_TOKEN, "deviceName": deviceName, "version": version})

    assert response.status_code == 200
    assert response.json()["deviceName"] == deviceName
    # .upper() because the server will return the string in some format and the client has to interpret it
    assert response.json()["deviceType"] == deviceType["string"].upper()
    assert response.json()["version"] == version
    assert sys.getsizeof(bytes(base64.b64decode(response.json()["modelBinary"]))) > 1


# get by DeviceName and Version Number
def testGetModelByDeviceNameNegative():
    invalid_version = 1337
    response = client.get("/getModelByDeviceName",
                          json={"token": AUTH_TOKEN, "deviceName": deviceName,
                                "version": invalid_version})

    assert response.status_code == 200
    assert response.json()["success"] == False


# /getLatestModelByDeviceName
def testGetLatestModelByDeviceNamePositive():
    response = client.get("/getLatestModelByDeviceName",
                          json={"token": AUTH_TOKEN, "deviceName": deviceName})

    assert response.status_code == 200
    assert response.json()["deviceName"] == deviceName
    # .upper() because the server will return the string in some format and the client has to interpret it
    assert response.json()["deviceType"] == deviceType["string"].upper()
    assert response.json()["version"] == version
    assert sys.getsizeof(bytes(base64.b64decode(response.json()["modelBinary"]))) > 1


def testGetLatestModelByDeviceNameNegative():
    response = client.get("/getLatestModelByDeviceName",
                          json={"token": AUTH_TOKEN, "deviceName": "roflcopter"})

    assert response.status_code == 200
    assert response.json()["success"] == False


# store multiple models and check version number
def testModelVersionNumber():
    global version
    # cleanup any prior tests
    cursor.execute("DELETE FROM alarms")
    cursor.execute("DELETE FROM wds")
    cursor.execute("DELETE FROM devices")
    cursor.execute("DELETE FROM models")
    conn.commit()
    version = 0

    # store a model <iterations> times
    iterations = 17
    for i in range(1, iterations + 1):
        version = testStoreModel()
        assert version == i
    assert version == iterations


# two clients interact with server
def testWebsocket():
    global version
    wd_websocket = client.websocket_connect("/ws")

    wd_websocket.send_json({"action": "auth", "token": AUTH_TOKEN})
    data = wd_websocket.receive_json()

    assert data["success"]
    # Authenticated!

    # first let's get a model for our device (stored by previous tests)
    response = client.get("/getLatestModelByDeviceName",
                          json={"token": AUTH_TOKEN, "deviceName": deviceName})

    assert response.json()["modelName"] == modelName
    assert response.json()["version"] == version

    # now we are playing around with our great new model and suddenly a wild alarm occurs.
    # better report to the authorities
    wd_websocket.send_json(
        {"action": "newAlarmDetected", "info": {"timestamp": int(time.time()), "deviceName": deviceName,
                                                "modelName": response.json()["modelName"],
                                                "version": response.json()["version"]}})

    data = wd_websocket.receive_json()
    print("wd received: " + str(data))
    assert data["success"]

    time.sleep(0.5)
    wd_websocket.send_json(
        {"action": "newAlarmDetected", "info": {"timestamp": int(time.time()), "deviceName": deviceName,
                                                "modelName": response.json()["modelName"],
                                                "version": response.json()["version"]}})

    data = wd_websocket.receive_json()
    print("wd received: " + str(data))
    assert data["success"]

    # now the admin comes and controls stuff
    # lets see if there is anything suspicious with the alarms
    response = admin_client.get("/getAlarmsForDevice", json={"token": ADMIN_AUTH_TOKEN, "deviceName": deviceName})
    # we previously generated two alarms
    assert len(response.json()["data"]) >= 2
    # wds might use different models so check modelID
    alarm_modelID = None

    for alarm in response.json()["data"]:
        if alarm_modelID is None:
            alarm_modelID = alarm[3]
        else:
            # here all alarms come from the same wd with the same modelID
            assert alarm_modelID == alarm[3]

    # multiple alarms by the same model on the same device. This is either really good or really bad ;)
    # perhaps now we want to update or rollback the model
    # admin connects as websocket to control devices
    admin_websocket = admin_client.websocket_connect("/ws")
    admin_websocket.send_json({"action": "auth", "token": ADMIN_AUTH_TOKEN})
    data = admin_websocket.receive_json()
    # admin authenticated
    time.sleep(0.5)
    # admin stores a "new" model
    with open("resources/" + model_file, "rb") as file:
        modelBinary = file.read()
    response = admin_client.post("/storeModel",
                                 json={"token": ADMIN_AUTH_TOKEN, "modelName": modelName, "deviceName": deviceName,
                                       "deviceType": deviceType["string"],
                                       "modelBinary": base64.b64encode(modelBinary).decode('utf-8')})
    # for testing purposes we increment the version ourselves
    version = version + 1

    assert response.json()["success"]
    # request that all wds pull the new model for the device
    admin_websocket.send_json(
        {"action": "requestPullLatestModel", "info": {"deviceName": deviceName, "modelID": alarm_modelID}})
    # concurrency problem here, the server first sends the command to all wds then to success to the admin, if truly parallel the order would not matter

    # so first the wds (the only other websocket) gets the command
    data = wd_websocket.receive_json()

    print("wd received: " + str(data))
    assert data["action"] == "pullLatestModel"
    assert data["info"]["deviceName"] == deviceName
    # now the wd should get the latest model via API
    response = client.get("/getLatestModelByDeviceName",
                          json={"token": AUTH_TOKEN, "deviceName": deviceName})

    assert response.status_code == 200
    assert response.json()["deviceName"] == deviceName
    assert response.json()["version"] == version
    assert sys.getsizeof(bytes(base64.b64decode(response.json()["modelBinary"]))) > 1

    # now the admin gets the success
    data = admin_websocket.receive_json()

    assert data["success"]

    # ping test, sanity check
    admin_websocket.send_json({"action": "ping"})
    data = admin_websocket.receive_json()
    assert data["success"]

    wd_websocket.send_json({"action": "disconnect"})
    data = wd_websocket.receive_json()
    assert data["success"]
    admin_websocket.send_json({"action": "disconnect"})
    data = admin_websocket.receive_json()
    assert data["action"] == "disconnect"

    time.sleep(0.1)
    wd_websocket.close()
    admin_websocket.close()
    time.sleep(0.1)


# TODO: send invalid bullshit to the server and hope it does not die
def testWebsocketNegative():
    wd_websocket = client.websocket_connect("/ws")

    wd_websocket.send_json({"action": "auth", "token": AUTH_TOKEN})
    data = wd_websocket.receive_json()

    assert data["success"]

    wd_websocket.send_json({"action": "roflcopter", "info": "lmao"})
    data = wd_websocket.receive_json()

    assert not data["success"]

    # send and directly close
    wd_websocket.send_json({"action": "ping"})
    wd_websocket.close()


def testWebsocketNegative_auth():
    wd_websocket = client.websocket_connect("/ws")

    # alter signature somehow to check for an invalid signature
    invalid_auth_token = copy.deepcopy(AUTH_TOKEN)
    index_to_replace = random.randint(1, len(invalid_auth_token["signature"]))
    replace_char = "="
    assert invalid_auth_token["signature"][index_to_replace] != replace_char
    invalid_auth_token["signature"] = invalid_auth_token["signature"][:index_to_replace] + \
                                      replace_char + invalid_auth_token["signature"][index_to_replace + 1:]
    assert invalid_auth_token["signature"][index_to_replace] == replace_char

    wd_websocket.send_json({"action": "auth", "token": invalid_auth_token})
    data = wd_websocket.receive_json()
    assert not data["success"]


try:
    test()
    print("Successfully completed test\n")

    testStoreModel()
    print("Successfully completed testStoreModel")
    # increment version for further tests
    version = version + 1
    testAuthNegative()
    print("Successfully completed testAuthNegative\n")

    testGetModelByDeviceNamePositive()
    print("Successfully completed testGetModelByDeviceNamePositive\n")
    testGetModelByDeviceNameNegative()
    print("Successfully completed testGetModelByDeviceNameNegative\n")

    testGetLatestModelByDeviceNamePositive()
    print("Successfully completed testGetLatestModelByDeviceNamePositive\n")
    testGetLatestModelByDeviceNameNegative()
    print("Successfully completed testGetLatestModelByDeviceNameNegative\n")

    testModelVersionNumber()
    print("Successfully completed testModelVersionNumber\n")

    print("''''''''''''''''''''''''''''' Testing Websocket '''''''''''''''''''''''''''''")
    testWebsocket()
    print("Successfully completed testWebsocket\n")
    testWebsocketNegative()
    print("Successfully completed testWebsocketNegative\n")
    testWebsocketNegative_auth()
    print("Successfully completed testWebsocketNegative_auth\n")
    print("'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''")



finally:
    # Cleanup
    cursor.execute("DELETE FROM alarms")
    cursor.execute("DELETE FROM wds")
    cursor.execute("DELETE FROM devices")
    cursor.execute("DELETE FROM models")
    conn.commit()
    cursor.close()
    conn.close()
    print("Done")

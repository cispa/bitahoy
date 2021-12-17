from fastapi.testclient import TestClient
from app import app
# from enums import DeviceType
import json
import requests
import psycopg2

import time
import random
import copy
from backend_lib.websocket_manager import WebsocketManager
from backend_lib.auth import Auth, Expired, VerificationFailed, InvalidToken

from app import updateRelation, updateType, updateConfig, selectConfig, isDefaultConfig

random.seed(42)

client = TestClient(app)
conn = psycopg2.connect("dbname='adn_db' user='adn_db' host='adn_db' [redacted-2]")
cursor = conn.cursor()

# Sample Addon entry to store and retrieve
addonName = "Adblock"
deviceName = "Google Alexa"
gitURL = "https://www.bitahoy.com"
commitHash = "fa60d138bacf14e47bc2704e73095bd083877681"
defaultConfig = {'ports': [0,0,0], 'flag': True, 'foo': 'bar'}

#### Setup clients for testing

AUTH_URL = "http://auth.bitahoy.cloud" # "http://auth" #old Marius dev addressing

# auth = Auth(AUTH_URL)

client = TestClient(app)  # This opens an additional Xth connection to the ZMQ server

wdcode = "xxxxxxxxxxxxxxxx"
secret= "[redacted-7]"
response = requests.get(AUTH_URL + "/authenticateWatchdog", json={"wdcode": wdcode, "secret": secret})
assert response.status_code == 200
assert response.json()["success"] == True
assert response.json()["token"] != None
AUTH_TOKEN = response.json()["token"]

# Another WD for tests
wdcode2 = "xxxxxxxxxxxxxxxx"
secret2 = "[redacted-7]"
response2 = requests.get(AUTH_URL + "/authenticateWatchdog", json={"wdcode": wdcode2, "secret": secret2})
assert response2.json()["success"] == True
assert response2.json()["token"] != None
AUTH_TOKEN2 = response2.json()["token"]

# User interaction
TEST_EMAIL = "roman-3000000000000045@testing.bitahoy.com"
password = "[redacted-6]"
response3 = requests.post(AUTH_URL + "/login", json={"email": TEST_EMAIL, "password": password})
assert response3.status_code == 200
# print(response3.json())
assert response3.json()["success"] == True
assert response3.json()["token"] != None
USER_AUTH_TOKEN = response3.json()["token"]


def connect_WS(authToken):
    websocket = client.websocket_connect("/ws")
    websocket.send_json({"action": "auth", "token": authToken})
    data = websocket.receive_json()
    assert data["success"]
    # Authenticated!
    return websocket

def disconnect_WS(usr_websocket):
    usr_websocket.send_json({"action": "disconnect"})
    data = usr_websocket.receive_json()
    assert data["success"]

    time.sleep(0.1)
    usr_websocket.close()


def test():
    response = client.get("/")
    assert response.status_code == 200
    time.sleep(0.5)

# given Addon data, add to db
def testUpdateAddon(addonName, gitURL, commitHash, defaultConfig):
    usr_websocket = connect_WS(USER_AUTH_TOKEN)

    # ping test, sanity check
    usr_websocket.send_json({"action": "ping"})
    data = usr_websocket.receive_json()
    assert data["success"]

    time.sleep(0.5)

    usr_websocket.send_json(
        {"action": "modifyType", "info":
            {"timestamp": int(time.time()),"addonName": addonName,
                                                "gitURL": gitURL, "commitHash": commitHash , "defaultConfig": defaultConfig
             }
         })

    data = usr_websocket.receive_json()
    # print(data)

    if not (data["success"]):
        # Cleanup
        cursor.execute("DELETE FROM wds")
        cursor.execute("DELETE FROM addons")
        cursor.execute("DELETE FROM configs")

        conn.commit()
        # cursor.close()
        # conn.close()
        print("EXTRAAAAAAAAAA Cleanup Done!")
        usr_websocket.send_json(
            {"action": "modifyType", "info":
                {"timestamp": int(time.time()), "addonName": addonName,
                 "gitURL": gitURL, "commitHash": commitHash , "defaultConfig": defaultConfig
                 }
             })

        data = usr_websocket.receive_json()
        assert data["success"]
        assert data["comment"] == 'Created a new entry, as no such Type exists in the Type Table'

    time.sleep(0.5)

    cursor.execute("SELECT * FROM addons WHERE addonName=%s", (addonName,))
    result = cursor.fetchone()

    assert result[0] == addonName
    assert result[1] == gitURL
    assert result[2] == commitHash
    # cfg = json.loads(result[3].tobytes())
    result_config = selectConfig(result[3])
    assert result_config == defaultConfig

    usr_websocket.send_json(
        {"action": "getType", "info":
            {"timestamp": int(time.time()), "addonName": addonName}
         })

    data = usr_websocket.receive_json()
    # print(data)
    assert data["success"]

    time.sleep(0.5)

    usr_websocket.send_json(
        {"action": "getType", "info":
            {"timestamp": int(time.time())}
         })

    data = usr_websocket.receive_json()
    # print(data)
    assert data["success"]
    
    time.sleep(0.5)

    usr_websocket.send_json(
        {"action": "modifyType", "info":
            {"timestamp": int(time.time()),"addonName": "Security",
                                                "gitURL": gitURL, "commitHash": commitHash , "defaultConfig": defaultConfig
             }
         })

    data = usr_websocket.receive_json()
    # print(data)
    
    time.sleep(0.5)
    
    disconnect_WS(usr_websocket)

def testUninstallAddon():
    cursor.execute("SELECT * FROM addons WHERE addonName=%s", (addonName,))
    result = cursor.fetchone()

    assert result[0] == addonName

    # response = client.post("/uninstallAddon", json={"token": USER_AUTH_TOKEN, "addonName": "testNameNoAddonExists"})
    #
    # assert response.status_code == 200
    #
    # assert response.json()["success"] == False

    wd_websocket = connect_WS(AUTH_TOKEN)
    # now connect user
    usr_websocket = connect_WS(USER_AUTH_TOKEN)
    usr_websocket.send_json(
        {"action": "uninstallAddon", "info":
            {"timestamp": int(time.time()), "addonName": "testNameNoAddonExists"}
         })

    data = usr_websocket.receive_json()
    assert not data["success"]
    time.sleep(0.5)

    cursor.execute("SELECT * FROM wds WHERE wdcode=%s AND addonName=%s", (wdcode, addonName))
    keep_for_later = cursor.fetchall()

    # response = client.post("/uninstallAddon", json={"token": USER_AUTH_TOKEN, "addonName": addonName})
    #
    # assert response.status_code == 200
    # assert response.json()["success"]
    usr_websocket.send_json(
        {"action": "uninstallAddon", "info":
            {"timestamp": int(time.time()), "addonName": addonName}
         })

    data = wd_websocket.receive_json()
    assert data["success"]
    time.sleep(0.5)

    data = usr_websocket.receive_json()
    assert data["success"]
    time.sleep(0.5)


    cursor.execute("SELECT * FROM wds WHERE wdcode=%s AND addonName=%s", (wdcode, addonName,))
    result = cursor.fetchone()

    assert result is None

    for i in keep_for_later:
        if isDefaultConfig(i[-1]):  # == default_config_id): #  make sure we don't remove the defaultConfig for this Addon
            continue
        cursor.execute("SELECT * FROM configs WHERE configID=%s", (i[-1],))
        result = cursor.fetchone()

        assert result is None

    response = client.get("/")
    assert response.status_code == 200

    disconnect_WS(usr_websocket)
    disconnect_WS(wd_websocket)

def testRemoveType():
    cursor.execute("SELECT * FROM addons WHERE addonName=%s", (addonName,))
    result = cursor.fetchone()

    assert result[0] == addonName

    # response = client.post("/removeType", json={"token": USER_AUTH_TOKEN, "addonName": "testNameNoAddonExists"})
    #
    # assert response.status_code == 200
    #
    # assert response.json()["success"] == False

    # now connect user
    usr_websocket = connect_WS(USER_AUTH_TOKEN)

    usr_websocket.send_json(
        {"action": "removeType", "info":
            {"timestamp": int(time.time()), "addonName": "testNameNoAddonExists"}
         })

    # first check that the WD recieves the msg
    data = usr_websocket.receive_json()
    assert not data["success"]

    time.sleep(0.5)

    cursor.execute("SELECT * FROM wds WHERE addonName=%s", (addonName,))
    keep_for_later = cursor.fetchall()

    # response = client.post("/removeType", json={"token": USER_AUTH_TOKEN, "addonName": addonName})
    #
    # assert response.status_code == 200
    # assert response.json()["success"]
    usr_websocket.send_json(
        {"action": "removeType", "info":
            {"timestamp": int(time.time()), "addonName": addonName}
         })

    # first check that the WD recieves the msg
    data = usr_websocket.receive_json()
    assert data["success"]
    assert data["addonName"] == addonName

    time.sleep(0.5)

    cursor.execute("SELECT * FROM addons WHERE addonName=%s", (addonName,))
    result = cursor.fetchone()

    assert result is None

    cursor.execute("SELECT * FROM wds WHERE addonName=%s", (addonName,))
    result = cursor.fetchone()

    assert result is None

    for i in keep_for_later:
        cursor.execute("SELECT * FROM configs WHERE configID=%s", (i[-1],))
        result = cursor.fetchone()

        assert result is None

    response = client.get("/")
    assert response.status_code == 200

    disconnect_WS(usr_websocket)
# installAddon a Null relation and test again to make sure
def installAddon():
    ## check if WD gets the Event
    wd_websocket = connect_WS(AUTH_TOKEN)

    # ping test on WD
    wd_websocket.send_json({"action": "ping"})
    data = wd_websocket.receive_json()
    assert data["success"]
    time.sleep(0.5)

    # now connect user
    usr_websocket = connect_WS(USER_AUTH_TOKEN)
    usr_websocket.send_json(
        {"action": "installAddon", "info":
            {"timestamp": int(time.time()), "addonName": addonName}
         })

    # first check that the WD recieves the msg
    data = wd_websocket.receive_json()
    assert data["success"]
    assert data["addonName"] == addonName
    time.sleep(0.5)

    # now check that the use receives his
    data = usr_websocket.receive_json()
    assert data["success"]

    time.sleep(0.5)

    # now test fail
    usr_websocket.send_json(
        {"action": "installAddon", "info":
            {"timestamp": int(time.time()), "addonName": addonName}
         })
    data = usr_websocket.receive_json()
    assert not data["success"]

    time.sleep(0.5)

    disconnect_WS(usr_websocket)
    disconnect_WS(wd_websocket)

# given NEW Addon data, update the old Addon entry
# first check if update available, if yes update code
def testUpdateExistingAddon():
    # simply change URL
    newGitURL = gitURL + "?idk"

    usr_websocket = connect_WS(USER_AUTH_TOKEN)

    # ping test, sanity check
    usr_websocket.send_json({"action": "ping"})
    data = usr_websocket.receive_json()
    assert data["success"]

    time.sleep(0.5)

    # sanity check, no safe_edit flag
    usr_websocket.send_json(
        {"action": "modifyType", "info":
            {"timestamp": int(time.time()), "addonName": addonName,
                                                 "gitURL": newGitURL, "commitHash": commitHash, "defaultConfig": defaultConfig }
         })

    data = usr_websocket.receive_json()
    assert not data["success"]

    time.sleep(0.5)

    usr_websocket.send_json(
        {"action": "modifyType", "info":
            {"timestamp": int(time.time()), "addonName": addonName,
                                                 "gitURL": newGitURL, "commitHash": commitHash, "defaultConfig": defaultConfig, "safe_edit": True }
         })

    data = usr_websocket.receive_json()
    # print(data["comment"])
    assert data["success"]
    assert data["comment"] == "safe_edit flag was supplied - updating an existing (addon)Type, thus overwritting an existing entry"

    time.sleep(0.5)


    cursor.execute("SELECT * FROM addons WHERE addonName=%s", (addonName,))
    result = cursor.fetchone()

    assert result[0] == addonName
    assert result[1] == newGitURL
    assert result[2] == commitHash
    # cfg = json.loads(result[3].tobytes())
    # assert cfg == defaultConfig
    cursor.execute("SELECT config FROM configs WHERE configID=%s", (result[3],))
    result = cursor.fetchone()
    assert json.loads(result[0].tobytes()) == defaultConfig


    disconnect_WS(usr_websocket)

# given wdcode, AddonID, DeviceName and Config data, add to db
# can also be used to UPDATE an existing config!!!
def testModifyConfig():
    # setup WS user
    usr_websocket = connect_WS(USER_AUTH_TOKEN)

    # sanity check - missing config
    usr_websocket.send_json(
        {"action": "modifyAddon", "info":
            {"timestamp": int(time.time()),
             "addonName": addonName,
             "deviceName": deviceName}
         })

    data = usr_websocket.receive_json()
    assert not data["success"]
    # print(data)
    assert data["comment"].startswith("One of the optional fields for enabled OR") # == "Incomplete request form: config"

    time.sleep(0.5)

    newconfig = {'ports': [21, 22, 23], 'flag': True, 'foo': 'bar'}

    # sanity check - not existing relation
    usr_websocket.send_json(
        {"action": "modifyAddon", "info":
            {"timestamp": int(time.time()),
             "addonName": "no_such_addon",
             "deviceName": deviceName,
             "config": newconfig}
         })

    data = usr_websocket.receive_json()
    assert not data["success"]
    assert data["comment"].startswith("No such relation exists, ")

    time.sleep(0.5)

    # this time for real - so we ned a wd
    wd_websocket = connect_WS(AUTH_TOKEN)

    usr_websocket.send_json(
        {"action": "modifyAddon", "info":
            {"timestamp": int(time.time()),
             "addonName": addonName,
             "deviceName": deviceName,
             "config": newconfig}
         })

    data = wd_websocket.receive_json()
    assert data["success"]
    assert data["addonName"] == addonName

    time.sleep(0.5)

    data = usr_websocket.receive_json()
    assert data["success"]
    # assert data["comment"] == 'null-device is the only relation found, created a new relation for this deviceName'

    time.sleep(0.5)

    # now try to change the config
    newconfig2 = {'ports': [666], 'flag': False, 'foo': 'bar'}

    usr_websocket.send_json(
        {"action": "modifyAddon", "info":
            {"timestamp": int(time.time()),
             "addonName": addonName,
             "deviceName": deviceName,
             "config": newconfig2}
         })

    data = wd_websocket.receive_json()
    assert data["success"]
    assert data["addonName"] == addonName

    time.sleep(0.5)

    data = usr_websocket.receive_json()
    assert data["success"]
    # assert data["comment"].startswith("One o..")

    # check by querying DB
    cursor.execute(
        "SELECT wds.configID FROM wds WHERE addonName=%s and wdcode=%s and deviceName=%s ORDER BY configID DESC LIMIT 1",
        (addonName, wdcode, deviceName))
    conn.commit()
    result = cursor.fetchone()
    result_config = selectConfig(result[-1])
    assert result_config == newconfig2

    time.sleep(0.5)

    # TEST9: disconnect WS
    disconnect_WS(usr_websocket)
    disconnect_WS(wd_websocket)


def addAnotherAddonConfig():
    # add another enrty to the two tables and re-run previous tests
    # insert another conifg, to make sure
    # first need another Addon, to be sure
    print("populate some more addons and configs....")
    addonName2 = 'deprecatedAddon v0.2'
    deviceName2 = "sonos Jump"
    gitURL2 = "https://www.bitahoy.com@"
    commitHash2 = "fakkd138bacf14e47bc2704e73095bd083877681"
    bytesDict2 = json.dumps({'ports': [666], 'flag': False})
    defaultConfig2 = {'ports': [666], 'flag': False}
    # manually add new Addon and new config+(wdXdeviceXaddon) into the DB
    configID2 = updateConfig(bytesDict2)
    updateType(addonName2, gitURL2, commitHash2, configID2)
    updateRelation(wdcode, addonName2, deviceName2, configID2)

    # now check if the results of the two previous tests work
    # testUpdateAddon(addonName2, gitURL2, commitHash2, {'ports': [666], 'flag': False})
    usr_websocket = connect_WS(USER_AUTH_TOKEN)

    usr_websocket.send_json(
        {"action": "modifyType", "info":
            {"timestamp": int(time.time()), "addonName": addonName2,
                                                "gitURL": gitURL2, "commitHash": commitHash2,
                                                "defaultConfig": defaultConfig2, "safe_edit": True
             }
         })

    data = usr_websocket.receive_json()
    # print(data["comment"])
    assert data["success"]

    disconnect_WS(usr_websocket)

    cursor.execute("SELECT * FROM addons WHERE addonName=%s", (addonName2,))
    result = cursor.fetchone()

    assert result[0] == addonName2
    assert result[1] == gitURL2
    assert result[2] == commitHash2
    # cfg = json.loads(result[3].tobytes())
    result_config = selectConfig(result[3])
    assert result_config == defaultConfig2
    print("now run testModifyConfig() again")
    testModifyConfig()

# just fetch ALL available addon Types
def getTypeCatalog():
    addonName2 = 'deprecatedAddon'
    deviceName2 = "sonos Jump"
    gitURL2 = "https://www.bitahoy.com@"
    commitHash2 = "fakkd138bacf14e47bc2704e73095bd083877681"
    defaultConfig = json.dumps({"field": None})

    configID = updateConfig(defaultConfig)
    updateType(addonName2, gitURL2, commitHash2, configID)

    cursor.execute("SELECT addons.addonName, addons.gitURL, addons.commitHash, addons.defaultConfigID FROM addons", ())
    result = cursor.fetchall()

    # use WebSockets instead
    usr_websocket = connect_WS(USER_AUTH_TOKEN)

    # when no AddonName is given, getType returns the whole cataloge
    usr_websocket.send_json(
        {"action": "getType",
         "info": {"timestamp": int(time.time())}
         })

    data = usr_websocket.receive_json()

    # print(data)
    assert data["success"]
    types = data["typesList"]

    time.sleep(0.5)

    # now check actuall results
    for (i, j) in list(zip(result, types)):
        assert i[0] == j["addonName"]
        assert i[1] == j["gitURL"]
        assert i[2] == j["commitHash"]
        assert selectConfig(i[3]) == j["defaultConfig"]

    time.sleep(0.5)

    disconnect_WS(usr_websocket)

# help fucntion for the test below
def populateMoreStuff():
    addonName2 = 'ML addon v1.666'
    deviceName2 = "Smart Fridge"
    gitURL2 = "https://www.bitahoy.com@"
    commitHash2 = "beefd138bacf14e47bc2704e73095bd083877681"
    defaultConfig2 = ({"field": None})

    usr_websocket = connect_WS(USER_AUTH_TOKEN)

    usr_websocket.send_json(
        {"action": "modifyType", "info":
            {"timestamp": int(time.time()),
             "addonName": addonName2, "gitURL": gitURL2, "commitHash": commitHash2,
                         "defaultConfig": defaultConfig2}
         })

    data = usr_websocket.receive_json()
    assert data["success"]

    # response = client.post("/installAddon", json={"token": USER_AUTH_TOKEN, "addonName": addonName2})
    # assert response.status_code == 200
    # assert response.json()["success"]

    usr_websocket.send_json(
        {"action": "installAddon", "info":
            {"timestamp": int(time.time()), "addonName": addonName2}
         })

    data = usr_websocket.receive_json()
    assert data["success"]

    newconfig2 = {'ports': [21,22,23], 'flag': True, 'foo': 'bar'}

    # sanity check
    usr_websocket.send_json(
        {"action": "modifyAddon", "info":
            {"timestamp": int(time.time()),
             "addonName": addonName2,
             "deviceName": deviceName2,
             "config": newconfig2}
         })

    data = usr_websocket.receive_json()
    assert data["success"]

    time.sleep(0.5)

    disconnect_WS(usr_websocket)

    ########## NOW SECONDS USER - WS dicsonnec tand conenct another

    usr_websocket = client.websocket_connect("/ws")
    usr_websocket.send_json({"action": "auth", "token": AUTH_TOKEN2})
    data = usr_websocket.receive_json()
    assert data["success"]
    # Authenticated!

    addonName2 = 'ML addon v1.666'
    deviceName2 = "Dumb sofa"
    gitURL2 = "https://www.bitahoy.com@"
    commitHash2 = "deadd138bacf14e47bc2704e73095bd083877681"
    defaultConfig2 = ({"field": None})

    usr_websocket.send_json(
        {"action": "installAddon", "info":
            {"timestamp": int(time.time()), "addonName": addonName2}
         })

    data = usr_websocket.receive_json()
    assert data["success"]

    usr_websocket.send_json(
        {"action": "modifyType", "info":
            {"timestamp": int(time.time()),
             "addonName": addonName2,
             "gitURL": gitURL2, "commitHash": commitHash2,
             "defaultConfig": defaultConfig2, "safe_edit": True}
         })

    data = usr_websocket.receive_json()
    assert data["success"]

    time.sleep(0.5)

    newconfig2 = {'ports': [21,22,23], 'flag': True, 'foo': 'bar'}

    usr_websocket.send_json(
        {"action": "modifyAddon", "info":
            {"timestamp": int(time.time()),
             "addonName": addonName2,
             "deviceName": deviceName2,
             "config": newconfig2}
         })

    data = usr_websocket.receive_json()
    assert data["success"]

    time.sleep(0.5)

    disconnect_WS(usr_websocket)
# just fetch ALL getInstalledTypes, regardless of deviceNames
def getInstalledTypes():
    # first populate the db with more addosn and devices
    populateMoreStuff()

    cursor.execute(
        "SELECT wds.addonName, wds.deviceName, wds.enabled, wds.configID, addons.gitURL, addons.commitHash, addons.defaultConfigID FROM wds LEFT JOIN addons ON wds.addonName = addons.addonName WHERE wds.wdcode=%s",
        (wdcode,))
    conn.commit()
    result = cursor.fetchall()

    usr_websocket = connect_WS(USER_AUTH_TOKEN)

    # ping test, sanity check
    usr_websocket.send_json({"action": "ping"})
    data = usr_websocket.receive_json()
    assert data["success"]

    time.sleep(0.5)

    usr_websocket.send_json(
        {"action": "getAddon", "info":
             {"timestamp": int(time.time())}
         })

    data = usr_websocket.receive_json()
    # print(data)
    assert data["success"]
    addons = data["addonsList"]

    # now check actuall results
    for (i, j) in list(zip(result, addons)):
        assert i[0] == j["addonName"]
        assert i[1] == j["deviceName"]
        assert i[2] == j["enabled"]
        assert selectConfig(i[3]) == j["config"]

    disconnect_WS(usr_websocket)

# given addonID, get info about addon
def testTypeInfo():
    usr_websocket = connect_WS(USER_AUTH_TOKEN)

    # ping test, sanity check
    usr_websocket.send_json({"action": "ping"})
    data1 = usr_websocket.receive_json()
    # print("tst ping: wd received: " + str(data1))
    assert data1["success"]

    time.sleep(0.5)

    # TEST0: dry test on new WS
    usr_websocket.send_json(
        {"action": "getType",
         "info":
            {"timestamp": int(time.time()),
             "addonName": addonName}
         })

    data = usr_websocket.receive_json()
    # print("tst WStest: wd received: " + str(data2))
    assert data["success"]
    response = data["type"]

    time.sleep(0.5)

    # now fetch same dict manually from DB and compare
    cursor.execute("SELECT * FROM addons WHERE addonName=%s", (addonName,))
    result = cursor.fetchone()

    addonNameRet = result[0]
    gitURLRet = result[1]
    commitHashRet = result[2]
    defaultConfig = selectConfig(result[3])

    assert response["addonName"] == addonNameRet
    assert response["gitURL"] == gitURLRet
    assert response["commitHash"] == commitHashRet
    assert response["defaultConfig"] == defaultConfig

    disconnect_WS(usr_websocket)

# # Invalid Authentication Signature Test
# # auth will be replaced with shared library that all API endpoints use so 1 test is enough
def testAuthNegative():
    # alter signature somehow to check for an invalid signature
    invalid_auth_token = copy.deepcopy(USER_AUTH_TOKEN)
    index_to_replace = random.randint(1, len(invalid_auth_token["signature"]))
    replace_char = "@"
    assert invalid_auth_token["signature"][index_to_replace] != replace_char #check we're not replacing the cahr with an indentical one

    invalid_auth_token["signature"] = invalid_auth_token["signature"][:index_to_replace] + \
                            replace_char + invalid_auth_token["signature"][index_to_replace + 1:]
    assert invalid_auth_token["signature"][index_to_replace] == replace_char

    usr_websocket = client.websocket_connect("/ws")
    usr_websocket.send_json({"action": "auth", "token": invalid_auth_token})
    data = usr_websocket.receive_json()
    assert not data["success"]

# taken from ML_service
def testWebsocketNEW():
    # setup WS
    usr_websocket = connect_WS(USER_AUTH_TOKEN)
    # ping test, sanity check
    usr_websocket.send_json({"action": "ping"})
    data1 = usr_websocket.receive_json()
    # print("tst ping: wd received: " + str(data1))
    assert data1["success"]

    time.sleep(0.5)

    # TEST9: disconnect WS
    disconnect_WS(usr_websocket)


def testInsertConfig():
    # setup WS
    usr_websocket = connect_WS(USER_AUTH_TOKEN)

    # ping test, sanity check
    usr_websocket.send_json({"action": "ping"})
    data = usr_websocket.receive_json()
    assert data["success"]

    time.sleep(0.5)

    # sanity check, no config supplied
    usr_websocket.send_json(
        {"action": "insertConfig", "info":
            {"timestamp": int(time.time()),
             }
         })

    data = usr_websocket.receive_json()

    assert not data["success"]
    # print(data)
    # assert data["comment"] == "No config supplied. Please check inputs."

    time.sleep(0.5)

    non_existing_config = {'ports': [21, 22, 23], 'flag': True, 'foo': 'bar'}

    usr_websocket.send_json(
        {"action": "insertConfig", "info":
             {"timestamp": int(time.time()),
              "config": non_existing_config}
         })

    data = usr_websocket.receive_json()
    assert data["success"]

    assert non_existing_config == data["config"]
    # print(data)
    # assert data["comment"] == "No config exists for this WD code. Created new entry."

    time.sleep(0.5)

    new_config = {'ports': [666], 'flag': False, 'foo': 'bar'}

    # now try to overwrite it
    usr_websocket.send_json(
        {"action": "insertConfig", "info":
            {"timestamp": int(time.time()),
             "config": new_config}
         })

    data = usr_websocket.receive_json()
    # print("tst WSgetConfig: wd received: " + str(data))
    assert data["success"]

    assert new_config == data["config"]
    # assert data["comment"] == "Found an existing config for this WD code. Overwriting existing with new."

    time.sleep(0.5)

    disconnect_WS(usr_websocket)

def testGetConfig():
    usr_websocket = connect_WS(USER_AUTH_TOKEN)

    # ping test, sanity check
    usr_websocket.send_json({"action": "ping"})
    data = usr_websocket.receive_json()
    assert data["success"]

    time.sleep(0.5)

    existing_config = {'ports': [666], 'flag': False, 'foo': 'bar'}

    # just get it already
    usr_websocket.send_json(
        {"action": "getAddon", "info":
             {"timestamp": int(time.time()),
              "addonName": addonName,
              "deviceName": deviceName}
         })

    data = usr_websocket.receive_json()
    # print("tst WSgetConfig: wd received: " + str(data))
    assert data["success"]
    config = data["addon"]["config"]
    assert existing_config == config

    time.sleep(0.5)

    # what about a wrong relation - how about a device that doesnt exists, expect a NULL device for return
    usr_websocket.send_json(
        {"action": "getAddon", "info":
             {"timestamp": int(time.time()),
              "addonName": addonName,
              "deviceName": "no_such_device"}
         })

    data = usr_websocket.receive_json()
    # print("tst WSgetConfig: wd received: " + str(data))
    assert not data["success"]
    assert data["comment"] == 'No addons for this addonName and/or deviceName were found, did you install any Addons for this wdcode?'

    # "no such relation exists, be it either for this deviceName OR for a NULL device. please check that you have installed the addon on this wd"
    # "null-device is the only relation found, returning defaultConfig for this addonName"
    time.sleep(0.5)

    # what about a wrong relation
    usr_websocket.send_json(
        {"action": "getAddon", "info":
             {"timestamp": int(time.time()),
              "addonName": "no Such Addon",
              "deviceName": deviceName}
         })

    data = usr_websocket.receive_json()
    # print("tst WSgetConfig: wd received: " + str(data))
    assert not data["success"]
    # assert data["comment"] == "no such relation exists, be it either for this deviceName OR for a NULL device. please check that you have installed the addon on this wd"

    time.sleep(0.5)

    disconnect_WS(usr_websocket)

def testSetEnabled():
    # setup WS
    usr_websocket = connect_WS(USER_AUTH_TOKEN)

    # TEST3: App requests to flip ENABLED bool for a wdcodeXdeviceXaddon
    # simple POST select
    cursor.execute(
        "SELECT enabled FROM wds WHERE addonName=%s and wdcode=%s and deviceName=%s ORDER BY configID DESC LIMIT 1",
        (addonName, wdcode, deviceName))
    conn.commit()
    result = cursor.fetchone()
    post_answer_bool = result[0]

    assert post_answer_bool # Addons are enabled per default

    # use WS to set it to False
    usr_websocket.send_json(
        {"action": "modifyAddon", "info":
            {"timestamp": int(time.time()),
             "addonName": addonName,
             "deviceName": deviceName,
             "enabled": False}
         })

    data = usr_websocket.receive_json()
    print(data)
    assert data["success"]

    answer_bool = data["enabled"]
    assert not answer_bool # check return

    # now try to "overwrite" it with same value, sanity check
    usr_websocket.send_json(
        {"action": "modifyAddon", "info":
            {"timestamp": int(time.time()),
             "addonName": addonName,
             "deviceName": deviceName,
             "enabled": False}
         })

    data = usr_websocket.receive_json()
    assert data["success"]

    answer_bool_2 = data["enabled"]
    assert not answer_bool_2 # same result as before

    # now we set it back to True
    usr_websocket.send_json(
        {"action": "modifyAddon", "info":
            {"timestamp": int(time.time()),
             "addonName": addonName,
             "deviceName": deviceName,
             "enabled": True}
         })

    data = usr_websocket.receive_json()
    assert data["success"]

    answer_bool_2 = data["enabled"]
    assert answer_bool_2  # should return True, like we set

    # check by selecting DB
    cursor.execute(
        "SELECT enabled FROM wds WHERE addonName=%s and wdcode=%s and deviceName=%s ORDER BY configID DESC LIMIT 1",
        (addonName, wdcode, deviceName))
    conn.commit()
    result = cursor.fetchone()
    post_answer_bool_2 = result[0]

    assert post_answer_bool_2

    time.sleep(0.5)

    # TEST9: disconnect WS
    disconnect_WS(usr_websocket)

# TODO: send invalid bullshit to the server and hope it does not die
def testWebsocketNegative():
    usr_websocket = client.websocket_connect("/ws")

    usr_websocket.send_json({"action": "auth", "token": USER_AUTH_TOKEN})
    data = usr_websocket.receive_json()

    assert data["success"]

    usr_websocket.send_json({"action": "roflcopter", "info": "lmao"})
    data = usr_websocket.receive_json()

    assert not data["success"]

    usr_websocket.send_json({"action": "disconnect"})
    data = usr_websocket.receive_json()

    assert data["success"]
    assert data["action"] == "disconnect"

    time.sleep(0.1)
    usr_websocket.close()
    time.sleep(0.1)


def testWebsocketNegative_auth():
    usr_websocket = client.websocket_connect("/ws")

    # alter signature somehow to check for an invalid signature
    invalid_auth_token = copy.deepcopy(USER_AUTH_TOKEN)
    index_to_replace = random.randint(1, len(invalid_auth_token["signature"]))
    replace_char = "="
    assert invalid_auth_token["signature"][index_to_replace] != replace_char
    invalid_auth_token["signature"] = invalid_auth_token["signature"][:index_to_replace] + \
                                      replace_char + invalid_auth_token["signature"][index_to_replace + 1:]
    assert invalid_auth_token["signature"][index_to_replace] == replace_char

    usr_websocket.send_json({"action": "auth", "token": invalid_auth_token})
    data = usr_websocket.receive_json()

    assert not data["success"]

    disconnect_WS(usr_websocket)


try:
    test()
    print("----Successfully completed SanityTest\n")
    testUpdateAddon(addonName, gitURL, commitHash, defaultConfig)
    print("----Successfully completed testUpdateAddon\n")
    testUpdateExistingAddon()
    print("----Successfully completed testUpdateExistingAddon\n")
    installAddon()
    print("----Successfully completed installAddon\n")
    testModifyConfig()
    print("----Successfully completed testUpdateConfig\n")
    addAnotherAddonConfig()
    print("----Successfully completed addAnotherAddonConfig\n")
    getTypeCatalog()
    print("----Successfully completed getTypeCatalog\n")
    testTypeInfo()
    print("----Successfully completed testTypeInfo\n")
    testAuthNegative()
    print("----Successfully completed testAuthNegative\n")
    getInstalledTypes()
    print("----Successfully completed getInstalledTypes\n")

    testWebsocketNEW()
    print("----Successfully completed testWebsocketNEW\n")
    testWebsocketNegative()
    print("----Successfully completed testWebsocketNegative\n")
    testGetConfig()
    print("----Successfully completed testGetConfig\n")
    testSetEnabled()
    print("----Successfully completed testWebsocketFlipEnabled\n")


    testUninstallAddon()
    print("----Successfully completed testUninstallAddon\n")

    testRemoveType()
    print("----Successfully completed testRemoveAddon\n")

finally:
    # Cleanup
    cursor.execute("DELETE FROM wds")
    cursor.execute("DELETE FROM addons")
    cursor.execute("DELETE FROM configs")

    conn.commit()
    cursor.close()
    conn.close()
    print("Cleanup Done!")

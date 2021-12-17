from fastapi import FastAPI, Request, HTTPException
import psycopg2
import requests
from requests.exceptions import Timeout
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from starlette.websockets import WebSocket, WebSocketState
import asyncio
import time
import base64
import json
from enums import DeviceType
import sys
import os
from backend_lib.websocket_manager import WebsocketManager
from backend_lib.auth import Auth, Expired, VerificationFailed, InvalidToken
import traceback

app = FastAPI()

# Database connection
conn = psycopg2.connect("dbname='db' user='db' host='{}' password='{}'".format(os.environ.get("DB_HOST"), os.environ.get("DB_PASS")))
conn.autocommit = True
cursor = conn.cursor()

# AUTH_URL = "http://192.168.175.21"
AUTH_URL = "https://auth.bitahoy.cloud"
auth = Auth(AUTH_URL)

TIMEOUT = 120000


class InternalServerError(Exception):
    pass


@app.get("/")
def read_root():
    cursor.execute("""SELECT 'World!'""")
    rows = cursor.fetchall()
    return {"Hello": rows}


def authenticate(token):
    try:
        authenticatedClient = auth.verify(token)
        return authenticatedClient, ""
    except Expired:
        return None, "Token expired"
    except InvalidToken:
        return None, "Invalid Token"
    except VerificationFailed as e:
        print(token)
        print("Verification failed")
        return None, str(e)
    except Exception as err:
        print(err)
        return None, str(err)


# mapping wd to used model
async def updateWDModelMapping(wdcode, deviceName, modelID):
    # TODO: this query does not work (yet) so catch exception in python
    # cursor.execute("INSERT INTO wds VALUES(%s, %s, %s) ON CONFLICT (wdcode, modelID) DO UPDATE SET modelID=%s WHERE wds.wdcode=%s AND wds.deviceName=%s",
    #                (wdcode, deviceName, modelID, modelID, wdcode, deviceName))
    try:
        cursor.execute("INSERT INTO wds VALUES(%s, %s, %s)", (wdcode, deviceName, modelID))
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.commit()
        cursor.execute("UPDATE wds SET modelID=%s WHERE wdcode=%s AND deviceName=%s", (modelID, wdcode, deviceName))
        conn.commit()


# get model by specifying DeviceName (Unique ID) and version
@app.get("/getModelByDeviceName")
async def getModelByDeviceName(request: Request):
    data = json.loads(await request.body())
    try:
        # authenticate
        token = data["token"]
        authenticatedClient, comment = authenticate(token)
        if authenticatedClient is None:
            return {
                "success": False,
                "comment": comment
            }
        # authentication done

        # which wd pulled which model. stored in db at the end
        wdcode = authenticatedClient.code

        deviceName = data["deviceName"]
        version = data["version"]
        # With deviceName get the model assigned to that device. for that modelName get the model with the corresponding version
        cursor.execute("SELECT * FROM devices WHERE deviceName=%s", (deviceName,))
        conn.commit()
        result = cursor.fetchone()
        if result is None:
            raise InternalServerError

        deviceType = DeviceType(result[1])
        modelID = result[2]
        cursor.execute("SELECT modelName FROM models WHERE modelID=%s", (modelID,))
        conn.commit()
        result = cursor.fetchone()
        if result is None:
            raise InternalServerError

        cursor.execute("SELECT * FROM models WHERE modelName=%s AND version=%s", (result[0], version))
        conn.commit()
        result = cursor.fetchone()
        if result is None:
            raise InternalServerError

        # map wd to pulled model
        await updateWDModelMapping(wdcode, deviceName, modelID)

        return {
            "sucess": True,
            "deviceName": deviceName,
            "deviceType": deviceType.name,
            "modelName": result[1],
            "version": result[2],
            "modelBinary": base64.b64encode(result[3]).decode('utf-8'),
        }
    except KeyError:
        raise HTTPException(status_code=400, detail="Incomplete request form")
    except InternalServerError:
        return {
            "success": False,
            "comment": "Internal Server Error. Model not found."
        }


# same as /getModelByDeviceName but without requiring version
@app.get("/getLatestModelByDeviceName")
async def getLatestModelByDeviceName(request: Request):
    data = json.loads(await request.body())
    try:
        # authenticate
        token = data["token"]
        authenticatedClient, comment = authenticate(token)
        if authenticatedClient is None:
            return {
                "success": False,
                "comment": comment
            }
        # authentication done

        # which wd pulled which model. stored in db at the end
        wdcode = authenticatedClient.code

        deviceName = data["deviceName"]
        # With deviceName get the model assigned to that device. this is the latest model for that device
        cursor.execute("SELECT * FROM devices WHERE deviceName=%s", (deviceName,))
        conn.commit()
        result = cursor.fetchone()
        if result is None:
            raise InternalServerError

        deviceType = DeviceType(result[1])
        modelID = result[2]
        cursor.execute("SELECT * FROM models WHERE modelID=%s", (modelID,))
        conn.commit()
        result = cursor.fetchone()
        if result is None:
            raise InternalServerError

        # map wd to pulled model
        await updateWDModelMapping(wdcode, deviceName, modelID)

        return {
            "success": True,
            "deviceName": deviceName,
            "deviceType": deviceType.name,
            "modelName": result[1],
            "version": result[2],
            "modelBinary": base64.b64encode(result[3]).decode('utf-8'),
        }
    except KeyError:
        raise HTTPException(status_code=400, detail="Incomplete request form")
    except:
        return {
            "success": False,
            "comment": "Internal Server Error. Model not found."
        }


# TODO: write test for this
@app.get("/getAlarmsForDevice")
async def getAlarmsForDevice(request: Request):
    data = json.loads(await request.body())
    try:
        # authenticate
        token = data["token"]
        authenticatedClient, comment = authenticate(token)
        if authenticatedClient is None:
            return {
                "success": False,
                "comment": comment
            }
        # authentication done

        deviceName = data["deviceName"]

        cursor.execute("SELECT * FROM alarms WHERE deviceName=%s", (deviceName,))
        conn.commit()
        result = cursor.fetchall()

        return {
            "sucess": True,
            "data": result,
        }
    except KeyError:
        raise HTTPException(status_code=400, detail="Incomplete request form")
    except InternalServerError:
        return {
            "success": False,
            "comment": "Internal Server Error. Model not found."
        }


# stores model and updates the device table to point to correct model
# old models are not deleted to support rollback
# TODO: auth: multiple privilege levels (not anybody should be allowed to store models)
# TODO: somehow this return 500 when storing a model but does store the model (ML_test.py in setup_database() )
@app.post("/storeModel")
async def storeModel(request: Request):
    data = json.loads(await request.body())
    try:
        # authenticate
        token = data["token"]
        authenticatedClient, comment = authenticate(token)
        if authenticatedClient is None:
            return {
                "success": False,
                "comment": comment
            }
        # authentication done

        modelName = data["modelName"]
        deviceName = data["deviceName"]
        deviceType = DeviceType.from_name(data["deviceType"])

        modelBinary = bytes(base64.b64decode(data["modelBinary"]))

        # is this a device for which we already have stored a model?
        cursor.execute("SELECT modelID FROM devices WHERE deviceName=%s", (deviceName,))
        conn.commit()
        result = cursor.fetchall()
        # new model for new Device
        if len(result) == 0:
            version = 1
            # TODO: perhaps a Postgres wizard can fit this into one query
            cursor.execute("INSERT INTO models VALUES(DEFAULT, %s, %s, %s) RETURNING modelID",
                           (modelName, version, psycopg2.Binary(modelBinary)))
            conn.commit()
            modelID = cursor.fetchone()[0]

            cursor.execute("INSERT INTO devices VALUES(%s, %s, %s)",
                           (deviceName, deviceType, modelID))
            conn.commit()
        # new Model for known Device
        elif len(result) == 1:
            modelID = result[0]

            # get latest model version and increment
            cursor.execute("SELECT version FROM models WHERE modelID=%s", (modelID))
            conn.commit()
            result = cursor.fetchone()
            version = result[0] + 1

            # store model binary
            cursor.execute("INSERT INTO models VALUES(DEFAULT, %s, %s, %s) RETURNING modelID",
                           (modelName, version, psycopg2.Binary(modelBinary)))
            conn.commit()
            modelID = cursor.fetchone()[0]
            # Update device table to map to new model
            cursor.execute("UPDATE devices SET modelID=%s, deviceType=%s WHERE deviceName=%s",
                           (modelID, deviceType, deviceName))
            conn.commit()
        else:
            raise InternalServerError
        return {
            "success": True
        }
    except KeyError:
        raise HTTPException(status_code=400, detail="Incomplete request form")
    except InternalServerError:
        return {
            "success": False,
            "comment": "Internal Server Error"
        }


@app.on_event("startup")
async def startup():
    task = asyncio.get_running_loop().create_task(websocket_manager.init())
    await task
    asyncio.get_running_loop().create_task(websocket_manager.work())


# TODO: getModelByModelID, getModelByDeviceType, device-tree-like-structure instead of enum

########################################################################################
# Websocket
########################################################################################

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
async def newAlarmDetected(data, ws_wrapper):
    code = ws_wrapper.wdcode
    info = data["info"]
    cursor.execute("SELECT modelID FROM models WHERE modelName=%s AND version=%s",
                   (info["modelName"], info["version"]))
    modelID = cursor.fetchone()
    cursor.execute("INSERT INTO alarms VALUES(DEFAULT, %s, %s, %s, %s) RETURNING modelID",
                   (code, info["deviceName"], modelID, info["timestamp"]))
    conn.commit()
    return True, None

requestPullLatestModel_schema = {
    "type": "object",
    "properties": {
        "info": {
            "type": "object",
            "properties": {
                "modelID" : {"type": "number"},
                "deviceName": {"type": "string"},
            },
            "required": ["modelID", "deviceName"],
            "additionalProperties": False,
        },
    },
    "required": ["info"],
    "additionalProperties": False,
}
async def requestPullLatestModel(data, ws_wrapper):
    code = ws_wrapper.wdcode
    info = data["info"]
    deviceName = info["deviceName"]
    modelID = info["modelID"]
    cursor.execute("SELECT wdcode FROM wds WHERE deviceName=%s and modelID=%s",
                   (deviceName, modelID))
    conn.commit()
    affected_wds = cursor.fetchall()
    # send pullLatestModel to all affected wds
    for wd in affected_wds:
        wdcode = wd[0]
        await websocket_manager.send({"action": "pullLatestModel", "info": {"deviceName": deviceName}}, wdcode)
    return True, None

async def storeMetadata(data, ws_wrapper):
    code = ws_wrapper.wdcode
    action = data["action"]
    resp = await storeMetadata(data, code)
    resp["action"] = action
    await websocket_manager.send(resp, code)
    return True, None


# create WebsocketManager and register actions
websocket_manager = WebsocketManager()
websocket_manager.register("newAlarmDetected", newAlarmDetected, schema=newAlarmDetected_schema)
websocket_manager.register("requestPullLatestModel", requestPullLatestModel, schema=requestPullLatestModel_schema)
websocket_manager.register("storeMetadata", storeMetadata)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    ws_wrapper = await websocket_manager.connect(websocket)
    # authentication failed
    if ws_wrapper is None:
        return

    while websocket_manager.is_connected(ws_wrapper):
        success = await websocket_manager.listen(ws_wrapper)
        if not success:
            break


########################################################################################
#
########################################################################################

# HANDLER FOR METADATA RECEPTION
async def storeMetadata(data, wdcode):
    # Briefly check input
    if 'packets' not in data:
        return {"success": False, "comment": "Post did not contain packets"}
    packets = data['packets']
    # https://stackoverflow.com/questions/8134602/psycopg2-insert-multiple-rows-with-one-query
    args = [cursor.mogrify("(%s,%s,%s,%s,%s,%s,%s,%s)", [wdcode] + packet[:7]) for packet in packets]
    args_str = b','.join(args)
    query = b"INSERT INTO packets (wdcode, src_mac, dst_mac, src_ip, dst_ip, proto, ttl, packet_size) VALUES " + \
            args_str + b"RETURNING packet_id"
    # raise ValueError(query)
    cursor.execute(query)
    ids = cursor.fetchall()
    # raise ValueError(ids)
    # Insert TCP packets
    args_str = b','.join(
        [cursor.mogrify("(%s,%s,%s,%s,%s,%s,%s,%s)", [ids[n][0]] + p[7:]) for n, p in enumerate(packets) if
         p[4] == "TCP"])
    print(args_str)
    if args_str:
        cursor.execute(b"INSERT INTO tcp_packets VALUES " + args_str)
    # INSERT UDP packets
    args_str = b','.join(
        [cursor.mogrify("(%s,%s,%s)", [ids[n][0]] + p[7:]) for n, p in enumerate(packets) if p[4] == "UDP"])
    if args_str:
        cursor.execute(b"INSERT INTO udp_packets VALUES " + args_str)
    conn.commit()
    return {"success": True, "comment": f"Inserted {len(ids)} packets"}


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000)

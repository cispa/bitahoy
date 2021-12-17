from fastapi import FastAPI, Request
from starlette.websockets import WebSocket
import traceback
import asyncio

import psycopg2
from enums import *
import smtplib
from email.mime.text import MIMEText

from backend_lib.websocket_manager import WebsocketManager, getVersion
from backend_lib.auth import Auth
import os
from slack import WebClient

app = FastAPI(docs_url=None)
auth = Auth()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

# Database connection
db_conn = psycopg2.connect("dbname='db' user='db' host='{}' [redacted-2]".format(os.environ.get("DB_HOST")))
db_conn.autocommit = True
cursor = db_conn.cursor()
slack = WebClient(os.environ.get('SLACK_BOT_TOKEN'))

# TODO make TIMEOUT bigger for after-dev phase
TIMEOUT = 30  # Every timeout seconds the client needs to send a ping, to not be kicked! TODO set to 2 minutes or so

DEBUG = True


def sendEmail(to, text):
    # TODO fill in
    password = "[redacted-5]"  # BIT
    msg = MIMEText(text, "html")
    msg['From'] = "core-test@testing.bitahoy.com"  # Something like auth@bitahoy.com
    msg['To'] = to

    try:
        server = smtplib.SMTP('mailserver', 587)
        server.connect('mailserver', 587)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(msg['From'], password)
        server.sendmail(msg['From'], msg['To'], msg.as_string())
        server.quit()
        if DEBUG:
            print("Sent email!")
    except Exception as e:
        print("Error during email sending process!")
        print(e)
        return False
    return True


def lookupEmail(wdcode, deviceid):
    # User currently not connected! Maybe send him an email?
    # First check if the device has an option set for the email
    # If so get the email of the user and send it
    # Else get the standard email settings from the user and then do above
    email = None
    mailpolicy = None

    cursor.execute(
        "SELECT value FROM optionals WHERE wdcode=%s AND deviceid='" + str(deviceid) + "' AND key='mailPolicy'",
        (wdcode,))
    res = cursor.fetchall()
    if len(res) == 1:
        mailpolicy = int(res[0][0])

    cursor.execute(
        "SELECT email FROM wdcodes WHERE wdcode=%s",(wdcode,))
    res = cursor.fetchall()

    if len(res) == 1:  #
        email = res[0][0]
        if mailpolicy == None:
            mailpolicy = res[0][1]
    elif len(res) != 0:
        raise Exception("Database Error!")
    return (email, mailpolicy)


@app.exception_handler(Exception)
async def slackExceptionHandler(request: Request, exc: Exception):
    print("Fatal error during exception handling! Kicking the client...")
    tb = traceback.format_exc()
    try:
        slack.chat_postMessage(channel='#stacktraces', text=tb)
    except Exception as err:
        print("Could not notify via Slack!")
        print(err)
    finally:
        print(tb)
    return JSONResponse(status_code=505,
                        content={"message": "Ooops, something went wrong! I already notified the developers!"})


@app.get("/", status_code=200)
def status():
    return {"status": "ok"}


@app.get("/brewCoffee", status_code=418)
async def brewCoffee():  # Easter Egg
    try:
        slack.chat_postMessage(channel='#stacktraces', text='Someone brewed coffee on a teapot...')
    except:
        traceback.print_exc()
    return {"comment": "I'm a teapot"}


########################################################################################
# Websocket Manager Backend Lib
########################################################################################
async def requestInfo(data, ws_wrapper):
    wdcode = ws_wrapper.wdcode
    if ws_wrapper.isUser:
        # First get all devices
        cursor.execute("SELECT wdcode,deviceid,devicetype,status FROM devices WHERE wdcode=%s", (wdcode,))
        res = cursor.fetchall()

        d = {}
        for e in res:
            wdc = e[0]
            dei = e[1]
            det = e[2]
            sta = e[3]
            if wdc not in d:
                d[wdc] = {}
            d[wdc][dei] = {"type": det}
            d[wdc][dei]["status"] = sta

        # Now get all optionals
        cursor.execute("SELECT wdcode,deviceid,key,value FROM optionals WHERE wdcode=%s", (wdcode,))
        l = cursor.fetchall()
        for e in l:
            wdc = e[0]
            dev = e[1]
            key = e[2]
            val = e[3]
            d[wdc][dev][key] = val

    else:
        code = id
        cursor.execute("SELECT deviceid,devicetype,status FROM devices WHERE wdcode=%s", (wdcode,))
        res = cursor.fetchall()

        d = {}
        for e in res:
            d[e[0]] = {}
            d[e[0]]["type"] = e[1]
            d[e[0]]["status"] = e[2]

        cursor.execute("SELECT deviceid,key,value FROM optionals WHERE wdcode=%s", (wdcode,))
        l = cursor.fetchall()
        for e in l:
            dev = e[0]
            key = e[1]
            val = e[2]
            d[dev][key] = val
            
    return True, {"data": d}


async def registerDevice(data, ws_wrapper):
    if ws_wrapper.isUser:
        return False, {"comment": "Users can't register devices manually!"}
    else:
        wdcode = ws_wrapper.wdcode
        deviceid = int(data["deviceid"])
        devicetype = int(data["devicetype"])
        
        cursor.execute("SELECT * FROM devices WHERE wdcode=%s AND deviceid=%s",(wdcode,str(deviceid),))
        res = cursor.fetchall()
        if len(res) != 0:
            return False, {"comment": "Non unique device id!"}
        cursor.execute("INSERT INTO devices(wdcode,deviceid,devicetype,status) VALUES(%s,%s,%s,%s)", (wdcode, str(deviceid), str(devicetype), str(Status.NORMAL.value)))
        db_conn.commit()

        # Notify the user or send an email to him
        if not await websocket_manager.send({"action": "registerDevice"}, wdcode):
            email, mailpolicy = lookupEmail(wdcode, deviceid)
            if email != None and mailpolicy != None and mailpolicy >= MailPolicy.NORMAL.value:  # TODO better check
                sendEmail(email, "<html><body><p>NEW DEVICE REGISTERED!</p></body></html>")
        return True, None


async def updateOption(data, ws_wrapper):
    if ws_wrapper.isUser:
        wdcode = ws_wrapper.wdcode
        deviceid = int(data["deviceid"])
        key = data["key"]
        value = data["value"]

        # Check if this is a valid option:
        if not key in set(item.value for item in Option):
            return False, {"comment": "Invalid Option"}

        # TODO check if value is valid for given key

        cursor.execute("SELECT * FROM optionals WHERE wdcode=%s AND deviceid=" + str(deviceid) + " AND key=%s",
                       (wdcode, key,))
        res = cursor.fetchall()
        if len(res) == 1:
            # Already present
            cursor.execute(
                "UPDATE optionals SET value=%s WHERE wdcode=%s AND deviceid=" + str(deviceid) + " AND key=%s",
                (value, wdcode, key))
                
            db_conn.commit()
        elif len(res) == 0:
            cursor.execute(
                "INSERT INTO optionals(wdcode,deviceid,key,value) VALUES(%s," + str(deviceid) + ",%s,%s)",
                (wdcode, key, value))
            db_conn.commit()
        else:
            print("ERROR!")
            print(res)
            return False, {"comment": "Error!"}

        await websocket_manager.send({"action": "updateOption"}, wdcode)
        return True, None
        
    else:
        wdcode = ws_wrapper.wdcode
        deviceid = int(data["deviceid"])
        key = data["key"]
        value = data["value"]
        
        cursor.execute("SELECT * FROM devices WHERE wdcode=%s AND deviceid=" + str(deviceid),(wdcode,))
        res = cursor.fetchall()
        if len(res) != 1:
            return False, {"comment": "Device is not registered!"}

        success = False
        cursor.execute("SELECT * FROM optionals WHERE wdcode=%s AND deviceid=" + str(deviceid) + " AND key=%s",(wdcode, key,))
        res = cursor.fetchall()
        if len(res) == 1:
            # Already present
            cursor.execute(
                "UPDATE optionals SET value=%s WHERE wdcode=%s AND deviceid=" + str(deviceid) + " AND key=%s",
                (value, wdcode, key))
            db_conn.commit()
            success = True
        elif len(res) == 0:
            # New optional
            cursor.execute(
                "INSERT INTO optionals(wdcode,deviceid,key,value) VALUES(%s," + str(deviceid) + ",%s,%s)",
                (wdcode, key, value))
            db_conn.commit()
            success = True
        else:
            print("ERROR!")
            print(res)
            return False, None

        await websocket_manager.send({"action": "updateOption"}, wdcode)
        return success, None

        
async def updateStatus(data, ws_wrapper):
    wdcode = ws_wrapper.wdcode
    if ws_wrapper.isUser:
        deviceid = int(data["deviceid"])
        status = int(data["status"])
        
        if not status in [e.value for e in Status]:
            return False, {"comment": "Invalid status!"}

        cursor.execute(
            "UPDATE devices SET status=" + str(status) + " WHERE wdcode=%s AND deviceid=" + str(deviceid),
            (wdcode,))
        db_conn.commit()
        updatedrows = cursor.rowcount
        if updatedrows != 1:
            return False, None

        await websocket_manager.send({"action": "updateStatus"}, wdcode)
        return True, None
    
    else:
        deviceid = int(data["deviceid"])
        status = int(data["status"])

        if not status in [e.value for e in Status]:
            return False, {"comment": "Invalid status!"}
        cursor.execute(
            "UPDATE devices SET status=" + str(status) + " WHERE wdcode=%s AND deviceid=" + str(deviceid),
            (wdcode,))
        db_conn.commit()
        updatedrows = cursor.rowcount
        if updatedrows != 1:
            return False, None

        # Notify the user
        if not await websocket_manager.send({"action": "updateStatus"}, wdcode):
            email, mailpolicy = lookupEmail(wdcode, deviceid)
            if email != None and mailpolicy != None and mailpolicy >= MailPolicy.NORMAL.value:  # TODO better check
                sendEmail(email, "<html><body><p>STATUS OF DEVICE WAS UPDATED!</p></body></html>")

        return True, None
        

async def updateType(data, ws_wrapper):
    wdcode = ws_wrapper.wdcode
    if ws_wrapper.isUser:
        return False, {"comment", "Action not supported for User"}
    else:
        deviceid = int(data["deviceid"])
        devicetype = int(data["devicetype"])
        cursor.execute("UPDATE devices SET devicetype=" + str(devicetype) + " WHERE wdcode=%s AND deviceid=" + str(
            deviceid), (wdcode,))
        db_conn.commit()
        updatedrows = cursor.rowcount
        if updatedrows != 1:
            return False, None

        # Confirm and notify
        if not await websocket_manager.send({"action": "updateType"}, wdcode):
            email, mailpolicy = lookupEmail(wdcode, deviceid,)
            if email != None and mailpolicy != None and mailpolicy >= MailPolicy.NORMAL.value:  # TODO better check
                sendEmail(email, "<html><body><p>DEVICETYPE WAS CHANGED!</p></body></html>")

        return True, None

websocket_manager = WebsocketManager(debug=True, zmq=True, timeout=30)
websocket_manager.register("requestInfo", requestInfo)
websocket_manager.register("registerDevice", registerDevice)
websocket_manager.register("updateOption", updateOption)
websocket_manager.register("updateStatus", updateStatus)
websocket_manager.register("updateType", updateType)

@app.on_event("startup")
async def startup():
    # print("startup coroutine called")
    task = asyncio.get_running_loop().create_task(websocket_manager.init())
    # await websocket_manager.init()
    await task
    asyncio.get_running_loop().create_task(websocket_manager.work())
    print("Working with backend-lib version: "+getVersion())
    print("Finished startup co-routine")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    ws_wrapper = await websocket_manager.connect(websocket)
    # authentication failed
    if not ws_wrapper:
        return
        
    wdcode = ws_wrapper.wdcode
    isUser = ws_wrapper.isUser

    if isUser:
        # update user database
        cursor.execute("SELECT * FROM wdcodes WHERE wdcode=%s", (wdcode,))
        #Users have an email!
        email = ws_wrapper.email
        res = cursor.fetchall()
        if len(res) == 0:
            try:
                cursor.execute("INSERT INTO wdcodes(wdcode,email,mailpolicy) VALUES(%s,%s," + str(MailPolicy.NORMAL.value) + ")", (wdcode,email,))
                db_conn.commit()
            except psycopg2.errors.UniqueViolation:
                #Entry was made in between -> Ignore!
                pass

    if DEBUG:
        print(wdcode + " connected successfully! ("+("isUser" if isUser else "noUser")+")")

    while websocket_manager.is_connected(ws_wrapper):
        success = await websocket_manager.listen(ws_wrapper)
        if not success:
            break


########################################################################################
#
########################################################################################

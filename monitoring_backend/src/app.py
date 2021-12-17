import asyncio
import os
import json
import psycopg2
from datetime import datetime
from fastapi import FastAPI, Request, Body, HTTPException
from backend_lib.websocket_manager import WebsocketManager
from backend_lib.auth import Auth, Expired, VerificationFailed, InvalidToken
from starlette.websockets import WebSocket

app = FastAPI(docs_url=None)
auth = Auth()

# Database connection
with psycopg2.connect("dbname='db' user='db' host='{}' password='{}'".format(os.environ.get("DB_HOST"),
                                                                             os.environ.get("DB_PASS"))) as conn:
    conn.autocommit = True

    validStatistics = ["traffic", "DDoS"]

    CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL"))
    LOGS_TIMEWINDOW = int(os.getenv("LOGS_TIMEWINDOW"))


    @app.get("/publicStatistics")
    async def publicStatistics():
        '''Accessable from anyone, yields current statistics'''

        stats = {}

        with conn.cursor() as cursor:
            # Query the amount of rows in the wdcode table (Every entry there is a active watchdog)
            cursor.execute("SELECT count(*) FROM (SELECT DISTINCT wdcode FROM statistics) sub")
            stats["clients"] = cursor.fetchall()[0][0]
            cursor.execute("SELECT count(*) FROM (SELECT DISTINCT uid FROM statistics) sub")
            stats["uids"] = cursor.fetchall()[0][0]
            cursor.execute("SELECT count(*) FROM (SELECT DISTINCT wdcode,deviceid FROM statistics) sub")
            stats["devices"] = cursor.fetchall()[0][0]

            # Now all the past 24 hour queries with a single sub query
            cursor.execute(
                "SELECT statistic,SUM(value) FROM statistics WHERE time >= NOW() - INTERVAL '24 HOURS' GROUP BY statistic")

            res = cursor.fetchall()
            for s in res:
                stats[s[0]] = s[1]

        return {
            "success": True,
            "statistics": stats
        }


    @app.get("/privateStatistics")
    async def privateStatistics(request: Request):
        '''
        This serves as an endpoint for the user to fetch it's statistics
        '''
        data = json.loads(await request.body())
        try:
            token = data["token"]  # Contains email and uid
            try:
                authenticatedClient = auth.verify(token)
            except Expired:
                return {
                    "success": False,
                    "comment": "Expired"
                }
            except InvalidToken:
                return {
                    "success": False,
                    "comment": "InvalidToken"
                }
            except VerificationFailed as e:
                return {
                    "success": False,
                    "comment": "VerificationFailed"
                }
            except Exception as err:
                return {
                    "success": False
                }

            code = authenticatedClient.code  # email
            uid = authenticatedClient.uid  # uid
            time = int(data["time"])  # Timeframe in hours
            if not authenticatedClient.isUser:
                return {
                    "success": False,
                    "comment": "Not a user"
                }
            try:
                time = int(time)
                assert 1 <= time <= 672  # 1month
            except:
                return {
                    "success": False,
                    "comment": "Invalid timeframe"
                }

            with conn.cursor() as cursor:
                # fetch private statistics
                # stats = {}
                cursor.execute(
                    "SELECT wdcode,deviceid,statistic,SUM(value) FROM statistics WHERE uid=%s AND time >= NOW() - INTERVAL '%s HOURS' GROUP BY wdcode,deviceid,statistic",
                    (uid, time))
                res = cursor.fetchall()
                # for s in res:
                #    stats[s[0]] = stats[s[1]]

            return {
                "success": True,
                "statistics": res
            }

        except KeyError:
            raise HTTPException(status_code=400, detail="Incomplete request form")


    @app.get("/submitStatistics")
    async def submitStatistics(request: Request):
        '''
        This serves as an endpoint for the client to submit statistics
        '''
        data = json.loads(await request.body())
        try:
            token = data["token"]
            try:
                authenticatedClient = auth.verify(token)
            except Expired:
                return {
                    "success": False,
                    "comment": "Expired"
                }
            except InvalidToken:
                return {
                    "success": False,
                    "comment": "InvalidToken"
                }
            except VerificationFailed as e:
                return {
                    "success": False,
                    "comment": "VerificationFailed"
                }
            except Exception as err:
                return {
                    "success": False
                }

            code = authenticatedClient.code  # wdcode
            uid = authenticatedClient.uid  # uid
            statistic = data["statistic"]
            value = int(data["value"])
            deviceid = int(data["deviceid"])

            if authenticatedClient.isUser:
                return {
                    "success": False,
                    "comment": "Not a client"
                }

            # Valid metric?
            if statistic not in validStatistics:
                return {
                    "success": False,
                    "comment": "Not a valid statistic"
                }

            with conn.cursor() as cursor:

                # Check time since last submission
                cursor.execute("SELECT time FROM statistics WHERE wdcode=%s AND statistic=%s ORDER BY time DESC",
                               (code, statistic,))

                res = cursor.fetchall()
                if len(res) > 0:
                    latest = res[0][0]

                    # TODO differ between WHAT query we are looking at!
                    if (datetime.utcnow() - latest).total_seconds() < 3600:  # Max 1 update per hour
                        return {
                            "success": False,
                            "comment": "Too many updates"
                        }

                cursor.execute(
                    "INSERT INTO statistics(wdcode,uid,deviceid,statistic,time,value) VALUES (%s, %s, %s ,%s, NOW(),%s)",
                    (code, uid, deviceid, statistic, value))
                conn.commit()
            return {
                "success": True
            }

        except KeyError:
            raise HTTPException(status_code=400, detail="Incomplete request form")


    async def clean_logs():
        while True:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(f"DELETE FROM logs WHERE time < now()-'%s seconds'::interval;", (LOGS_TIMEWINDOW,))
                    conn.commit()
                # print("Clean up old logs.")
                await asyncio.sleep(CLEANUP_INTERVAL)
            # table not yet defined, try again later
            except psycopg2.errors.UndefinedTable:
                pass


    ########################################################################################
    #
    ########################################################################################
    # TODO: level return all level <= specified level

    async def getLogs(data, ws_wrapper):
        wdcode = ws_wrapper.wdcode
        isUser = ws_wrapper.isUser

        timewindow = data["timewindow"]
        sender = None
        level = None
        # TODO: prettier
        try:
            sender = data["sender"]
        except KeyError:
            pass
        try:
            level = data["level"]
        except KeyError:
            pass

        with conn.cursor() as cursor:
            if sender is not None and level is not None:
                cursor.execute(
                    "SELECT sender, message, level FROM logs WHERE wdcode=%s AND sender=%s AND level<=%s AND time > now()-'%s seconds'::interval ORDER BY time DESC",
                    (wdcode, sender, level, timewindow))
            elif sender is not None:
                cursor.execute(
                    "SELECT sender, message, level FROM logs WHERE wdcode=%s AND sender=%s AND time > now()-'%s seconds'::interval ORDER BY time DESC",
                    (wdcode, sender, timewindow))
            elif level is not None:
                cursor.execute(
                    "SELECT sender, message, level FROM logs WHERE wdcode=%s AND level<=%s AND time > now()-'%s seconds'::interval ORDER BY time DESC",
                    (wdcode, level, timewindow))
            else:
                cursor.execute(
                    "SELECT sender, message, level FROM logs WHERE wdcode=%s AND time > now()-'%s seconds'::interval ORDER BY time DESC",
                    (wdcode, timewindow))
            res = cursor.fetchall()

        return True, {"logs": res}


    async def uploadLogs(data, ws_wrapper):
        isUser = ws_wrapper.isUser
        if isUser:
            return False, {"comment": "Only wds can upload logs."}

        wdcode = ws_wrapper.wdcode
        if not isinstance(data["logs"], list):
            return False, {"comment": "Please submit logs as list of length >= 1"}

        # if oldest entry is older than 24 hours

        with conn.cursor() as cursor:

            for log in data["logs"]:
                level = log["level"]
                time = log["time"]
                sender = log["sender"]
                message = log["message"]

                cursor.execute(
                    "INSERT INTO logs(wdcode,level,time,sender,message) VALUES (%s, %s, to_timestamp(%s), %s, %s)",
                    (wdcode, level, time, sender, message)
                )
            conn.commit()
        return True, {"comment": f"Inserted {len(data['logs'])} log(s) into db."}


    async def uploadNotifications(data, ws_wrapper):
        isUser = ws_wrapper.isUser
        if isUser:
            return False, {"comment": "Only wds can upload notifications."}

        wdcode = ws_wrapper.wdcode
        if not isinstance(data["notifications"], list):
            return False, {"comment": "Please submit logs as list of length >= 1"}

        # if oldest entry is older than 24 hours
        with conn.cursor() as cursor:

            for log in data["notifications"]:
                level = log["level"]
                time = log["time"]
                sender = log["sender"]
                message = log["message"]

                cursor.execute(
                    "INSERT INTO notifications(wdcode,level,time,sender,message) VALUES (%s, %s, to_timestamp(%s), %s, %s)",
                    (wdcode, level, time, sender, message)
                )
            conn.commit()

        # forward to all connected users/clients
        await websocket_manager.send_all(data, ws_wrapper, success=True)
        return True, {"comment": f"Inserted {len(data['notifications'])} notification(s) into db."}


    async def getNotifications(data, ws_wrapper):
        wdcode = ws_wrapper.wdcode

        timewindow = data["timewindow"]
        sender = None
        level = None
        # TODO: prettier
        try:
            sender = data["sender"]
        except KeyError:
            pass
        try:
            level = data["level"]
        except KeyError:
            pass

        with conn.cursor() as cursor:

            if sender is not None and level is not None:
                cursor.execute(
                    "SELECT sender, message, level, time FROM notifications WHERE wdcode=%s AND sender=%s AND level<=%s AND time > now()-'%s seconds'::interval ORDER BY time DESC",
                    (wdcode, sender, level, timewindow))
            elif sender is not None:
                cursor.execute(
                    "SELECT sender, message, level, time FROM notifications WHERE wdcode=%s AND sender=%s AND time > now()-'%s seconds'::interval ORDER BY time DESC",
                    (wdcode, sender, timewindow))
            elif level is not None:
                cursor.execute(
                    "SELECT sender, message, level, time FROM notifications WHERE wdcode=%s AND level<=%s AND time > now()-'%s seconds'::interval ORDER BY time DESC",
                    (wdcode, level, timewindow))
            else:
                cursor.execute(
                    "SELECT sender, message, level, time FROM notifications WHERE wdcode=%s AND time > now()-'%s seconds'::interval ORDER BY time DESC",
                    (wdcode, timewindow))
            res = cursor.fetchall()

            if len(res) > 0:
                res = [(sender, message, level, datetime.timestamp(time)) for (sender, message, level, time) in res]

        return True, {"notifications": res}


    async def getConfig(data, ws_wrapper):
        code = ws_wrapper.wdcode
        '''
        for given code, return the remote-access config
        :param request: -
        :return:  "success": bool, "config": dict, "comment": string
        '''
        info = data["info"]
        action = data["action"]

        with conn.cursor() as cursor:

            # is there a relation for this wdcode addonName?
            cursor.execute("SELECT config FROM configs WHERE wdcode=%s", (code,))
            result = cursor.fetchone()

        if not result:  # no config for this code
            comment = "No config exists for this WD code. use insertConfig to set a new config for this WD code."
            return False, {"action": action, "comment": comment}

        else:
            config = json.loads(result[0].tobytes())
            comment = "Found an existing for this WD code."
            return True, {"action": action, "config": config, "comment": comment}


    async def insertConfig(data, ws_wrapper):
        code = ws_wrapper.wdcode
        '''
        for given code, insert remote-access config into DB
        :param request: config Dict
        :return:  "success": bool, "config": Dict, "comment": string
        '''
        info = data["info"]
        action = data["action"]

        try:
            jsonConfig = info["config"]
            bytesConfig = json.dumps(jsonConfig)
        except KeyError:  # can't get value from request data
            return False, {"action": action, "comment": "No config supplied. Please check inputs."}

        # valid_return = inputValidation(info, ("config"))
        # if valid_return[0]:  # check return form the validation
        #     jsonConfig = valid_return[1]  # unpack results
        #     bytesConfig = json.dumps(jsonConfig)  # dump the json
        # else:  # no config supplied
        #     return False, {"action": action, "comment": valid_return[2]}

        with conn.cursor() as cursor:
            try:
                cursor.execute("INSERT INTO configs VALUES(%s, %s)", (code, bytesConfig))
                conn.commit()
                comment = "No config exists for this WD code. Created new entry."
            except psycopg2.errors.UniqueViolation:  # entry exists for this WD code
                conn.commit()
                cursor.execute("UPDATE configs SET config=%s WHERE wdcode=%s", (bytesConfig, code))
                conn.commit()
                comment = "Found an existing config for this WD code. Overwriting existing with new."

        return True, {"action": action, "config": jsonConfig, "comment": comment}


    # TODO: loglevel set and get

    websocket_manager = WebsocketManager(zmq=True, servicename="monitoring_service")
    websocket_manager.register("getConfig", getConfig)
    websocket_manager.register("insertConfig", insertConfig)
    websocket_manager.register("uploadLogs", uploadLogs)
    websocket_manager.register("getLogs", getLogs)
    websocket_manager.register("uploadNotifications", uploadNotifications)
    websocket_manager.register("getNotifications", getNotifications)


    @app.on_event("startup")
    async def startup():
        task = asyncio.get_running_loop().create_task(websocket_manager.init())
        await task

        async def startup_tasks():
            await websocket_manager.work()
            await clean_logs()

        asyncio.get_running_loop().create_task(startup_tasks())
        print("Startup co-routine started")

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

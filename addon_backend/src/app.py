from fastapi import FastAPI, Request, HTTPException
import psycopg2

from starlette.websockets import WebSocket, WebSocketState
import asyncio

import json
import os

from backend_lib.websocket_manager import WebsocketManager
from backend_lib.auth import Auth, Expired, VerificationFailed, InvalidToken
import traceback

app = FastAPI()

# Database connection
conn = psycopg2.connect("dbname='db' user='db' host='{}' password='{}'".format(os.environ.get("DB_HOST"), os.environ.get("DB_PASS")))
conn.autocommit = True
cursor = conn.cursor()

#if auth check is ran locally, set ip (or docker netw namingresolution "auth") to whatever you are using in the docker setup
AUTH_URL = "http://auth.bitahoy.cloud"
auth = Auth(AUTH_URL)
TIMEOUT = 120000

null_device = "NULL"
inter_serv_err = "Internal Server Error."

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
        return authenticatedClient, "authenticate(token) debug?"
    except Expired:
        return None, "Token expired"
    except InvalidToken:
        return None, "Invalid Token"
    except VerificationFailed as e:
        return None, repr(e)
    except Exception as err:
        return None, repr(err)


def updateRelation(wdcode, addonName, deviceName, configID, enabled=None):
    '''
    help function to add new main entry in the WDS Table
    '''
    # enabled is an optional param, this is because configs are set as enabled by default, but we don't want to change it that often
    try:
        cursor.execute("INSERT INTO wds VALUES(%s, %s, %s, %s, %s)", (wdcode, addonName, deviceName, enabled, configID))
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.commit()
        cursor.execute("UPDATE wds SET enabled=%s, configID=%s WHERE wdcode=%s AND addonName=%s AND deviceName=%s", (enabled, configID, wdcode, addonName, deviceName))
        conn.commit()

def updateType(addonName, gitURL, commitHash, configID):
    '''
    help function to add new main entry in the ADDONS Table
    '''
    try:
        cursor.execute("INSERT INTO addons VALUES(%s, %s, %s, %s)", (addonName, gitURL, commitHash, configID))
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.commit()
        cursor.execute("UPDATE addons SET gitURL=%s, commitHash=%s, defaultConfigID=%s WHERE addonName=%s ", (gitURL, commitHash, configID, addonName))
        conn.commit()

def updateConfig(jsonDict, configID=None):
    '''
    helper function to INSERT and get back new configID if not existing already.
    '''
    if configID:
        if (isDefaultConfig):
            # print("YOU ARE MODIFYING A DEFAULT CONFIG, WHICH IS USED BY ALL NULL DEVICES. ARE YOU SURE YOU WANT TO DO THIS?")
            pass

        cursor.execute("UPDATE configs SET config=%s WHERE configID=%s",
                       (jsonDict, configID))
        conn.commit()
    else:
        cursor.execute("INSERT INTO configs VALUES(DEFAULT, %s) RETURNING configID",
                       (jsonDict,))
        conn.commit()
        return cursor.fetchone()[0]


def isDefaultConfig(configID):
    # quick check that we don't set a defaultConfig by mistake
    cursor.execute("SELECT defaultConfigID FROM addons", ())
    result = cursor.fetchall()

    # default_configs, dummy = zip(*result)
    for i in result:
        if configID == i[0]:
            # print("ABORTED: YOU ARE ATTEMPTING TO MODIFY A DEFAULT CONFIG")
            return True
    return False

def selectRelation(wdcode, addonName, deviceName):
    '''
    simple helper function to fetch Relation entry
    if exact unique deviceName is not found,  it will check for a NULL device fall-back
    '''
    cursor.execute("SELECT wds.addonName, wds.deviceName, wds.enabled, wds.configID FROM wds WHERE wdcode=%s AND addonName=%s AND deviceName=%s", (wdcode, addonName, deviceName))
    conn.commit()
    result = cursor.fetchone()
    if not result: # maybe there's a NULL-device entry?
        cursor.execute("SELECT wds.addonName, wds.deviceName, wds.enabled, wds.configID FROM wds WHERE wdcode=%s AND addonName=%s AND deviceName=%s", (wdcode, addonName, null_device))
        conn.commit()
        result = cursor.fetchone()
        # print("fetching NULL device relation entry!!")
    return result


def selectType(addonName):
    '''
    simple helper function to fetch Type details and it's config
    '''
    cursor.execute("SELECT addons.addonName, addons.gitURL, addons.commitHash, addons.defaultConfigID FROM addons WHERE addonName=%s", (addonName,))
    conn.commit()
    return cursor.fetchone()

def selectConfig(configID):
    '''
    simple helper function to fetch and decode the config dict form CONFIGS Table
    '''
    cursor.execute("SELECT config FROM configs WHERE configID=%s", (configID,))
    result = cursor.fetchone()
    return json.loads(result[0].tobytes())


# WEBSOCKET START HERE!!! --------------------------
# TODO: wat?
@app.on_event("startup")
async def startup():
    print("startup coroutine called")
    task = asyncio.get_running_loop().create_task(websocket_manager.init())
    await task
    asyncio.get_running_loop().create_task(websocket_manager.work())



def checkIsUser(action, code):
    # DEPRECATED: code = authenticatedClient.belongs[0] if authenticatedClient.isUser else authenticatedClient.code
    # code = websocket_manager.get_websocket(code).wdcodes[0] if websocket_manager.get_websocket(code).isUser else code
    if websocket_manager.get_websocket(code).isUser:
        try:
            wdcode = websocket_manager.get_websocket(code).wdcodes[0]
        except IndexError:
            return False, {"action": action,
                           "comment": "the isUSer check is acting up, should check this, as the .wdcodes[0] is None?"}
        return True, wdcode

    else:
        return False, code

'''
Now for the actual functions ---------------------------
'''

class PlaceHolderType(Exception):
    pass


modifyType_schema = {
    "type": "object",
    "properties": {
        "info": {
            "type": "object",
            "properties": {
                "addonName" : {"type": "string"},
                "gitURL": {"type": "string"},
                "commitHash": {"type": "string"},
                "defaultConfig": {"type": "object"},
                "timestamp": {"type": "number"},
                "safe_edit": {"type": "boolean"}
            },
            "required": ["addonName", "gitURL", "commitHash", "defaultConfig", "timestamp"],
            "additionalProperties": False,
        },
    },
    "required": ["info"],
    "additionalProperties": False,
}
async def modifyType(data, code):
    '''
    checks if such (addon)Type already exist and if not, adds one - Use this to initialize new Addons into the service
    ELSE, we update(overwrite) the existing entry with new data (WARNNING: might be risky!!!)
    if safe_edit not present, then no overwrite is possible
    :param request: "addonName" : {"type": "string"},
                    "gitURL": {"type": "string"},
                    "commitHash": {"type": "string"},
                    "defaultConfig": {"type": "object"},
                    "timestamp": {"type": "number"},
                    "safe_edit": {"type": "boolean"} [OPTIONAL]
    :return:  "success": bool and "comment" string
    '''
    info = data["info"]
    action = data["action"]

    addonName = info["addonName"]
    gitURL = info["gitURL"]
    commitHash = info["commitHash"]
    defaultConfig = info["defaultConfig"]
    bytesCfg = json.dumps(defaultConfig)  # dump the json

    result = selectType(addonName)

    if not result:  # no such (addon)Type exists in the Type Table, create new entry
        configID = updateConfig(bytesCfg)
        updateType(addonName, gitURL, commitHash, configID)
        comment = "Created a new entry, as no such Type exists in the Type Table"
        return True, {"action": action, "comment": comment}

    else:  # found existing Type entry, updating it now
        try:
            safe_edit = info["safe_edit"]
        except KeyError:
            comment = "You are attempting to update an existing (addon)Type, thus overwritting an existing entry that might be used by other devices/addon_configs. If you are sure about this, add a 'safe_edit' boolena flag and retry again."
            return False, {"action": action, "comment": comment}
        if (safe_edit):
            configID = result[-1]
            updateConfig(bytesCfg, configID)
            updateType(addonName, gitURL, commitHash, configID)  # this overwrites the existing entry, if such exists
            comment = "safe_edit flag was supplied - updating an existing (addon)Type, thus overwritting an existing entry"
            return True, {"action": action, "comment": comment}
        else:
            comment = "You are attempting to update an existing (addon)Type, thus overwritting an existing entry but your safe_edit flag is FALSE. Check AddoName and make sure you set the flag to true if you are sure about what you are doing."
            return False, {"action": action, "comment": comment}


getType_schema = {
    "type": "object",
    "properties": {
        "info": {
            "type": "object",
            "properties": {
                "addonName": {"type": "string"},
                "timestamp": {"type": "number"},
            },
            "required": ["timestamp"],
            # "optional": ["addonName"],
            "additionalProperties": False,
        },
    },
    "required": ["info"],
    "additionalProperties": False,
}
async def getType(data, code):
    '''
    given AddonName, return the Type details and its default config
    if no AddonName is specified, you get a LIST of all possible Types (ex-TypeCatalogue)
    :param request:   "addonName": {"type": "string"}, [OPTINAL]
                "timestamp": {"type": "number"},
    :return: Dict {addonName, gitURL, commitHash, defaultConfig} - if no params provided will be given as a LIST of dicts
    '''
    info = data["info"]
    action = data["action"]

    # addonName optional
    try:
        addonName = info["addonName"]
    except KeyError:
        addonName = None

    if addonName:
        result = selectType(addonName)

        if result is None:
            comment = "No types found, is the Types Table even populated?"
            return False, {"action": action, "comment": comment}

        else:
            comment = "found the required Type, returing details"
            defaultConfig = selectConfig(result[3])
            typeDetails = {"addonName": result[0], "gitURL": result[1], "commitHash": result[2],
                           "defaultConfig": defaultConfig}
            return True, {"action": action, "type": typeDetails, "comment": comment}

    else: # no addonName given, return all
        try:
            cursor.execute("SELECT addons.addonName, addons.gitURL, addons.commitHash, addons.defaultConfigID FROM addons",
                           ())
            conn.commit()
            result = cursor.fetchall()
        except InternalServerError:
            return False, {"action": action, "comment": "InternalServerError on query on Types Table"}

        if result is None:
            comment = "No types found, is the Types Table even populated?"
            return False, {"action": action, "comment": comment}

        else:
            typesArray = []
            for entry in result: # iterate through results and format them for the return
                defaultConfig = selectConfig(entry[3])
                typeDetails = {"addonName": entry[0], "gitURL": entry[1], "commitHash": entry[2], "defaultConfig": defaultConfig}
                typesArray.append(typeDetails)
            comment = "No addonName was given, returning whole catalouge. "
            return True, {"action": action, "typesList": typesArray, "comment": comment}



removeType_schema = {
    "type": "object",
    "properties": {
        "info": {
            "type": "object",
            "properties": {
                "addonName": {"type": "string"},
                "timestamp": {"type": "number"},
            },
            "required": ["timestamp", "addonName"],
            "additionalProperties": False,
        },
    },
    "required": ["info"],
    "additionalProperties": False,
}
async def removeType(data, code):
    '''
    cleanly removes all traces of an (addon)TYPE from the TYPE db, including WDS and CONFIG db entires that relate tot his Type
    :param request: "addonName": {"type": "string"},
                    "timestamp": {"type": "number"},
    :return:  "success": bool and "comment" string
    '''
    info = data["info"]
    action = data["action"]

    isUser, wdcode = checkIsUser(action, code)

    addonName = info["addonName"]

    result = selectType(addonName)

    # can't find this Type, something is wrong!
    if not result:
        comment = "No addon named {} in the Type Table, check your inputs or printout the Type Cataloge using getInstalledTypes with the Cataloge flag".format(
            addonName)
        return False, {"action": action, "addonName": addonName, "comment": comment}

    else: # Type exists in the Table
        default_id_result = selectType(addonName)[-1]

        # now write down all the unique-user-defined configs
        cursor.execute(
            "SELECT configID FROM wds WHERE addonName=%s",
            (addonName,))
        conn.commit()
        unique_id_result = cursor.fetchall()

        # ... and also the relevant relatiosn still left in the wds Table.
        cursor.execute("DELETE FROM wds WHERE addonName=%s", (addonName,))
        conn.commit()

        # now we can safly remove the AddonType entry
        cursor.execute("DELETE FROM addons WHERE addonName=%s", (addonName,))
        conn.commit()

        # now we can safly remove the ids saved from before
        if default_id_result:
            cursor.execute("DELETE FROM configs WHERE configID=%s", (default_id_result,))
            conn.commit()
        if unique_id_result:
            for i in unique_id_result:
                cursor.execute("DELETE FROM configs WHERE configID=%s", (i[0],))
                conn.commit()

        comment = "removed addon named {} from the Type Table, as well as any relations with the Addon's name in the wds Table and it's corresponding configs in the configs Table".format(
            addonName)
        return True, {"action": action, "addonName": addonName, "comment": comment}




class PlaceHolderAddon(Exception):
    pass


modifyAddon_schema = {
    "type": "object",
    "properties": {
        "info": {
            "type": "object",
            "properties": {
                "deviceName": {"type": "string"},
                "addonName": {"type": "string"},
                "config": {"type": "object"},
                "enabled": {"type": "boolean"},
                "timestamp": {"type": "number"},
            },
            "required": ["deviceName", "addonName", "timestamp"],
            "additionalProperties": False,
        },
    },
    "required": ["info"],
    "additionalProperties": False,
}
async def modifyAddon(data, code):
    '''
    Given Addon-device tupel, changes its related config AND/OR enabled bool
    if a NULL relation is present, we will create a new relation with the deviceName given.
    will Notify WD, if was submitted by a user-client
    :param request: "deviceName" : {"type": "string"},
                    "addonName": {"type": "string"},
                    [Optional] "config": {"type": "object"},
                    [Optional] "enabled": {"type": "boolean"},
                    "timestamp": {"type": "number"},
    :return: "success": bool and "comment" string
    '''
    info = data["info"]
    action = data["action"]

    isUser, wdcode = checkIsUser(action, code)

    deviceName = info["deviceName"]
    addonName = info["addonName"]
    json_send = {"action": action, "addonName": addonName, "deviceName": deviceName} # placeholder for later

    # is there a relation for this wdcode addonName?
    result = selectRelation(wdcode, addonName, deviceName)

    if not result:  # no such relation exists, be it either for this deviceName OR for a NULL device
        comment = "No such relation exists, be it either for this deviceName OR for a NULL device. please check that you have installed the addon on this wd "
        return False, {"action": action, "comment": comment}

    try:
        enabled = info["enabled"]
        comment = "Found enabled %s value in input. ".format(enabled)
        json_send["enabled"] = enabled
    except KeyError:
        enabled = None #!!! avoid using <if enabled:> as this could be assigned to False

    try:
        config = info["config"]
        bytesConfig = json.dumps(config)
        comment = "Found config value in input. "
        json_send["config"] = config
    except KeyError:
        bytesConfig = None

    if (enabled is None) and (bytesConfig is None):  # both optional fields for enabled and config are not present!
        comment = "One of the optional fields for enabled OR config are required(!) to run this action! check inputs. "
        return False, {"action": action, "comment": comment}

    '''Both when either enabled or config are modified, there are 2 possible cases:
    1. we are doing changes to a unique device or explicitly to a NULL device, both of which already has an entry
        if changes are being applied to an NULL device, we need to alter the NULL entry 
        (even in this case it already has a unique configID number, compared to the defaultConfigID from the TYPE Table - see installAddon for more info)
    2. if changes are being applied to a device, which has yet to be installed, we create a new config entry for it
    -
    in both cases we use updateRelation to set those relation modifications
    '''
    # either case, if no enabled is given, we need to write the old value from the resul
    if enabled is None:  # enabled not present in input
        enabled = result[-2]

    # user requests us to either modify a unique device, or explicitly asks to modify the NULL entry
    if (result[-3] != null_device) or (deviceName == null_device):
        comment = comment + "Modify entry for deviceName %s. ".format(deviceName)

        configID = result[-1]
        if bytesConfig: # config present in input
            updateConfig(bytesConfig, configID=configID)
        else:
            pass # when no config is present, there's no need to change config entry

        # updateRelation(wdcode, addonName, deviceName, configID, enabled=enabled)

    # elif (result[-3] == null_device) and (deviceName != null_device):
    else: # user asked to modify a unique device entry, but there's only a fall-back NULL entry (i.e no unique)
        comment = comment + "Fall-back NULL device is the only relation found, created a new relation for the given unqiue deviceName. "

        if bytesConfig: # config present in input
            configID = updateConfig(bytesConfig) # create a new Config entry
        else: # if no config is present, we actually need to create a new copy config for this new entry, similar to how we do this in installAddon()
            copyConfig = selectConfig(result[-1]) # check which config the NULL is using
            configID = updateConfig(json.dumps(copyConfig))  # write new entry(which is a copy of the config in the NULL device entry)

    updateRelation(wdcode, addonName, deviceName, configID, enabled=enabled)

    json_send["comment"] = comment

    if isUser:
        user_send = json_send
        user_send["success"] = True
        await websocket_manager.send(user_send, wdcode)

    return True, json_send


getAddon_schema = {
    "type": "object",
    "properties": {
        "info": {
            "type": "object",
            "properties": {
                "deviceName" : {"type": "string"},
                "addonName": {"type": "string"},
                "timestamp": {"type": "number"},
            },
            "required": ["timestamp"],
            # "optional": ["deviceName", "addonName"],
            "additionalProperties": False,
        },
    },
    "required": ["info"],
    "additionalProperties": False,
}
async def getAddon(data, code):
    '''
    for entire addon details, mainly for enabled bool and config
    - if no input is given, it returns a LIST all the enabled (i.e. installed) addons as "addonsList"
    :param request: "deviceName" : {"type": "string"},
                    "addonName": {"type": "string"},[OPTIONAL]
                    "timestamp": {"type": "number"},
    :return:  "success": bool,
                "addon": {
                    "addonName": string,
                    "deviceName": string,
                    "enabled": bool,
                    "config": dict
                }
    '''
    info = data["info"]
    action = data["action"]

    isUser, wdcode = checkIsUser(action, code)

    try:
        deviceName = info["deviceName"]
        addonName = info["addonName"]
    except KeyError:
        deviceName = None
        addonName = None
    
    comment = ""

    # check if mandatory Addons are already installed, if not, manually install them before proceeding
    mandatory_addons = ["adblock", "security"]
    for must_addon in mandatory_addons:
        is_mandatory_installed = selectRelation(wdcode, must_addon, deviceName)
        if not is_mandatory_installed:
            # -------------- BEGIN of installAddon copy-paste ------------------------
            # based on the selectRelation check above we know that there's no relatin yet for this addonName.
            # this means that we need to add a NULL device entry into the ADDONS table (last part of installAddon() )
            # check how the default config looks like
            selectTypeResult = selectType(must_addon)
            if not selectTypeResult:
                cursor.execute(
                    "SELECT * FROM addons",
                    ())
                conn.commit()
                result_alltypes = cursor.fetchall()
                comment = "is_mandatory_installed: No such addon Type {} found? are you sure about the addon name? check types cataloge: {}".format(must_addon, result_alltypes)
                return False, {"action": action, "comment": comment}
            defaultConfigID = selectTypeResult[-1]  # get defaultConfigID for this NULL device
            defaultConfigCopyJSON = json.dumps(selectConfig(defaultConfigID))
            newConfigID = updateConfig(defaultConfigCopyJSON)  # when given w/o id, creates a new entry in the CONFIGS Table
            # now write this new config in the relation
            updateRelation(wdcode, must_addon, null_device, newConfigID,
                           enabled=True)  # enabled bool is set to True by default
            comment = "is_mandatory_installed: created a new NULL device fall-back entry for this wdcode and addon relation with a fresh copy of the default config."

            if isUser:
                await websocket_manager.send(
                    {"success": True, "action": action, "addonName": must_addon, "comment": comment}, wdcode)

            # -------------- END of installAddon copy-paste ------------------------
    
    if deviceName and addonName:
        # result = selectRelation(wdcode, addonName, deviceName)
        result = None
        try:
            # initial version was fetching only ADDOn data, so I made the query more complicated to fetch TYPE data aswell
            # cursor.execute("SELECT wds.addonName, wds.deviceName, wds.enabled, wds.configID FROM wds WHERE wdcode=%s",
            #                (wdcode,))
            cursor.execute("SELECT wds.addonName, wds.deviceName, wds.enabled, wds.configID, addons.gitURL, addons.commitHash, addons.defaultConfigID FROM wds LEFT JOIN addons ON wds.addonName = addons.addonName WHERE wds.wdcode=%s AND wds.addonName=%s AND wds.deviceName=%s ",(wdcode, addonName, deviceName))
            conn.commit()
            result = cursor.fetchone()
        except InternalServerError:
            return False, {"action": action, "comment": "InternalServerError on query on Table"}

        if result is None:
            comment = "No addons for this addonName and/or deviceName were found, did you install any Addons for this wdcode?"
            return False, {"action": action, "addonName": addonName, "deviceName": deviceName, "comment": comment}
        else: # meaning that we found the requested addon in the DB
            config = selectConfig(result[3])
            defaultConfig = selectConfig(result[-1])
            addonDetails = {"addonName": result[0], "deviceName": result[1], "enabled": result[2], "config": config,
                            "gitURL": result[4], "commitHash": result[5], "defaultConfig": defaultConfig}
            return True, {"action": action, "addon": addonDetails, "comment": "found a match"}

    else:  # can't get value from request data - return all installed addons
        comment = " returning all installed Addons for this WD code."
        try:
            # initial version was fetching only ADDOn data, so I made the query more complicated to fetch TYPE data aswell
            # cursor.execute("SELECT wds.addonName, wds.deviceName, wds.enabled, wds.configID FROM wds WHERE wdcode=%s",
            #                (wdcode,))
            cursor.execute("SELECT wds.addonName, wds.deviceName, wds.enabled, wds.configID, addons.gitURL, addons.commitHash, addons.defaultConfigID FROM wds LEFT JOIN addons ON wds.addonName = addons.addonName WHERE wds.wdcode=%s",(wdcode,))
            conn.commit()
            result = cursor.fetchall()
        except InternalServerError:
            return False, {"action": action, "comment": "InternalServerError on query on Types Table"}

        if result is None:
            comment = "No addons for this addonName and/or deviceName were found, did you install any Addons for this wdcode?"
            return False, {"action": action, "addonName": addonName, "deviceName": deviceName, "comment": comment}

        addonsArray = []
        for entry in result:
            config = selectConfig(entry[3])
            defaultConfig = selectConfig(entry[-1])
            addonDetails = {"addonName": entry[0], "deviceName": entry[1], "enabled": entry[2], "config": config, "gitURL": entry[4], "commitHash": entry[5], "defaultConfig": defaultConfig}
            addonsArray.append(addonDetails)

        return True, {"action": action, "addonsList": addonsArray, "comment": comment}


installAddon_schema = {
    "type": "object",
    "properties": {
        "info": {
            "type": "object",
            "properties": {
                "addonName": {"type": "string"},
                "timestamp": {"type": "number"},
            },
            "required": ["timestamp", "addonName"],
            "additionalProperties": False,
        },
    },
    "required": ["info"],
    "additionalProperties": False,
}
async def installAddon(data, code):
    '''
    Used whenever a user "installs" an addon. Will check if already installed, then create a NULL fall-back device relation if not.
    will Notify WD, if submitted by a user-client
    :param request: "addonName": {"type": "string"},
                "timestamp": {"type": "number"},
    :return:
    '''
    info = data["info"]
    action = data["action"]

    isUser, wdcode = checkIsUser(action, code)

    addonName = info["addonName"]

    try:
        cursor.execute('''SELECT wds.configID FROM wds WHERE wds.wdcode=%s AND wds.addonName=%s''',(wdcode, addonName))
        conn.commit()
        result = cursor.fetchone()
    except InternalServerError:
        comment = inter_serv_err + ", either RELATIONS Table is empty or (most probably) wdcode/addonName has no entries in the db"
        return False, {"action": action, "comment": comment}

    if result:
        comment = "This wdcode already has relations with the addonName, please use /getAddon to get a full list of already installed addons"
        return False, {"action": action, "comment": comment}

    else: # we setup a NULL device fall-back entry, that uses a COPY of the default config
        # check how the default config looks like
        selectTypeResult = selectType(addonName)
        if not selectTypeResult:
            return False, {"action": action, "comment": "No such addon Type was found? are you sure about the addon name?"}
        defaultConfigID = selectTypeResult[-1] # get defaultConfigID for this NULL device
        defaultConfigCopyJSON = json.dumps(selectConfig(defaultConfigID))
        newConfigID = updateConfig(defaultConfigCopyJSON) # when given w/o id, creates a new entry in the CONFIGS Table
        # now write this new config in the relation
        updateRelation(wdcode, addonName, null_device, newConfigID, enabled=True) # enabled bool is set to True by default
        comment = "created a new NULL device fall-back entry for this wdcode and addon relation with a fresh copy of the default config."

        if isUser:
            # print("installAddon: also sending to WD {} and to USR {}".format(wdcode, code))
            await websocket_manager.send({"success": True, "action": action, "addonName": addonName, "comment": comment}, wdcode)

        return True, {"action": action, "addonName": addonName, "comment": comment}


uninstallAddon_schema = {
    "type": "object",
    "properties": {
        "info": {
            "type": "object",
            "properties": {
                "addonName": {"type": "string"},
                "timestamp": {"type": "number"},
            },
            "required": ["timestamp", "addonName"],
            "additionalProperties": False,
        },
    },
    "required": ["info"],
    "additionalProperties": False,
}
async def uninstallAddon(data, code):
    '''
    similar to removeType but for a specific WD
    removes all traces of an addonTYPE from the DB, including WDS and CONFIG entries
    will Notify WD, if submitted by a user-client
    :param request: "addonName": {"type": "string"},
                "timestamp": {"type": "number"},
    :return:  "success": bool and "comment" string
    '''

    info = data["info"]
    action = data["action"]

    isUser, wdcode = checkIsUser(action, code)

    addonName = info["addonName"]

    result = selectType(addonName)

    # can't find this Type, something is wrong!
    if not result:
        comment = "No addon named {} in the Type Table, check your inputs or printout the Type Cataloge using getInstalledTypes with the Cataloge flag".format(
            addonName)
        return False, {"action": action, "addonName": addonName, "comment": comment}

    else:  # Type exists
        # we dont want to delete the default config, as it might be used elsewhere
        default_config_id = selectType(addonName)[-1]

        # now write down all the configs related to this Addon on this WD
        cursor.execute(
            "SELECT configID FROM wds WHERE wdcode=%s AND addonName=%s",
            (wdcode, addonName))
        conn.commit()
        unique_id_result = cursor.fetchall()  # NULL device is in this list!!

        # ... and also the relevant relations still left in the wds Table.
        cursor.execute("DELETE FROM wds WHERE wdcode=%s AND addonName=%s", (wdcode, addonName))
        conn.commit()

        # now we can safely remove the ids saved from before, without removing the defaultConfig
        if unique_id_result:
            for i in (unique_id_result):
                if i[0] == default_config_id:  # isDefaultConfig(i[0]): #  make sure we don't remove the defaultConfig for this Addon
                    continue
                cursor.execute("DELETE FROM configs WHERE configID=%s", (i[0],))
                conn.commit()

        comment = "removed addon named {} for wd {} from the Type Table, as well as any relations with the Addon's name in the wds Table and it's corresponding configs in the configs Table".format(
            addonName, wdcode)
        if isUser:
            # print("installAddon: also sending to WD {} and to USR {}".format(wdcode, code))
            await websocket_manager.send({"success": True, "action": action, "addonName": addonName, "comment": comment},
                                         wdcode)
        return True, {"action": action, "addonName": addonName, "comment": comment}


# create WebsocketManager and register actions
websocket_manager = WebsocketManager()
websocket_manager.register("uninstallAddon", uninstallAddon, schema=uninstallAddon_schema)
websocket_manager.register("removeType", removeType, schema=removeType_schema)
websocket_manager.register("installAddon", installAddon, schema=installAddon_schema)
websocket_manager.register("getType", getType, schema=getType_schema)
websocket_manager.register("getAddon", getAddon, schema=getAddon_schema)
websocket_manager.register("modifyAddon", modifyAddon, schema=modifyAddon_schema)
websocket_manager.register("modifyType", modifyType, schema=modifyType_schema)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    id, ws_wrapper = await websocket_manager.connect(websocket)
    # authentication failed
    if not id:
        return
    
    while websocket_manager.is_connected(ws_wrapper):
        success = await websocket_manager.listen(ws_wrapper)
        if not success:
            break
########################################################################################
# END OF WS
########################################################################################

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000)

Addon Service consists of three Tables: 

In the Addons Table, we define abstract addon types. Those entries include all the possible addon types, _**indepentant**_ of concrete user or configuration. This array is dynamic and will change in the future, as more addons will be added into the global list of available addons. For example here we will have an Addon called `ad-blocker v1.2` with it's current git URL, the latest commit hash and it's default config, which it uses per default when we first set it up somewhere.

Next Table, `wds` includes the main relation of wdcode, addonName and deviceName. This follows the notion that each WD controls a set of device son it's network, each of which has an array of possible addons. For example `WD_01` could control `Philips_hue` which has `Ad_blocker v1.2` and `ML v0.3`, while it's `Sonos_Move` device has only `Ad_blocker v1.2` enabled. 

In addition, it has a enabled bool and a configID serial number, pointing at the relevant entry in the Config table, which in turn corresponds to the relevant configuration dictionary for that specific addon. 

Lastly, `configs` table includes the aforementioned configID and its' corresponding config dict, that includes the BYTES formatting of a json dict.

One important detail is that although we want to have a relation for each possible wdcode, addon and device, it doesn't scale that well considering that most people would be using the same addon configuration for multiple devices. To avoid the bloat and keep tables small, we introduce the notion of NULL device. This is a fall-back device, that will be initiated on Addon install, which then weill be used by all devices for that WATCHDOG, as long as the config doesn't change. As soon as the user changes the config for one device, that device gets a unique config.

Due to the NULL-device being a Fall-back device whenever we install an Addon we need to keep in mind:
1. Whenever we query configs, we need to make sure we first check for unique config, and then for the fall-back NULL device config. if the query returns Asencding order, and we don't specify the deviceName, we will get the NULL device entry first. This is wrong, and cannot be adjusted with Descending order, as this might return a totally different DeviceName entry. Thus, we need to: 
   a. check for wdcode, addonName, deviceName. If found: return this unique entry.
   b. else: check for a NULL device entry. If not found this is an error and this addon was never installed in the first place. 
2. When adjusting configs, we don't actually change the NULL-device config, as it is the default config od the AddonType itself. Instead, we create a new entry in the WDS Table with a new config. 


Independently of internal helper functions, there are a few possible ways to interact with the Addon service (all functions besides the two POST remove/uninstall were ported to websocket!):

First the (addon) Type:

Get (addon)Type details or a LIST of all possible types (ex-getTypeCatalogue)
> getType(data, code):
```
   given AddonName, return the Type details and its default config
    if no AddonName is specified, you get a LIST of all possible Types (ex-TypeCatalogue)
    :param request:   "addonName": {"type": "string"}, [OPTINAL]
                      "timestamp": {"type": "number"},
    :return: Dict {addonName, gitURL, commitHash, defaultConfig} 
```


Setup a new Addon Type, with its gitURL, CommitHash and default configurations. Or alter it if it already exists. 
> modifyType(data, code):
```
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
```

Finally, removing an AddonType, we remove all related entries in AddonType Table, relations in the WDS Table and configs. 
> removeType(request: Request):
```
     cleanly removes all traces of an (addon)TYPE from the TYPE db, including WDS and CONFIG db entires that relate tot his Type
    :param request: "addonName": {"type": "string"},
                    "timestamp": {"type": "number"},
    :return:  "success": bool and "comment" string
```

Now to the more complicated part, the addons themselves (constructed out of relation + config):

Get Addon tails or a LIST of all enabled Addons (ex- getInstalledAddons)
> getAddon(data, code):
```
    for entire addon details, mainly for enabled bool and config
    - if no input is given, it returns a LIST all the enabled (i.e. installed) addons
    :param request: "deviceName" : {"type": "string"},
                "addonName": {"type": "string"},[OPTIONAL]
                "timestamp": {"type": "number"},
    :return:  "success": bool, "enabled": bool, "config": dict and "comment" string
    
```


One can "install" an addon on a WATCHDOG, by adding relations for each device it owns to this addonName. This also creates a NULL device that links those relations to a defaultConfiguration form the AddonType Table. Think of this as your "all devices initially use the default config"
> installAddon(request: Request):
```  
    Used whenever a user "installs" an addon. Will check if already installed, then create a NULL device if not.
    will Notify WD, if submitted by a user-client
    :param request: "addonName": {"type": "string"},
                     "timestamp": {"type": "number"},
    :return:
```

Adjusting addon (be it either the enabled bool or the config dict is done through the same function. This replaces both the old modifyConfig() and modifyEnabled(), mainly to avoid redundancy and make it easier to implement those in the frontend. 
Enabled: Disabled and again enabling the Relation. This doesn't remove any entry but simply flips the switch in the Relation WDS Table.
Config: changes the dict in the CONFIGS Table that relate to this device. If this is a device that has yet to have anything besides the fall-back NULL device, we will create a new config entry and change the configID.
> modifyAddon(data, code):
```
    Given Addon-device tupel, changes its related config AND/OR enabled bool
    if a NULL relation is present, we will create a new relation with the deviceName given.
    will Notify WD, if was submitted by a user-client
    :param request: "deviceName" : {"type": "string"},
                    "addonName": {"type": "string"},
                    [Optional] "config": {"type": "object"},
                    [Optional] "enabled": {"type": "boolean"},
                    "timestamp": {"type": "number"},
    :return: "success": bool and "comment" string
```


Same goes for "Uninstalling" an Addon for the WATCHDOG simply means we remove its relation entries in the main WDS Table. We also remove all the unique configs, without deleting the defaultConfig (which is used by other devices/Watchdogs). 
   > uninstallAddon(request: Request):
```
    similar to removeType but for a specific WD
    removes all traces of an addonTYPE from the DB, including WDS and CONFIG entries
    will Notify WD, if submitted by a user-client
    :param request: "addonName": {"type": "string"},
                     "timestamp": {"type": "number"},
    :return:  "success": bool and "comment" string
```

-----

All of the above take NULL device into account. This means that we check for NULL device and defaultconfigID all the time when we might remove/change one of the configs/addons, which are being used by MULTIPLE WDs.

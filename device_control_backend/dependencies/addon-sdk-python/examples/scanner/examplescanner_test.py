from bitahoy_sdk.addon.emulator.emulator import run_device_scanner, EmuDevice
from bitahoy_sdk.addon.utils import Device
from examplescanner import NopScanner


"""
This file is not really a test, but this file uses the sdk emulator to execute the addon in a similar way the client does. 

"""


if __name__ == "__main__":
    run_device_scanner(NopScanner, [EmuDevice("127.0.0."+str(n)) for n in range(10)], {})
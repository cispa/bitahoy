# TODO: add test user and wdcode info for server tests to import
import requests
from mockito import *
from backend_lib.test_credentials import CREDENTIALS
import subprocess
import sys
import pytest

addon_sdk_python_path = 'dependencies/addon-sdk-python/'
def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
try:
    install(addon_sdk_python_path)
    from bitahoy_sdk.backend import BackendWS
except Exception as e:
    print("Could not install {}".format(addon_sdk_python_path))
    print(e)

AUTH_URL = "https://auth.bitahoy.cloud"
# AUTH_URL = "http://localhost:9010"
logger = mock()

logger.verbose = print
logger.warn = print

class TestEntity:
    # suppress pytest warning
    __test__ = False

    def __init__(self, credentials):
        self.WDCODE = credentials["WDCODE"]
        self.SECRET = credentials["SECRET"]
        self.EMAIL = credentials["EMAIL"]
        self.PASSWORD = credentials["PASSWORD"]

        self.timeout = None


class TestUser(TestEntity):
    # suppress pytest warning
    __test__ = False

    def __init__(self, credentials):
        super().__init__(credentials)

    # returns a BackendWS object
    async def authenticate(self, URL):
        response = requests.post(AUTH_URL + "/login", json={"email": self.EMAIL, "password": self.PASSWORD})
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["token"] is not None

        ws = BackendWS(URL, get_token=lambda: response.json()["token"], logger=logger)
        await ws.authenticate()
        self.timeout = ws.timeout
        return ws


class TestClient(TestEntity):
    # suppress pytest warning
    __test__ = False

    def __init__(self, credentials):
        super().__init__(credentials)

    # returns a BackendWS object
    async def authenticate(self, URL):
        response = requests.get(AUTH_URL + "/authenticateWatchdog",
                                json={"wdcode": self.WDCODE, "secret": "[redacted-7]"})
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["token"] is not None

        ws = BackendWS(URL, get_token=lambda: response.json()["token"], logger=logger)
        await ws.authenticate()
        self.timeout = ws.timeout
        return ws



# There are 20 accounts
TESTUSERS = [TestUser(credentials) for credentials in CREDENTIALS]
TESTCLIENTS = [TestClient(credentials) for credentials in CREDENTIALS]


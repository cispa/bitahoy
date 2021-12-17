import pytest
import subprocess
import sys
import platform

def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

backend_lib_python_path = 'dependencies/backend_lib_python/'

try:
    install(backend_lib_python_path)
    from backend_lib.test_utils import TESTUSERS, TESTCLIENTS
except Exception as e:
    print("Could not install {}".format(backend_lib_python_path))
    print(e)


MONITORING_URL = "http://localhost:9000/ws"

@pytest.fixture(scope="session", autouse=True)
def pretest():
    pass

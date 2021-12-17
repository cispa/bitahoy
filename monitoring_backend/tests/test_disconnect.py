import asyncio
import pytest
from pretest import *
from backend_lib.test_utils import TESTUSERS, TESTCLIENTS

@pytest.fixture(autouse=True)
def run_around_tests():
    # Code that will run before your test, for example:
    pass
    # A test function will be run at this point
    yield
    # Code that will run after your test, for example:
    print("\n")
    pass

@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_disconnect():
    users = []
    clients = []
    amount_users = len(TESTUSERS)
    amount_clients = len(TESTCLIENTS)

    for i in range(0, amount_users):
        users.append(await TESTUSERS[i].authenticate(MONITORING_URL))
        print("Users authenticated {}".format(i))
    for i in range(0, amount_clients):
        clients.append(await TESTCLIENTS[i].authenticate(MONITORING_URL))
        print("Clients authenticated {}".format(i))

    # asyncio.create_task(start_listening())
    for user in users:
        print("send ping")
        res = await user.request({"action": "ping"})
        print("Response: {}".format(res))

    for client in clients:
        res = await client.request({"action": "ping"})
        print("Response: {}".format(res))

    user_disconnect_count = 0
    client_disconnect_count = 0
    for i, user in enumerate(users):
        await user.close()
        user_disconnect_count += 1
        print("Users closed {}".format(i))
    for i, client in enumerate(clients):
        await client.close()
        client_disconnect_count += 1
        print("Clients closed {}".format(i))

    assert user_disconnect_count == amount_users
    assert client_disconnect_count == amount_clients

    print("TEST DONE")


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_timeout():
    user = await TESTUSERS[0].authenticate(MONITORING_URL)
    print("User authenticated")
    timeout = user.timeout
    assert timeout is not None

    try:
        # sleep for longer than timeout
        await asyncio.sleep(timeout*1.2)
        # send a ping after waiting for more than timeout
        print(await user.request({"action": "ping"}))
        await user.close()
        pass
    except Exception as e:
        print("Exception: {}".format(e))
        assert False
    print("TEST DONE")






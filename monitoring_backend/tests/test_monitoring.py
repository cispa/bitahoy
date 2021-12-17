import pytest
import asyncio
import time
from functools import partial
from pretest import *
import random
from backend_lib.test_utils import TESTUSERS, TESTCLIENTS
from bitahoy_sdk.backend import BackendWS


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
@pytest.mark.timeout(10)
async def test_single_notification():
    ws = await TESTCLIENTS[0].authenticate(MONITORING_URL)
    # Authenticated!
    notifications = [{"level": 0, "time": time.time(), "sender": "Backend_Test", "message": "test message"}]
    data = await ws.request({"action": "uploadNotifications", "notifications": notifications})
    print(data)
    assert data["success"]

    data = await ws.request({"action": "getNotifications", "timewindow": 10})
    assert data["success"]
    assert len(data["notifications"]) == 1
    await ws.close()
    print("SUCCESS")


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_multiple_notifications():
    USER_AMOUNT = 10

    client_ws = await TESTCLIENTS[0].authenticate(MONITORING_URL)
    users = list()
    users_received_notifications = list()

    # the notifications to upload
    notifications = [{"level": 99, "time": time.time(), "sender": "Backend_Test", "message": "test message"}]

    # callback to check if users received notifications
    async def users_uploadNotifications_callback(index, response_data):
        assert response_data["success"]
        assert response_data["notifications"] == notifications
        users_received_notifications[index] = True
        print("User[{}] received {}".format(index, response_data))

    # log in multiple users
    for i in range(0, USER_AMOUNT):
        user_ws = await TESTUSERS[0].authenticate(MONITORING_URL)
        user_ws.register_callback("uploadNotifications", partial(users_uploadNotifications_callback, i))
        users.append(user_ws)
        users_received_notifications.append(False)

    # all users authenticated and connected
    # client uploads notifications
    data = await client_ws.request({"action": "uploadNotifications", "notifications": notifications})
    print("Client uploaded notifications")
    print(data)
    assert data["success"]

    # here we sleep a short amount of time b.c. the callbacks might be executed after the following lines
    # often not even necessary
    await asyncio.sleep(1)
    # this list should now be only filled with True
    for entry in users_received_notifications:
        assert entry is True

    print("Closing Websockets")
    await client_ws.close()
    for user in users:
        await user.close()
    print("SUCCESS")

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_multiple_notifications_with_multiple_clients():
    CLIENT_AMOUNT = 5
    USER_PER_CLIENT = 2

    clients = list()
    clients_to_user = dict()
    users_received_notifications = dict()

    # the notifications to upload
    notifications = [{"level": 99, "time": time.time(), "sender": "REPLACE", "message": "test message"*10},
                     {"level": 98, "time": time.time(), "sender": "REPLACE", "message": "test message"*20},
                     {"level": 97, "time": time.time(), "sender": "REPLACE", "message": "test message"*30},
                     {"level": 96, "time": time.time(), "sender": "REPLACE", "message": "test message"*40},
                     {"level": 95, "time": time.time(), "sender": "REPLACE", "message": "test message"*50}]

    # callback to check if users received notifications
    async def users_uploadNotifications_callback(client_index, user_index, response_data):
        print("User[{}][{}] received {}".format(client_index, user_index, response_data))
        assert response_data["success"]
        assert response_data["action"] == "uploadNotifications"
        received_notifications = response_data["notifications"]
        for i, received_notification in enumerate(received_notifications):
            # is this our WDCODE?
            assert received_notification["sender"] == TESTUSERS[client_index].WDCODE
            # is this the rest correct?
            assert received_notification["message"] == notifications[i]["message"]
            assert received_notification["time"] == notifications[i]["time"]
            assert received_notification["level"] == notifications[i]["level"]

        users_received_notifications[client_index][user_index] = True

    # log in multiple users
    for i in range(0, CLIENT_AMOUNT):
        clients_to_user[i] = []
        users_received_notifications[i] = []
        for j in range(0, USER_PER_CLIENT):
            user_ws = await TESTUSERS[i].authenticate(MONITORING_URL)
            user_ws.register_callback("uploadNotifications", partial(users_uploadNotifications_callback, i, j))
            clients_to_user[i].append(user_ws)
            users_received_notifications[i].append(False)
    # all users authenticated and connected
    # all clients login
    for i in range(0, CLIENT_AMOUNT):
        client_ws = await TESTCLIENTS[i].authenticate(MONITORING_URL)
        clients.append(client_ws)

    # send notifications
    rand_clients = random.sample(clients, CLIENT_AMOUNT)
    for rand_client in rand_clients:
        custom_notifications = []
        for notification in notifications:
            custom_notification = notification["sender"] = TESTCLIENTS[clients.index(rand_client)].WDCODE
            custom_notifications.append(custom_notification)
        # the sender of each notification is the WDCODE of the client and thus the users that receive it
        data = await rand_client.request({"action": "uploadNotifications", "notifications": notifications})
        assert data["success"]


    # here we sleep a short amount of time b.c. the callbacks might be executed after the following lines
    # often not even necessary
    await asyncio.sleep(1)
    # this list should now be only filled with True
    for user_list in users_received_notifications.values():
        for entry in user_list:
            assert entry is True

    print("Closing Websockets")
    for client in clients:
        await client.close()
    for user_list in clients_to_user.values():
        for user in user_list:
            await user.close()
    print("SUCCESS")

@pytest.mark.asyncio
@pytest.mark.timeout(300)
@pytest.mark.skip(reason="Takes too long")
async def test_large_scale():
    # large numbers (e.g. 100) of websocket connections in a single thread might lead to keepalive issues
    CLIENT_AMOUNT = 20
    USERS_PER_CLIENT = 4

    ITERATIONS = 10

    clients = list()
    clients_to_user = dict()
    users_received_notifications = dict()

    # the notifications to upload
    notifications = [{"level": 99, "time": time.time(), "sender": "REPLACE", "message": "test message"*10},
                     {"level": 98, "time": time.time(), "sender": "REPLACE", "message": "test message"*20},
                     {"level": 97, "time": time.time(), "sender": "REPLACE", "message": "test message"*30},
                     {"level": 96, "time": time.time(), "sender": "REPLACE", "message": "test message"*40},
                     {"level": 95, "time": time.time(), "sender": "REPLACE", "message": "test message"*50}]

    # callback to check if users received notifications
    async def users_uploadNotifications_callback(client_index, user_index, response_data):
        print("User[{}][{}] received {}".format(client_index, user_index, response_data))
        assert response_data["success"]
        assert response_data["action"] == "uploadNotifications"
        received_notifications = response_data["notifications"]
        for ind, received_notification in enumerate(received_notifications):
            # is this our WDCODE?
            assert received_notification["sender"] == TESTUSERS[client_index].WDCODE
            # is this the rest correct?
            assert received_notification["message"] == notifications[ind]["message"]
            assert received_notification["time"] == notifications[ind]["time"]
            assert received_notification["level"] == notifications[ind]["level"]

        users_received_notifications[client_index][user_index] = True


    users_received_notifications = dict()
    # log in multiple users
    for i in range(0, CLIENT_AMOUNT):
        clients_to_user[i] = []
        users_received_notifications[i] = []
        for j in range(0, USERS_PER_CLIENT):
            user_ws = await TESTUSERS[i].authenticate(MONITORING_URL)
            user_ws.register_callback("uploadNotifications", partial(users_uploadNotifications_callback, i, j))
            clients_to_user[i].append(user_ws)
            users_received_notifications[i].append(False)
    # all users authenticated and connected
    # all clients login
    for i in range(0, CLIENT_AMOUNT):
        client_ws = await TESTCLIENTS[i].authenticate(MONITORING_URL)
        clients.append(client_ws)

    for iteration in range(0, ITERATIONS):
        print("######################## ITERATION {} START #######################\n".format(iteration))
        # rewrite users_received_notifications
        for i in range(0, CLIENT_AMOUNT):
            users_received_notifications[i] = []
            for j in range(0, USERS_PER_CLIENT):
                users_received_notifications[i].append(False)


        # send notifications
        rand_clients = random.sample(clients, CLIENT_AMOUNT)
        for rand_client in rand_clients:
            custom_notifications = []
            for notification in notifications:
                custom_notification = notification["sender"] = TESTCLIENTS[clients.index(rand_client)].WDCODE
                custom_notifications.append(custom_notification)
            # the sender of each notification is the WDCODE of the client and thus the users that receive it
            data = await rand_client.request({"action": "uploadNotifications", "notifications": notifications})
            assert data["success"]


        # here we sleep a short amount of time b.c. the callbacks might be executed after the following lines
        # often not even necessary
        await asyncio.sleep(1)
        # this list should now be only filled with True
        for user_list in users_received_notifications.values():
            for entry in user_list:
                assert entry is True

        print("######################## ITERATION {} DONE ########################\n".format(iteration))

    print("Closing Websockets")
    for client in clients:
        await client.close()
    for user_list in clients_to_user.values():
        for user in user_list:
            await user.close()
    print("SUCCESS")




if __name__ == '__main__':
    test_single_notification()
    # test_multiple_notfications()

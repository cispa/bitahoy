# ML Service
## Setup
Using docker networks to communicate with auth service requiring the following adjustments to the docker-compose.yml file of the auth service:
```
version: '2'

volumes:
    database-data:

services:
    auth:
      build: .
      volumes:
        - ./src/:/app/
      ports:
        - 0.0.0.0:80:80 
      restart: always
      env_file:
        - ./.env
      networks:
        - auth-net
    auth_db:
      image: "postgres"
      env_file:
        - database.env
      volumes:
        - database-data:/var/lib/postgresql/data/
      networks:
        - auth-net
networks:
  auth-net:
    driver: bridge
 ```

Initially, execute ```setup_database.py setup```.
 
Further we require two authenticated clients to execute the websocket test thus I added another one manually into the auth db.
setup_test.py:
```
if sys.argv[1] == "setup":
    hashed = bcrypt.hashpw("password".encode('utf8'), bcrypt.gensalt()).decode("ascii")
    cursor.execute("INSERT INTO users(uid,email,password) VALUES(9999,'"+testmail+"',%s)",(hashed,))
    cursor.execute("INSERT INTO wdcodes(wdcode,uid) VALUES('xxxxxxxxxxxxxxxx',9999)")
    # second user
    cursor.execute("INSERT INTO users(uid,email,password) VALUES(1111,'" + testmail2 + "',%s)", (hashed,))
    cursor.execute("INSERT INTO wdcodes(wdcode,uid) VALUES('xxxxxxxxxxxxxxxx',1111)")
    conn.commit()
    print("SUCCESS!")

elif sys.argv[1] == "cleanup":
    cursor.execute("DELETE FROM users WHERE uid=9999")
    cursor.execute("DELETE FROM wdcodes WHERE uid=9999")
    cursor.execute("DELETE FROM users WHERE uid=1111")
    cursor.execute("DELETE FROM wdcodes WHERE uid=1111")
    conn.commit()
    print("SUCCESS!")
```
## Database
We are using 4 different tables to track:
- models: contains the actual binary for the model 
- devices: contains all devices (those to protect, not the wd itself) and a reference to the currently used model for this device
The deviceName is unique and the deviceType not yet used.
- wds: contains a pair of wd and deviceName to keep track of which wd protects which device.
- alarms: table with alarms the wd reports to the server.
## Tests
First all API endpoints are tested on their own but also tested in ```testWebsocket()```.
The general idea behind ```testWebsocket()``` is to mimic a use-case.

We have the server and two clients, one wd and one admin. The wd pulls a model and then reports some alarms to the server. 

The admin can see the alarms and decide that all clients with the model that cause the alarms have to pull a new Model. Alternatively he could also request all clients to rollback the model or pull a "blank model", a model that never causes an alarm.
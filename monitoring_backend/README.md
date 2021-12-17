![https://www.bitahoy.com](https://www.bitahoy.com) ![https://www.bitahoy.com](https://www.bitahoy.com)

# Monitoring Service

Backend service to handle all monitoring-related data of the watchdog.

## Tech stack

The service consists of 3 deployments that are meant to be deployed in the same kubernetes namespace.

- monitoring-service: Python service based on FastAPI. 1-n instances
- zmq-service: For backend to backend communication. 1 instance
- postgres database: 1 instance

## Dependencies

- [addonSDK](https://www.bitahoy.com-sdk-python)
- [backend_lib](https://www.bitahoy.com)
- [backend_zmq_sever](https://www.bitahoy.com)
- [Bitnami postgreSQL](https://hub.docker.com/r/bitnami/postgresql/)

# Deployment

The service is deployed on a kubernetes cluster using helm. 

## Local development

It is possible to spin up a local kubernetes cluster and observe the outcome of your changes immediately. For this purpose, we utilize Tilt.

### Set up tilt


Dependencies:

- Docker
- Tilt
```
curl -fsSL https://raw.githubusercontent.com/tilt-dev/tilt/master/scripts/install.sh | sudo bash
```
- Helm
```
curl https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 | bash
```
- ctlptl
```
CTLPTL_VERSION="0.5.0"
curl -fsSL https://github.com/tilt-dev/ctlptl/releases/download/v$CTLPTL_VERSION/ctlptl.$CTLPTL_VERSION.linux.x86_64.tar.gz | sudo tar -xzv -C /usr/local/bin ctlptl
```
- [kubectl](https://kubernetes.io/de/docs/tasks/tools/install-kubectl/)

- Kind (or any other local kubernetes cluster)
```
# install go
sudo apt-get install golang-go
# install kind
go get sigs.k8s.io/kind
# fix path
sudo ln -s $(go env GOPATH)/bin/kind /usr/bin/kind
# create cluster
sudo -s ctlptl create cluster kind --registry=ctlptl-registry
sudo ctlptl get cluster kind-kind -o template --template '{{.status.localRegistryHosting.host}}'
```

### Use Tilt

```
sude kubectl create namespace <namespace> # create namespace as specified in Tiltfile (if not already existing): e.g. auth, control, addon, ...
sudo tilt up
```

Service will be running at localhost:9000. You can open the tilt browser interface to restart pods and see the logs. The pods may restart automatically of you make changes to the files.

If you want to forward a local port to the watchdog for testing, use ssh port forwarding:

```
ssh -R 9000:localhost:9000 watchdog
```

### Tests in Tilt

You can run the tests from the tilt webinterface, or via the commandline:
```
sudo tilt ci
```
This is also how the CI/CD pipeline runs the tests.


For mor info about tilt, see the documentation of tile.



# API reference
## Logs
### Storing Logs
Every watchdog can submit logs with the action "uploadLogs" in the format

`{"level": level, "time": time.time(), "sender": event.sender, "message": message}`

Every Log entry will be stored in the database. Because the db would explode otherwise, every CLEANUP_INTERVAL seconds entries that are older than LOGS_TIMEWINDOW seconds are removed from the db.
These values are controlled via the .env file
````
CLEANUP_INTERVAL = 5
LOGS_TIMEWINDOW = 60
````

That means there will never be logs that are older than, in this case, one minute. 

Change as you please.

### Getting Logs
The websocket action "getLogs" can be used to retrieve log entries. The request needs to have the following format:
`{"timewindow": 10, <"sender": specific_sender>, <"level": specific_level>}`

where `sender` and `level` are optional filters. The `timewindow` specifies that only logs no older than timewindow seconds will be returned.
> Remember that logs are periodically purged based on time.

### Storing Notifications
Every watchdog can submit logs with the action "uploadNotifications" in the format

`{"level": level, "time": time.time(), "sender": event.sender, "message": message}`

Notifications are not cleared currently. But this might change at any time, don't rely on it,

That means there will never be logs that are older than, in this case, one minute. 

Change as you please.

### Getting Notifications
The websocket action "getNotifications" can be used to retrieve log entries. The request needs to have the following format:
`{"timewindow": 10, <"sender": specific_sender>, <"level": specific_level>}`

where `sender` and `level` are optional filters. The `timewindow` specifies that only logs no older than timewindow seconds will be returned.



# Notes
- The `testLogsCleanUp` test might take a while to execute depending on `LOGS_TIMEWINDOW` therefore consider commenting it out.

# Auth Service

Backend service to handle user management and authentication. Provides signed auth tokens to use in other backend services, and the public key to verify it.

## Tech stack

The service consists of 2 deployments that are meant to be deployed in the same kubernetes namespace.

- auth-service: Python service based on FastAPI. 1-n instances
- postgres database: 1 instance

## Dependencies

- [backend_lib](https://www.bitahoy.com)
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

### Database:

There are 3 tables used for this server. Max values are and should be enforced by the endpoints.

* users:

  uid:int, email:varchar(50), password:varchar(70)

* wdcodes:

  wdcode:varchar(20), uid:int

* pending:

  token:varchar(64), type:int, time:bigint email:varchar(50), password:varchar(70), wdcode:varchar(20)
  
An additional table "key" is present and holds the (history) of private/public keys to be used by the auth server.
This table is populated only by sysadmins or by the start of the docker container with the prestart.sh file.

### Endpoints:

All the endpoints return {"success":True} iff the sent request was handled successfully.

* post("/register", status_code=201)

  Used for registration. Sent request must contain key/value pairs for: "email", "password" and "wdcode".
  Tries to send an email to the specified email containing a link to activate the account (valid for 10 minutes)
  
* get("/verifyEmail?token={token}", status_code=201)

  Used for registration. The token the client received via email is embedded into the link.
  Tries to send a success email.
	
* get("/requestPasswordReset")

  Used to reset the password. Sent request must contain key/value pair for: "token".
  Checks if the submitted token is valid. If so sends an email to the users, which contains a link to reset the password (valid for 10 minutes)

* post("/resetPassword?token={token}")

  Used to reset the password. The token the client received via email is embedded into the link.
  Send request must contain key/value pair for: "password".
  Tries to send a success email.
		
* post("/login")

  Used to login. Sent request must contain key/value pair for: "email" and "password".
  On success returns a response containing {"success":True, "token":token}, where the token may be used to authenticate at different servers for 36 hours.

* get("/authenticateWatchdog")

  Used only by the watchdog. Request contains a key/value pair for "wdcode".
  Responds with the same as /login.

* get("/validate")

  Can, but should <b>NOT</b> be used to validate a token that is submitted in the Request as K/V pair for "token".
  Instead use /requestPublicKey and do the authentication yourself.
		
* get("/requestToken")

  Can be used to exchange a currently valid token for a fresher one. This prevents the needs for logging in frequently.
  Currently valid token must be submitted in the request as K/V pair for "token".

* get("/requestPublicKey")

  Can be used to query the current PK of the authentication server. Should be used by other servers to authenticate users by themselves.
  Returns a reponse containing {"publickey":pk}
  NOTE: There is no key revokation capability. The key should be refreshed frequently.
  
  
* get("/addCodes")

  This admin-only-access endpoint is constructed to push new wdcodes to the database.
  The sent request should contain a K/V pair for "pw", that is used for authentication of the admin.
  Furthermore a list of new codes is expected as "codes". The response will contain "success" and if success is true a list of invalid codes as "comment".
  
### Testing and Setup

In the source folder and docker container the following files can be found:

* setup_database.py

  Can be used to setup the databases or drop them. This is mainly needed for testing and development process, handle with care.
  
* setup_test.py

  Must be executed for the device_control_service to be able to execute it's tests. After testing execute it again with "cleanup" to get rid of testing artifacts.
  
* test.py 

  Runs the tests for the auth_service. Depends on a setup database.


### How to user / Examples:

First of all: Check out the test.py file in /src.

* Obtain the message and signature from a token:

```
  response = ... #login post request or similar
  token = response.json()["token"]
  message = token["code"]+str(token["id"])+str(token["time"])
  signature = base64.b64decode(token["signature"])
```

* Authenticate locally by requesting the public key:
 ```
  k = client.get("/requestPublicKey")
  key = serialization.load_pem_public_key(k.json()["publickey"].encode('utf-8'), backend=default_backend())
  try:
	key.verify(signature, message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
  except:
	assert False
```

### Maintanance:

* The database credentials are located in the beginning of the app.py in /src together with some magic values

* The email server to user must be configured in the sendEmail function in app.py

* The email messages sent out by the server are created in the corresponding endpoints

* Requirements for password/email/... are done by regex matching. Regexes can be found at the top of app.py near the magic values 

### Security:

* Crypto Lib used: https://github.com/pyca/cryptography

* The server relies on an encrypted connection to the user (TLS).

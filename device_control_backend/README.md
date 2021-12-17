# Device Control Service

This is the core backend implementation. Clients and Users can connect to the server with a websocket.

### Communication Protocol

Communication is done via JSON commands. In the following "client" may refer to clients as well as actuall users.
First the client needs to authenticate itself by submitting a JSON string that contains the authentication token that was received earlier by the authentication server.
Format: `{"token":<token>}`, where <token> should be replaced by the actual token string.
Note that the user has exactly one try and a very limited amount of time to submit this token, after opening the websocket.
If the client is not fast enough the websocket will be closed again.

The client will now receive either a `{"success":True}` or a `{"success":False}`.
If False is received, i.e. the client authentication failed, the websocket is closed immediately.

Now that the client is authenticated it can send commands to the server to execute by sending:<br/>
`{"action":<command> ?[,<requiredData>:<data>]?}`<br/>
An example would be:<br/>
`{"action":"updateType","deviceid":1234,"devicetype":DeviceType.OTHER.value}`<br/>
The server will try to execute the command and reply with:<br/>
`{"success":<Bool>, "action":<command>, ?<data>:<ResultOfCommand>?}`<br/>

Note that the server's response may ALWAYS (also for the authentication) contain an additional K/V pair `"comment":\<comment\>`,
where comment yields additional information about why the execution might have failed or any warnings.

Connections will timeout after a specific amount of time. To avoid that the client can send a ping-command every now and then to reset the timeout.
The server does NOT reply to ping commands.

To gracefully close the connection the client should send a disconnect command, wait for the reply and then close the websocket.

### Commands

* disconnect (user and client)

* ping (user and client)

* requestInfo (user and client)

* registerDevice (client only)

* updateType (client only)

* updateStatus (user and client)

* updateOption (user only)

### Enums

For in commands always the values are passed!

* Option

  The values are the valid options that can be passed in the updateOption command

* MailPolicy

  Contains the valid values for the email setting.
  
* Status

  Contains the valid values for the status setting.
  
* DeviceType

  Contains the valid values for the device type.

# arpjet

Arpjet is a traffic monitor and interceptor for home networks, allowing blocking modifying and intercepting traffic of devices vulnerable to ARP spoofing.
Note that some modern routers prevent forwarding APR messages with conflicting IP Addresses, so it may not work in every network.
The arpjet heavily communicates with the could, that in additionally communicates with the customer's app, where he can modify rules for certain devices or just monitor logged in devices.    
Our active device identification detects the capabilities of many devices and presents them to the user in via the app.
While arpjet can be run on a RaspberryPi4 without problems the python application is too heavy for embedded devices as a lot of processes are spawned and 2GB of RAM may be used.    
We plan to decrease this resource usage in the future by offloading tasks to the kernel or the network card.

## Running arpjet

`sudo python3 ./arpjet.py`

## Config

The config is stored at `./config.json`:

```json
{
  "deviceid": "bitahoy_dev003",
  "cloud": {
    "auth": {
      "wdcode": "xxxxxxxxxxxxxxxx"
    }, 
    "control": {
    }
  }
}

```

### Authenticating a wdcode to the cloud
A valid wdcode is required to communicate with the backend and enable arpjet functionality.
In order to regiser a wdcode you need to make a get request to the auth.bitahoy.cloud/addCodes endpoint with a json of type `{"pw": password, "codes": [your_code]}` and afterwards register on the normal backend with that wdcode.

# Install as systemd service

To setup arpjet as systemd service:

```
cp /arpjet/arpjet.service /etc/systemd/system/arpjet.service
systemctl start arpjet
```

If you want to start arpjet on system boot for true plug&play experience:

```
systemctl enable arpjet
```

# Project strcture
Goal of the client is to have as little state as possible, to enable effective crash recovery.
To handle the workload in python each module is run as its separate subprocess which in turn make heavy use of the asyncio library.
Queues are passes to modules for communication with other processes.
Modules to not need direct handles to each other queues as the master module has routing capabilities.
Once created there is no handle other than a subprocess to a module, meaning that all communication channels and data should be present at startup, or passed to the modules via Events through the IPC queues.

# Debugging arpjet
Logs are in general verbose and can be grepped for interested modules.   
Use `PYTHONTRACEMALLOC=1 PYTHONASYNCIODEBUG=1 python3 arpjet.py` to trace asyncio problems like unawaited coroutines.
Also interactively debugging Modules can be achieved by using `remote_pdb`.   
```python
from remote_pdb import RemotePdb; RemotePdb('127.0.0.1', 4444).set_trace()
```
And in another terminal run after the breakpoint was reached:   
```bash
telnet localhost 4444
```

## Tracing arpjet
Tracing globally is not possible as the modules are run in separate processes.
The tool `viztrace` can be used to trace the modules.
Make sure to install viztrace with `pip3 install viztrace`.
To attach to a process run `viztracer --attach <pid> -t <seconds> --log_async`.
A file called `result.json` is placed inside the current working directory of the traced process.
In order to trace a process you must include 
```python3
    from viztracer import VizTracer
    tracer = VizTracer()
    tracer.install()
```
To view the results run `vizviewer --server_only -p 9001 results.json`.
If arpjet is not reachable you can bridge the ports using ssh like:
`ssh -L 8080:127.0.0.1:8090 arpjet` to forward the port 8090 to port 8080 on your local machine.

To use the webserver you can use WASD to navigate and click on bars to open the source code.

# Writing tests for arpjet
As modules are started as separate processes, writing good tests is hard.
While the conftest.py in the watchdog folder has some nice fixtures to spawn modules, it is impossible with them to access internal state variables of the module, unless it is not started as its own process.
Integration tests can use a virtual network, allowing to send specific packets without noise.
We also have a fixture that captures traffic, which is useful to assert certain actions were take by a module such as sending arp requests.
The packet capture never contains the most recently sent packet.

# Using commit hooks
To improve code quality we added the [`pre-commit`](https://pre-commit.com/) package to requirements.txt.   
Simply run `pre-commit install` inside the repo.   
Then before committing it runs:   
1. [black](https://github.com/psf/black): automatically beautifies code:   
	You need to add the changes in order to commit.
	If `test.py` was modified you have to `git add test.py` before committing again to accept the changes.

2. [flake8](https://github.com/PyCQA/flake8/tree/3.9.2): lints the code and shows you unused variables or imports.   
	For violations starting with B you can look then up [here](https://pypi.org/project/flake8-bugbear/) as they are part of bugbear. The rest (E and W) can be found [here](https://www.flake8rules.com/).   
	If you believe that the way you are doing things is correct and pylint is too strict you can do the following:   

	`example = lambda: 'example'` violates *E731*. If you really need this lambda add:   
	`example = lambda: 'example'  # noqa: E731` the comment, so the error is ignored by the linter.
	
3. [bandit](https://bandit.readthedocs.io/en/latest/plugins/index.html#complete-test-plugin-listing): finds potential security vulnerabilities   
	After evaluating if highlighted problems are security relevant, you can fix the issue or comment the affected line out with `# nosec` to silence the warning.   
	This seems quite sensitive and is definitely an experimental addition to ci.

4. [isort](https://pycqa.github.io/isort/): reorders your imports

5. [mypy](https://mypy.readthedocs.io/en/stable/index.html): does variable type checking. If you need to ignore something use `# type: ignore`

6. [pytest](https://github.com/pytest-dev/pytest): runs our tests.   
	Caveats: Tests are run on the state of the repository that would be committed. That means if you modified a test that is not included in the commit it won't fail. You can directly run `pytest` to see if that is the case.

## Skipping hooks
If you need to skip a hook, e.g. because you wrote tests showing a bug and need to skip the pytest hook (because you want somebody else to fix the problem) you can run `SKIP=pytest git commit` to disable pytests for that commit. Please refrain from adding `SKIP` permanently to your env, since it decreases our CI performance.

# Compiling arpjet
Theis is a beta feature that may give additional performance by compiling the python code into an elf with the help of [nuitka](https://github.com/Nuitka/Nuitka).    
```python3 -m nuitka arpjet.py --follow-import-to=watchdog --follow-import-to=bitahoy_sdk --standalone --onefile --show-progress --linux-onefile-icon=./favicon.ico```

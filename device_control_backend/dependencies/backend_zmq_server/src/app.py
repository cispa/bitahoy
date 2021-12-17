import socket
from socket import AF_INET, SOCK_STREAM
import json
import asyncio
import traceback
import os
from slack import WebClient

class DeviceControl:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr

connectedDCs = []
pendingQueries = {} # Query ID -> [[addrs of DCs who still need to answer],DC who initiated]
cache = {} #caching wdcode -> [(dc,age)] (list because there could be multiple connected instances)
#Max entry age is 1 hour
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(('0.0.0.0',9000))
slack = WebClient(os.environ.get('SLACK_BOT_TOKEN'))

withCache = os.getenv("WITH_CACHE")

async def cleanup(dc):
    #Called on crash, disconnect etc. to cleanup the queries
    loop = asyncio.get_running_loop()
    try:
        connectedDCs.remove(dc)
    except:
        print(str(dc.addr)+" was not present in connectedDCs anymore")
    for pqk in pendingQueries.keys():
        try:
            pendingQueries[pqk][0].remove(dc.addr)
            if len(pendingQueries[pqk][0]) <= 0:
                await loop.sock_sendall(pendingQueries[pqk][1].conn, json.dumps({"type":"rep","success":False,"id":pqk}).encode())
        except ValueError:
            #Remove failed, because dc was not queried for this id. We can ignore it!
            pass
     
    if withCache:
        for ce in cache.keys():
            #Remove cache entry (if exists)
            cache[ce] = list(filter(lambda x: x[0] != dc, cache[ce]))
        
    dc.conn.close()


async def handleDC(dc):
    global connectedDCs, pendingQueries, sock
    try:
        loop = asyncio.get_running_loop()

        connectedDCs += [dc]

        while True:
            msg = ""
            cc = 0
            while not msg or cc != 0:
                s = await loop.sock_recv(dc.conn,1)
                if not s:
                    print(str(dc.addr)+" closed connection")
                    await cleanup(dc)
                    return
                s = s.decode("utf-8")
                for c in s:
                    if c == "{":
                        cc += 1
                    if c == "}":
                        cc -= 1
                msg += s

            print("Received "+msg)
            data = json.loads(msg)
            type = data["type"]
            id = data["id"]

            if type == "req":
                message = data["msg"]
                wdcode = data["wdcode"]
                
                if withCache:
                    try:
                        #First filter out old entries
                        cache[wdcode] = list(filter(lambda x: time.time()-x[1] < 3600, cache[wdcode]))
                        assert len(cache[wdcode]) > 0
                        
                        #Now send query to all cached entries
                        l = []
                        for e in cache[wdcode]:
                            l.append(e[0])
                        pendingQueries[id] = [l,dc]
                    
                        for d in l:
                            try:
                                await loop.sock_sendall(connDC.conn, json.dumps({"type":type,"msg":message,"wdcode":wdcode,"id":id}).encode())
                            except TimeoutError:
                                print(str(connDC.addr)+" timed out during send!")
                                await cleanup(connDC) #Also removes from cache
                                return
                            
                        continue
                    except KeyError:
                        pass
                
                #So it is not cached...
                l = []
                for cdc in connectedDCs:
                    l.append(cdc.addr)
                pendingQueries[id] = [l,dc]
                
                #Broadcast
                for connDC in connectedDCs:
                    try:
                        await loop.sock_sendall(connDC.conn, json.dumps({"type":type,"msg":message,"wdcode":wdcode,"id":id}).encode())
                    except TimeoutError:
                        print(str(connDC.addr)+" timed out during send!")
                        await cleanup(connDC)
                        return

            elif type == "rep":
                success = data["success"]
                
                if success:
                    try:
                        await loop.sock_sendall(pendingQueries[id][1].conn, json.dumps({"type":"rep","success":True,"id":id}).encode())
                        del pendingQueries[id]
                        print("Query "+id+" was successful")
                    except KeyError:
                        #Another DC also found matching receiver (User has more than 1 connection)
                        pass
                        
                    if withCache:
                        wdcode = int(id.split("-")[0])
                        #Update cache
                        try:
                            cache[wdcode] = list(filter(lambda x: x[0] != dc, cache[wdcode])).append((dc,time.time()))
                        except KeyError:
                            #New cache entry!
                            cache[wdcode] = [(dc,time.time())]
                    
                else:
                    try:
                        pendingQueries[id][0].remove(dc.addr)
                    except KeyError:
                        continue
                        
                    if len(pendingQueries[id][0]) <= 0:
                        print("Query "+id+" was not successful")
                        await loop.sock_sendall(pendingQueries[id][1].conn, json.dumps({"type":"rep","success":False,"id":id}).encode())
                        del pendingQueries[id]
                        
                    if withCache:
                        wdcode = int(id.split("-")[0])
                        #Remove cache entry (if exists)
                        try:
                            cache[wdcode] = list(filter(lambda x: x[0] != dc, cache[wdcode]))
                        except KeyError:
                            pass #Not present

            else:
                print("Received strange request: "+type)
                await loop.sock_sendall(conn, json.dumps({"type":type,"success":False}).encode())
    except:
        await cleanup(dc)
        print("Connection died with exception: ")
        tb = traceback.format_exc()
        try:
            slack.chat_postMessage(channel='#stacktraces',text=tb)
        except:
            pass
        finally:
            traceback.print_exc()



async def waitForConnections():
    tasks = []
    loop = asyncio.get_running_loop()
    try:
        sock.setblocking(0)
        sock.listen(10)
        print("Waiting for connections...")
        while True:
            connection, address = await loop.sock_accept(sock)
            connection.setblocking(0)
            print("connected to {}:{}".format(*address))
            u = DeviceControl(connection,address)
            tasks += [loop.create_task(handleDC(u))]
    finally:
        for task in tasks:
            await task


asyncio.run(waitForConnections())

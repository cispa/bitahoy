import psycopg2
import sys
import os

conn = psycopg2.connect("dbname='db' user='db' host='{}' [redacted-2]".format(os.environ.get("DB_HOST")))
conn.autocommit = True
cursor = conn.cursor()

if len(sys.argv) < 2:
    print("Please provide the command. Give 'help' as arg to see all cmds")
    
if sys.argv[1] == "setup":
    #Use wdcodes as GENERAL table for global settings etc.
    cursor.execute("CREATE TABLE IF NOT EXISTS wdcodes (wdcode varchar(20) UNIQUE PRIMARY KEY, email varchar(50), mailpolicy int)")
    cursor.execute("CREATE TABLE IF NOT EXISTS devices (wdcode varchar(20), deviceid bigint, PRIMARY KEY(wdcode,deviceid), devicetype bigint, status int)")
    cursor.execute("CREATE TABLE IF NOT EXISTS optionals (wdcode varchar(20), deviceid bigint, key varchar(80), value varchar(2048), PRIMARY KEY(wdcode,deviceid,key))")
    conn.commit()
    print("SUCCESS!")

elif sys.argv[1] == "drop":
    cursor.execute("DROP TABLE wdcodes")
    print("Dropped wdcodes!")
    cursor.execute("DROP TABLE devices")
    print("Dropped devices!")
    cursor.execute("DROP TABLE optionals")
    print("Dropped optionals!")
    conn.commit()
    print("SUCCESS!")
    
elif sys.argv[1] == "list":
    print("WDCODES:")
    print("wdcode".ljust(18)+"|"+("email".ljust(60))+"|"+("mailpolicy".ljust(10)))
    print("".ljust(90,"-"))
    cursor.execute("SELECT * FROM wdcodes")
    res = cursor.fetchall()
    for row in res:
        wdcode = row[0] if row[0] else "NOTPROVIDED"
        email = row[1] if row[1] else "NOTPROVIDED"
        mailpolicy = str(row[2]) if str(row[2]) else "NOTPROVIDED"
        print(wdcode.ljust(18)+"|"+email.ljust(60)+"|"+mailpolicy.rjust(10))
    
    print("\nDEVICES:")
    print("wdcode".ljust(18)+"|"+("deviceid".rjust(20))+"|"+("devicetype".rjust(20))+"|"+("status".rjust(10)))
    print("".ljust(71,"-"))
    cursor.execute("SELECT * FROM devices")
    res = cursor.fetchall()
    for row in res:
        wdcode = row[0] if row[0] else "NOTPROVIDED"
        deviceid = str(row[1]) if str(row[1]) else "NOTPROVIDED"
        devicetype = str(row[2]) if str(row[2]) else "NOTPROVIDED"
        status = str(row[3]) if str(row[3]) else "NOTPROVIDED"
        print(wdcode.ljust(18)+"|"+deviceid.rjust(20)+"|"+devicetype.rjust(20)+"|"+status.rjust(10))
        
    print("\nOPTIONALS:")
    print("wdcode".ljust(18)+"|"+("deviceid".rjust(20))+"|"+("key".ljust(60))+"|"+("value".ljust(60)))
    print("".ljust(158,"-"))
    cursor.execute("SELECT * FROM optionals")
    res = cursor.fetchall()
    for row in res:
        wdcode = row[0] if row[0] else "NOTPROVIDED"
        deviceid = str(row[1]) if str(row[1]) else "NOTPROVIDED"
        key = row[2] if row[2] else "NOTPROVIDED"
        value = row[3] if row[3] else "NOTPROVIDED"
        print(wdcode.ljust(18)+"|"+deviceid.rjust(20)+"|"+key.ljust(60)+"|"+value.ljust(60))
  
else:
    print("Possible commands:")
    print("setup")
    print("drop")
    print("list")

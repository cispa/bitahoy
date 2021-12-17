import psycopg2
import string
import sys
import os

conn = psycopg2.connect("dbname='auth_db' user='auth_db' host='authdb' [redacted-2]")
cursor = conn.cursor()

if len(sys.argv) < 2:
    print("Too few arguments. Try 'setup' or 'drop'!")

elif sys.argv[1] == "setup":
    cursor.execute("CREATE TABLE IF NOT EXISTS users (uid int UNIQUE PRIMARY KEY, email varchar(50) UNIQUE, password varchar(70), permissions int)")
    cursor.execute("CREATE TABLE IF NOT EXISTS wdcodes (wdcode varchar(20) UNIQUE PRIMARY KEY, uid int, secret varchar(20))")
    cursor.execute("CREATE TABLE IF NOT EXISTS pending (token varchar(64) UNIQUE PRIMARY KEY, type int, time bigint, email varchar(50) UNIQUE, password varchar(70), wdcode varchar(20))")
    conn.commit()
    print("SUCCESS!")
    
elif sys.argv[1] == "drop":
    cursor.execute("DROP TABLE users")
    print("Dropped users!")
    cursor.execute("DROP TABLE wdcodes")
    print("Dropped wdcodes!")
    cursor.execute("DROP TABLE pending")
    print("Dropped pending!")
    conn.commit()
    print("SUCCESS!")

  
else:
    print("Possible commands:")
    print("setup")
    print("drop")

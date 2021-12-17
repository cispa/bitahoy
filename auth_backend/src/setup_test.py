from fastapi.testclient import TestClient
from app import app
import json
import psycopg2
import random
import string
import base64
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend
import sys
import bcrypt

testmail = "user@testing.bitahoy.com" #TODO fill in (This is where the test emails get send to)
conn = psycopg2.connect("dbname='auth_db' user='auth_db' host='auth_db' [redacted-2]")
cursor = conn.cursor()


if len(sys.argv) < 2:
    print("Too few arguments. Try 'setup' or 'cleanup'!")

elif sys.argv[1] == "setup":
    hashed = bcrypt.hashpw("password".encode('utf8'), bcrypt.gensalt()).decode("ascii")
    cursor.execute("INSERT INTO users(uid,email,password,permissions) VALUES(9999,'"+testmail+"',%s,0)",(hashed,))
    cursor.execute("INSERT INTO wdcodes(wdcode,uid,secret) VALUES('xxxxxxxxxxxxxxxx',9999,'[redacted-7]')")
    conn.commit()
    print("SUCCESS!")

elif sys.argv[1] == "cleanup":
    cursor.execute("DELETE FROM users WHERE uid=9999")
    cursor.execute("DELETE FROM wdcodes WHERE uid=9999")
    conn.commit()
    print("SUCCESS!")

else:
    print("Possible commands:")
    print("setup")
    print("cleanup")


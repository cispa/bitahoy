import sys
import os
import psycopg2
import base64
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend
import time


if len(sys.argv) < 2:
    print("Please enter either create or remove as a argv[1]")
    sys.exit(0)

with psycopg2.connect("dbname='auth_db' user='auth_db' host='authdb' [redacted-2]") as conn:
    with conn.cursor() as cursor:
    
        if sys.argv[1] == "generate":

            #Load the key or generate a new one:
            cursor.execute("CREATE TABLE IF NOT EXISTS key (key varchar(4096),time bigint UNIQUE PRIMARY KEY)")
            privkey = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
            pem = privkey.private_bytes(encoding=serialization.Encoding.PEM,format=serialization.PrivateFormat.TraditionalOpenSSL,encryption_algorithm=serialization.NoEncryption())
            cursor.execute("INSERT INTO key (key,time) VALUES('"+str(pem.decode("utf-8"))+"',"+str(int(time.time()))+")")
            conn.commit()
                
            print("New key generated!")
            
        elif sys.argv[1] == "generate_if_needed":

            #Load the key or generate a new one:
            cursor.execute("CREATE TABLE IF NOT EXISTS key (key varchar(4096),time bigint UNIQUE PRIMARY KEY)")
            cursor.execute("SELECT * FROM key")
            res = cursor.fetchall()
            if len(res) == 0:
                privkey = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
                pem = privkey.private_bytes(encoding=serialization.Encoding.PEM,format=serialization.PrivateFormat.TraditionalOpenSSL,encryption_algorithm=serialization.NoEncryption())
                cursor.execute("INSERT INTO key (key,time) VALUES('"+str(pem.decode("utf-8"))+"',"+str(int(time.time()))+")")
                conn.commit()
                print("New key generated, as database was empty!")
            else:
                print("Database has key ready!")

        elif sys.argv[1] == "drop":
            
            cursor.execute("DROP TABLE key")
            conn.commit()
            
            print("Dropped old keys")

        else:
            print("Invalid option! Try 'drop', 'generate' or 'generate_if_needed'...")
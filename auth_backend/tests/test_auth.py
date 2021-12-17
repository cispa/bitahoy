import random
import string
import pytest
import psycopg2
import base64
import requests
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend


client = requests.session()
baseurl = "http://localhost:9000"
conn = psycopg2.connect("dbname='auth_db' user='auth_db' host='localhost' port='9001' [redacted-2]")
cursor = conn.cursor()
testmail = "user@testing.bitahoy.com" #TODO fill in (This is where the test emails get send to)


@pytest.fixture(autouse=True)
def run_around_tests():
    # Code that will run before your test, for example:
    conn = psycopg2.connect("dbname='auth_db' user='auth_db' host='localhost' port='9001' [redacted-2]")
    cursor = conn.cursor()
    # A test function will be run at this point
    yield
    cursor = conn.cursor()
    cursor.close()
    conn.close()
    print("\n")
    pass

@pytest.fixture(scope="session", autouse=True)
def execute_before_any_test():
    # your setup code goes here, executed ahead of first test
    conn = psycopg2.connect("dbname='auth_db' user='auth_db' host='localhost' port='9001' [redacted-2]")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE email='"+testmail+"'")
    cursor.execute("DELETE FROM wdcodes WHERE wdcode='xxxxxxxxxxxxxxxx'")
    cursor.execute("DELETE FROM wdcodes WHERE wdcode='ZZZZYYYYXXXX9999'")
    cursor.execute("INSERT INTO wdcodes(wdcode,uid) VALUES('xxxxxxxxxxxxxxxx',-1)")
    conn.commit()

    yield

    
    cursor.execute("DELETE FROM users WHERE 1=1")
    cursor.execute("DELETE FROM wdcodes WHERE 1=1")
    cursor.execute("DELETE FROM pending WHERE 1=1")
    conn.commit()
    cursor.close()
    conn.close()
    pass

def sanityCheck():
    response = client.get(baseurl+"/")
    assert response.status_code == 200
    assert response.json() == {
        "Hello": "World"
    }
        
def testRegisterPositive1():
    response = client.post(baseurl+"/register",json={"email":testmail, "password": "Password1", "wdcode":"xxxxxxxxxxxxxxxx"})
    assert response.status_code == 201
    assert response.json()["success"] == True
    cursor.execute("SELECT * FROM pending")
    result = cursor.fetchall()
    assert len(result) == 1
    assert result[0][1] == 0 #Type
    
def testRegisterNegative1():
    response = client.post(baseurl+"/register",json={"email":testmail, "password": "Password1", "wdcode":"xxxxxxxxxxxxxxxx"})
    assert response.status_code == 201
    assert response.json()["success"] == False
    
    
def testVerifyEmailPositive1():
    cursor.execute("SELECT * FROM pending")
    result = cursor.fetchall()
    url = "/verifyEmail?token={}".format(result[0][0])
    response = client.get(baseurl+url)
    assert response.status_code == 201
    assert response.json()["success"] == True
    return

def testVerifyEmailNegative1():
    cursor.execute("SELECT * FROM pending")
    result = cursor.fetchall()
    assert len(result) == 0
    url = "/verifyEmail?token=AAAABBBBCCCCDDDDAAAABBBBCCCCDDDDAAAABBBBCCCCDDDDAAAABBBBCCCCDDDD"
    response = client.get(baseurl+url)
    assert response.status_code == 201
    assert response.json()["success"] == False
    

def testLoginPositive1():
    response = client.post(baseurl+"/login",json={"email":testmail, "password": "Password1"})
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["token"] != None
    
def testValidateAndExtendTokenPositive1():
    response = client.post(baseurl+"/login",json={"email":testmail, "password": "Password1"})
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["token"] != None
    token = response.json()["token"]
    
    response = client.get(baseurl+"/validate",json={"token":token})
    assert response.json()["success"] == True
    
    response = client.get(baseurl+"/requestToken",json={"token":token})
    assert response.json()["success"] == True
    token = response.json()["token"]
    
    response = client.get(baseurl+"/validate",json={"token":token})
    assert response.json()["success"] == True
    
def testValidateTokenNegative1():
    token = ''.join(random.choice(string.ascii_letters) for i in range(24))
    response = client.get(baseurl+"/validate",json={"token":token})
    assert response.status_code == 200
    assert response.json()["success"] == False
    
def testAuthenticateWatchdogPositive1():
    response = client.get(baseurl+"/authenticateWatchdog",json={"wdcode":"xxxxxxxxxxxxxxxx","secret":"[redacted-7]"})
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["token"] != None
    
def testAuthenticateWatchdogNegative1():
    response = client.get(baseurl+"/authenticateWatchdog",json={"wdcode":"xxxxxxxxxxxxxxxx","secret":"[redacted-7]2"})
    assert response.status_code == 200
    assert response.json()["success"] == False
    
def testAuthenticateWatchdogNegative2():
    response = client.get(baseurl+"/authenticateWatchdog",json={"wdcode":"xxxxxxxxxxxxxxxx","secret":"[redacted-7]"})
    assert response.status_code == 200
    assert response.json()["success"] == False
    
def testRequestPublicKey():
    response = client.get(baseurl+"/requestPublicKey")
    assert response.status_code == 200
    assert response.json()["publickey"] != None
    
def testRemoteAuthentication():
    response = client.post(baseurl+"/login",json={"email":testmail, "password": "Password1"})
    assert response.json()["success"]
    k = client.get(baseurl+"/requestPublicKey")
    key = serialization.load_pem_public_key(k.json()["publickey"].encode('utf-8'), backend=default_backend())
    token = response.json()["token"]
    message = token["code"]+str(token["id"])+str(token["time"])+str(token["belongs"])+str(token["perm"])
    signature = base64.b64decode(token["signature"])
    try:
        key.verify(signature, message.encode("utf-8"), padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    except:
        assert False

def testPasswordReset():
    response = client.get(baseurl+"/requestPasswordReset",json={"email": testmail})
    assert response.json()["success"]
    cursor.execute("SELECT * FROM pending WHERE email='"+testmail+"'")
    result = cursor.fetchall()
    assert len(result) == 1
    response = client.post(baseurl+"/resetPassword?token="+result[0][0],json={"password": "MyNewPassword1"})
    assert response.json()["success"]
    response = client.post(baseurl+"/login",json={"email":testmail, "password": "MyNewPassword1"})
    assert response.json()["success"]
    
def testUnregister1():
    response = client.post(baseurl+"/login",json={"email":testmail, "password": "MyNewPassword1"})
    assert response.json()["success"] == True
    token = response.json()["token"]
    assert token != None
    
    response = client.post(baseurl+"/unregister",json={"token":token})
    assert response.status_code == 201
    assert response.json()["success"] == True
    
    response = client.post(baseurl+"/login",json={"email":testmail, "password": "MyNewPassword1"})
    assert response.json()["success"] == False
    
    response = client.get(baseurl+"/authenticateWatchdog",json={"wdcode":"xxxxxxxxxxxxxxxx","secret":"[redacted-7]"})
    assert response.json()["success"] == False
    assert "user" in response.json()["comment"]
    
def testAddCodes():
    response = client.get(baseurl+"/addCodes",json={"pw": "[redacted-1]", "codes": ["ZZZZYYYYXXXX9999"]})
    assert response.json()["success"]
    cursor.execute("SELECT * FROM wdcodes WHERE wdcode='ZZZZYYYYXXXX9999'")
    result = cursor.fetchall()
    assert len(result) == 1
    
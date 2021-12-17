from fastapi import FastAPI, Request, Body, HTTPException
import os
import sys
import json
import bcrypt
import psycopg2
import time
import re
import string
import random
import hashlib
import base64
import secrets
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend
import smtplib
from email.mime.text import MIMEText


from functools import lru_cache, wraps
from time import monotonic_ns


def timed_lru_cache(
    _func=None, *, seconds: int = 600, maxsize: int = 128, typed: bool = False
):
    """Extension of functools lru_cache with a timeout

    Parameters:
    seconds (int): Timeout in seconds to clear the WHOLE cache, default = 10 minutes
    maxsize (int): Maximum Size of the Cache
    typed (bool): Same value of different type will be a different entry

    """

    def wrapper_cache(f):
        f = lru_cache(maxsize=maxsize, typed=typed)(f)
        f.delta = seconds * 10 ** 9
        f.expiration = monotonic_ns() + f.delta

        @wraps(f)
        def wrapped_f(*args, **kwargs):
            if monotonic_ns() >= f.expiration:
                f.cache_clear()
                f.expiration = monotonic_ns() + f.delta
            return f(*args, **kwargs)

        wrapped_f.cache_info = f.cache_info
        wrapped_f.cache_clear = f.cache_clear
        return wrapped_f

    # To allow decorator to be used without arguments
    if _func is None:
        return wrapper_cache
    else:
        return wrapper_cache(_func)



#Database connection
with psycopg2.connect("dbname='auth_db' user='auth_db' host='authdb' [redacted-2]") as conn:

    conn.autocommit = True
    
    app = FastAPI(docs_url=None)

    #Magic values
    auth_token_validness = 129600 #This is 36 hours
    change_token_validness = 600 #This is 10 minutes
    adminAccessPasswordHashed = "[redacted-3]".encode("utf8") #[redacted-1]

    #Regexes
    passwordRegex = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[a-zA-Z0-9!?_]{8,30}$" #At least 8 chars, max 30 chars, one lowerCase, one uppercase and one number. Allowed special chars: !?_
    emailRegex = "^[^@\s]+@[^@\s]+\.[a-zA-Z0-9]+$" 
    wdRegex = r"^[a-zA-Z0-9]{16,16}$"  #16 alphanumerical chars
    wdSecretRegex = r"^[a-zA-Z0-9]{8,16}$" #8-16 alphanumerical chars
    tokenRegex = r"^[a-zA-Z0-9]{64,64}$" #64 alphanumerical chars

    #Pending pattern shape
    pptoken = 0
    pptype = 1  #type 0 = email, 1 = password reset
    pptime = 2
    ppemail = 3
    pphash = 4
    ppwdcode = 5

    #Load the key
    try:
        
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM key")
            res = cursor.fetchall()
        key = res[-1][0].encode("utf-8") #Take the newest key
        privkey = serialization.load_pem_private_key(key, password=None, backend=default_backend())
        pubkey = privkey.public_key()
        print("Using stored keys!")
    except Exception as e:
        raise Exception("No stored keys found! Exiting...")
        
        
    @app.on_event("startup")
    def startup():
        #For whatever fucking reason this does not work as expected
        pass
        
    @app.on_event("shutdown")
    def shutdown():
        pass

    @timed_lru_cache(seconds=600)
    def generateToken(code,id,permissions=-1):
        ct = int(time.time())
        belongs = None
        if "@" in code:
            with conn.cursor() as cursor:
                #User, so we need to fetch the belonging wdcodes
                cursor.execute("SELECT wdcode FROM wdcodes WHERE uid="+str(id))
                result = cursor.fetchall()
                belongs = [i[0] for i in result]
            
        message = code+str(id)+str(ct)+str(belongs)+str(permissions)
        message = message.encode("utf-8")
        signature = privkey.sign(message,padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
        return {"code": code,
                "id": id,
                "perm": permissions,
                "time": ct,
                "belongs": belongs,
                "signature": base64.b64encode(signature)
        }
        

    def sendEmail(to,text):
        #TODO fill in
        password = "[redacted-4]"
        mail = "<html><body><p>Hi!<br>This is an automated email from Bitahoy:<br>"+text+"</p></body></html>"
        msg = MIMEText(mail, "html")
        msg['From'] = "auth-test@testing.bitahoy.com" #Something like auth@bitahoy.com
        msg['To'] = to
        
        
        try:
            server = smtplib.SMTP('mailserver',587)
            server.connect('mailserver',587)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(msg['From'],password)
            server.sendmail(msg['From'], msg['To'], msg.as_string())
            server.quit()
        except Exception as e:
            print("Error during email sending process!")
            print(e)
            return False
        return True

        
    @app.get("/")
    def read_root():
        return {
            "Hello": "World"
        }

    @app.post("/register", status_code=201)
    async def register(request: Request):
        data = json.loads(await request.body())
        try:
            email = data["email"]
            password = data["password"]
            wdcode = data["wdcode"]
            
            #Check validness of input
            #First the email
            if len(email) >= 50:
                return{
                    "success": False,
                    "comment": "Your email should be 50 char or less!"
                }
            if not re.match(emailRegex, email):
                return{
                    "success": False,
                    "comment": "Invalid email!"
                }
            
            #Now password: 
            if(len(password) < 8 or len(password) > 30 or not re.match(passwordRegex,password)):
                return{
                    "success": False,
                    "comment": "Your password is not valid."
                }
            hashed = bcrypt.hashpw(password.encode('utf8'), bcrypt.gensalt()).decode("ascii")
            if len(hashed) != 60:
                raise HTTPException(status_code=500, detail="Password hashing went wrong!")
                
            
            with conn.cursor() as cursor:
                #Check if user exists already:
                cursor.execute("SELECT * FROM users WHERE email=%s",(email,))
                result = cursor.fetchall()
                if len(result) != 0:
                    return{
                        "success": False,
                        "comment": "Email already claimed!"
                    }
                
                #Check if watchdog code matches our pattern
                if len(wdcode) != 16 or not re.match(wdRegex,wdcode): #16 alphanum chars
                    return{
                        "success": False,
                        "comment": "Watchdog code has strange shape"
                    }
                #Fetch the watchdog code's status
                cursor.execute("SELECT * FROM wdcodes WHERE wdcode=%s",(wdcode,))
                result = cursor.fetchall()
                if len(result) != 1:
                    return{
                        "success": False,
                        "comment": "Not a valid Watchdog code!"
                    }
                if result[0][1] != -1:
                    return{
                        "success": False,
                        "comment": "Watchdog code is already claimed!"
                    }
                
                
                #Check if the email is already trying to claim something or if the wd is already being claimed by someone
                msg = ""
                cursor.execute("SELECT * FROM pending")
                result = cursor.fetchall()
                for r in result:
                    if time.time() - r[pptime] < change_token_validness:
                        if r[ppemail] == email or r[ppwdcode] == wdcode:
                            msg = "This email or watchdog code is already in a critical phase."
                    else:
                        cursor.execute("DELETE FROM pending WHERE token=%s",(r[pptoken],))
                        conn.commit()
                if msg != "":
                    return{
                        "success": False,
                        "comment": msg
                    }
                
                token = ''.join(secrets.choice(string.ascii_letters+string.digits) for i in range(64))
                cursor.execute("INSERT INTO pending(token,type,time,email,password,wdcode) VALUES('"+token+"',0,'"+str(int(time.time()))+"',%s,%s,%s)",(email,hashed,wdcode,))    
                conn.commit()
                
                sendEmail(email,"Here is your <a href=\"https://auth.bitahoy.cloud/verifyEmail/?token="+token+"\">link to activate</a>")
                    
                return {
                    "success": True
                }
                
        except KeyError:
            raise HTTPException(status_code=400, detail="Incomplete request form")
            
            
    @app.post("/unregister", status_code=201)
    async def unregister(request: Request):
        #TODO maybe also verify deletion per email?
        #TODO delete also on DC?
        data = json.loads(await request.body())
        try:
            res = await validateToken(request)
            if not res['success']:
                return res
            
            token = data["token"]
            uid = token["id"]
            email = token["code"] #cant be a watchdog
            wdcodes = token["belongs"]
            
            if not "@" in email:
                return{
                    "success": False,
                    "comment": "Endpoint is only accessable for users"
                }

                
            with conn.cursor() as cursor:
                
                #token is valid, check if critical phase
                msg = ""
                cursor.execute("SELECT * FROM pending")
                result = cursor.fetchall()
                for r in result:
                    if time.time() - r[pptime] < change_token_validness:
                        if r[ppemail] == email:
                            msg = "This account is already in a critical phase."
                    else:
                        cursor.execute("DELETE FROM pending WHERE token=%s",(r[pptoken],))
                        conn.commit()
                        
                if msg != "":
                    return{
                        "success": False,
                        "comment": msg
                    }
                
                #Everything legit: Lets delete
                cursor.execute("DELETE FROM users WHERE uid="+str(int(uid))) #No injection since cast to int    
                for wdcode in wdcodes:
                    cursor.execute("UPDATE wdcodes SET uid=-1,secret=%s WHERE wdcode=%s",(None,wdcode,)) #No injection since cast to int    
                conn.commit()
                
                return{
                        "success": True
                }
            
        except KeyError:
            raise HTTPException(status_code=400, detail="Incomplete request form")
            
            

    @app.get("/verifyEmail", status_code=201)
    async def verifyEmail(token: str):
        
        if len(token) != 64 or not re.match(tokenRegex,token): #64 alphanum chars
            return{
                "success": False,
            }
        
        
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM pending WHERE token=%s AND type=0",(token,))
            r = cursor.fetchall()
            if len(r) != 1:
                return{
                    "success": False,
                    "comment": "Invalid token"
                }
            result = r[0]
            if time.time() - result[pptime] > change_token_validness:
                return{
                    "success": False,
                    "comment": "Token expired"
                }
            
            uid = 0
            #Valid email verification!
            while(True): #Generate a uid
                uid = random.randint(0,2147483647) #4 byte int
                cursor.execute("SELECT * FROM users WHERE uid="+str(uid))
                res = cursor.fetchall()
                if len(res) == 0:
                    break
            #Insert user into db and remove the pending token
            cursor.execute("DELETE FROM pending WHERE token=%s",(token,))
            cursor.execute("INSERT INTO users(uid,email,password,permissions) VALUES("+str(uid)+",%s,%s,0)",(result[ppemail],result[pphash],))
            cursor.execute("UPDATE wdcodes SET uid="+str(uid)+" WHERE wdcode=%s",(result[ppwdcode],))
            conn.commit()
            sendEmail(result[ppemail],"SUCCESSFULLY VERIFIED EMAIL!")
            return{
                "success": True #User can now login normally
            }
        
        
    @app.get("/requestPasswordReset")
    async def requestPasswordReset(request: Request):
        try:
            data = json.loads(await request.body())
            email = data["email"]
            
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE email=%s",(email,))
                res = cursor.fetchall()
                
                if len(res) != 1:
                    return{
                        #We return "True" as well do avoid leaking emails in our database!
                        "success": True,
                        "comment": "If the email is valid, we sent a reset link to it!"
                    }
                
                #Check if the email is already trying to claim something
                msg = ""
                
                with conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM pending")
                    result = cursor.fetchall()
                    for r in result:
                        if time.time() - r[pptime] < change_token_validness:
                            if r[ppemail] == email or r[ppwdcode] == wdcode:
                                msg = "This email or watchdog code is already in a critical phase."
                        else:
                            cursor.execute("DELETE FROM pending WHERE token=%s",(r[pptoken],))
                            conn.commit()
                            
                    if msg != "":
                        return{
                            "success": False,
                            "comment": msg
                        }
                    
                    token = ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(64))
                    cursor.execute("INSERT INTO pending(token,type,time,email,password,wdcode) VALUES('"+token+"',1,'"+str(int(time.time()))+"',%s,%s,%s)",(email,"",-1,))    
                    conn.commit()
                    
                    sendEmail(email,"Here is your <a href=\"http://auth.bitahoy.cloud/resetPassword/?token="+token+"\">link to reset the password</a>")
                    
                    return {
                        "success": True,
                        "comment": "If the email is valid, we sent a reset link to it!"
                    }
        except KeyError:
            raise HTTPException(status_code=400, detail="Incomplete request form")
        
        
    @app.post("/resetPassword")
    async def resetPassword(token: str, request: Request):
        if len(token) != 64 or not re.match(tokenRegex,token): #64 alphanum chars
            return{
                "success": False,
            }
            
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM pending WHERE token=%s AND type=1",(token,))
            r = cursor.fetchall()
            if len(r) != 1:
                return{
                    "success": False,
                    "comment": "Invalid reset token"
                }
            result = r[0]
            if time.time() - result[pptime] > change_token_validness:
                return{
                    "success": False,
                    "comment": "Reset token expired"
                }
            
            data = json.loads(await request.body())
            hashed = ""
            try:
                password = data["password"]
                #At least 8 chars, max 30 chars, one lowerCase, one uppercase and one number. Allowed special chars: !?_
                if(len(password) < 8 or len(password) > 30 or not re.match(passwordRegex,password)):
                    return{
                        "success": False,
                        "comment": "Your new password is not valid."
                    }
                hashed = bcrypt.hashpw(password.encode('utf8'), bcrypt.gensalt()).decode("ascii")
                if len(hashed) != 60 or hashed == "":
                    raise HTTPException(status_code=500, detail="Password hashing went wrong!")
                    
                
                #Insert user into db and remove the pending token
                cursor.execute("DELETE FROM pending WHERE token=%s",(token,))
                cursor.execute("UPDATE users SET password=%s WHERE email=%s",(hashed,result[ppemail],))
                conn.commit()
                sendEmail(result[ppemail],"PASSWORD RESET SUCCESS!")
                return{
                    "success": True #User can now login normally
                }
                
            except KeyError:
                raise HTTPException(status_code=400, detail="Incomplete request form")
        
        
        
            
    @app.post("/login")
    async def login(request: Request):
        data = json.loads(await request.body())
        try:
            email = data["email"]
            password = data["password"]

            
            with conn.cursor() as cursor:
                
                #Fetch user with this email
                cursor.execute("SELECT * FROM users WHERE email=%s",(email,))
                result = cursor.fetchall()
                if len(result) != 1:
                    return{
                        "success": False,
                        "comment": "Email does not exist!"
                    }
                
                #Get the password of the user and compare it to the given password
                hashed = result[0][2].encode("ascii")
                t = bcrypt.hashpw(password.encode("utf8"), hashed)
                if len(hashed) != len(t):
                    return{
                        "success": False,
                        "comment": "Incorrect password! "+str(hashed)
                    }
                    
                hashOK = True
                for i in range(len(hashed)):
                    if hashed[i] != t[i]:
                        hashOK = False
                        
                if not hashOK:
                    return{
                        "success": False,
                        "comment": "Incorrect password!"
                    }
                
                return{
                    "success": True,
                    "token": generateToken(email,result[0][0], result[0][3])
                }
        except KeyError:
            raise HTTPException(status_code=400, detail="Incomplete request form")

        
        
    @app.get("/authenticateWatchdog")
    async def authenticateWatchdog(request: Request):
        #Watchdog sends it's code to the server in order to get a token
        #Token is given out, if there is a user that owns the watchdog and the secret is correct
        data = json.loads(await request.body())
        try:
            wdcode = data["wdcode"]
            secret = data["secret"]
            
            #Check if code matches pattern
            if len(wdcode) != 16 or not re.match(wdRegex,wdcode): #16 alphanum chars
                return{
                    "success": False,
                    "comment": "Watchdog code has strange shape"
                }
                
            if not re.match(wdSecretRegex,secret):
                return{
                    "success": False,
                    "comment": "Secret has strange shape"
                }

            
            with conn.cursor() as cursor:
                
                #Look if a user claimed this code and secret
                cursor.execute("SELECT * FROM wdcodes WHERE wdcode=%s",(wdcode,))
                result = cursor.fetchall()
                
                #0 is code, 1 is uid, 2 is secret
                if len(result) != 1:
                    return{
                        "success": False,
                        "comment": "Not a valid code!"
                    }
                    
                if result[0][1] == -1: #uid -1 indicates it is not claimed!
                    return{
                        "success": False,
                        "comment": "No user could be identified"
                    }
                        
                        
                if len(result[0]) < 3 or result[0][2]==None:
                    #No secret in there yet!
                    cursor.execute("UPDATE wdcodes SET secret=%s WHERE wdcode=%s",(secret,wdcode,))
                    return{
                        "success": True,
                        "token": generateToken(wdcode,result[0][1])
                    }
                else:
                    if secret == result[0][2]:
                        return{
                            "success": True,
                            "token": generateToken(wdcode,result[0][1])
                        }
                    else:
                        return{
                            "success": False,
                            "comment": "Invalid secret"
                        }
            
                
                    
                
            
        except KeyError:
            raise HTTPException(status_code=400, detail="Incomplete request form")
        except TypeError:
            raise HTTPException(status_code=400, detail="Request contains unexpected types")
        
        
            
    @app.get("/validate")
    async def validateToken(request: Request):
        #Can be called by other server modules to validate a token
        #Should not be used by other modules
        data = json.loads(await request.body())
        try:
            token = data["token"]
            try:
                message = token["code"]+str(token["id"])+str(token["time"])+str(token["belongs"])+str(token["perm"])
                signature = base64.b64decode(token["signature"])
                pubkey.verify(signature, message.encode("utf-8"), padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
                #Token matches
                t = float(token["time"])
                if time.time()-t < auth_token_validness:
                    return{
                        "success": True
                    }
                return{
                    "success": False,
                    "comment": "Token expired"
                }
            except Exception as e:
                return {
                    "success": False
                }
        except KeyError:
            raise HTTPException(status_code=400, detail="Incomplete request form")
        except TypeError:
            raise HTTPException(status_code=400, detail="Request contains unexpected types")
            
            
    @app.get("/requestToken")
    async def requestToken(request: Request):
        #Request a fresh token with a old one
        data = json.loads(await request.body())
        try:
            token = data["token"]
            
            try:
                message = token["code"]+str(token["id"])+str(token["time"])+str(token["belongs"])+str(token["perm"])
                signature = base64.b64decode(token["signature"])
                pubkey.verify(signature, message.encode("utf-8"), padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
                #Token matches message
                code = token["code"]
                t = float(token["time"])
                if time.time()-t < auth_token_validness:
                    #Still valid:
                    return{
                        "success": True,
                        "token": generateToken(code,token["id"])
                    }
                else:
                    return{
                        "success": False,
                        "comment": "Expired"
                    }
            except Exception as e:
                return{
                    "success": False
                }
        except KeyError:
            raise HTTPException(status_code=400, detail="Incomplete request form")
        except TypeError:
            raise HTTPException(status_code=400, detail="Request contains unexpected types")
            
    @timed_lru_cache(seconds=600)
    def getPublicKey():
        return pubkey.public_bytes(encoding=serialization.Encoding.PEM,format=serialization.PublicFormat.SubjectPublicKeyInfo)
            
    @app.get("/requestPublicKey")
    async def requestPublicKey():
        return{
            "publickey": getPublicKey()
        }
        
        
    @app.get("/addCodes")
    async def addCodes(request: Request):
        
        data = json.loads(await request.body())
        
        try:
            pw = data["pw"]
            t = bcrypt.hashpw(pw.encode("utf8"), adminAccessPasswordHashed)
            if len(adminAccessPasswordHashed) != len(t):
                return {
                    "success": False,
                    "comment": "Incorrect password"
                }
            
            hashOK = True
            for i in range(len(t)):
                if t[i] != adminAccessPasswordHashed[i]:
                    hashOK = False
            
            if not hashOK:
                return {
                    "success": False,
                    "comment": "Incorrect password"
                }
            
            codes = data["codes"]
            invalid = []

            
            with conn.cursor() as cursor:
                
                try:
                    for c in codes:
                        if len(c) != 16 or not re.match(wdRegex,c): #16 alphanum chars
                            invalid.append(c)
                            continue
                        cursor.execute("SELECT * FROM wdcodes WHERE wdcode=%s",(c,))
                        result = cursor.fetchall()
                        if len(result) != 0:
                            invalid.append(c)
                            continue
                        
                        cursor.execute("INSERT INTO wdcodes(wdcode,uid) VALUES(%s,-1)",(c,))
                        
                    conn.commit()
                except Exception as e:
                    return{
                        "success": False
                    }
                    
                return {
                    "success": True,
                    "comment": "Invalid codes: "+str(invalid)
                }
        except KeyError:
            raise HTTPException(status_code=400, detail="Incomplete request form")




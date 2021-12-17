import os

import requests
import time
import base64
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa




class AuthenticatedClient:

    def __init__(self, token):
        self.code = token["code"] #email or wdcode
        self.uid = token["id"] #uid
        self.belongs = token["belongs"]
        self.isUser = "@" in self.code
        self.permissions = token["perm"]

class Expired(Exception):
    pass

class VerificationFailed(Exception):
    pass

class InvalidToken(Exception):
    pass

class Auth:

    def __init__(self, auth_url:str=None):
        if auth_url:
            self.__auth_url = auth_url
        else:
            try:
                self.__auth_url = os.getenv("AUTH_BACKEND_SERVICE_PROTO", "http://")+os.environ["AUTH_BACKEND_SERVICE_HOST"]+":"+os.environ["AUTH_BACKEND_SERVICE_PORT"]
            except KeyError:
                self.__auth_url = "https://auth.bitahoy.cloud"
        self.__publickey = (None,0)
        self.__publickey_TTL = 3600
        self.__auth_token_validness = 129600
        self.debug = False
        pass

    def __updateKey(self, force=False):
        if force or self.__publickey[1] + self.__publickey_TTL < time.time() or not self.__publickey[0]:
            res = requests.get(self.__auth_url+"/requestPublicKey").json()
            self.__publickey = (serialization.load_pem_public_key(res["publickey"].encode('utf-8'), backend=default_backend()), time.time())
            if self.debug:
                print("[Auth] updated publickey")
            return True
        else:
            if self.debug:
                print("[Auth] publickey not updated")
            return False

    def verify(self, token:list) -> AuthenticatedClient:
        """
        Validates and parses an user-provided token
        """
        try:
            message = token["code"]+str(token["id"])+str(token["time"])+str(token["belongs"])+str(token["perm"])
            signature = base64.b64decode(token["signature"])
            t = token["time"]
        except Exception as e:
            raise InvalidToken(str(e))
        if time.time() - float(t) > self.__auth_token_validness:
            raise Expired("token expired")
        self.__updateKey()
        try:
            self.__publickey[0].verify(signature, message.encode("UTF-8"), padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
        except Exception as err:
            x = VerificationFailed(str(err))
            x.err = err
            raise x
        return AuthenticatedClient(token)
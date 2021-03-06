import socket, json, threading, binascii, random, string, codecs
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from encrypt_decrypt import rsa_encrypt, rsa_decrypt
from sha_hash import sha_hash
from symmetric_enc_dec import symmetric_encrypt, symmetric_decrypt
from Crypto.Signature import PKCS1_v1_5
from Crypto.Hash import SHA256
from base64 import b64decode, b64encode
from datetime import datetime, timedelta

class Client:
    HOST = "127.0.0.1"
    state = 0

    def __init__(self, port_CA, port_AS, port_VS):
        self.VOTE = 0
        self.PU_CA = RSA.importKey(open("PU_CA.key", "rb").read())
        self.port_CA = port_CA
        self.port_AS = port_AS
        self.port_VS = port_VS
        self.NAME = ""
        self.ID = ""

    def connect(self):
        while True:
            if (self.state == 0):
                print("Please enter your Name:")
                self.NAME = input()
                print("Please enter your national ID:")
                self.ID = input()
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((self.HOST, self.port_CA))
                # encrypt hash of message
                M = self.ID + self.NAME
                K_C = self.ID + 'S3'
                signature = symmetric_encrypt(K_C, sha_hash(bytes(M, encoding="utf-8")))
                # timestamp
                TS1 = datetime.now()
                LT1 = timedelta(seconds=5)
                # final message
                msg = {"ID": self.ID, "NAME": self.NAME, "TS1": str(TS1), "LT1": str(LT1), "signature": signature.decode("utf-8")}
                # encrypt key
                key = ''.join(random.choices(string.ascii_uppercase + string.digits, k = 5))
                PU_CA = RSA.importKey(open('PU_CA.key', "rb").read())
                key_enc = rsa_encrypt(PU_CA, bytes(key, encoding="utf-8"))
                # encrypt message
                msg_enc = symmetric_encrypt(key, json.dumps(msg))
                data = json.dumps({"message": msg_enc.decode("utf-8"), "key": key_enc.hex()})
                # send message
                s.sendall(bytes(data, encoding="utf-8"))
                # next state
                self.state = 1
            if (self.state == 1):
                # receive
                data = s.recv(4096)
                # decrypt message
                K_C = self.ID + 'S3'
                data = json.loads(symmetric_decrypt(K_C, data))
                # extract data
                if data['validity'] == 'NO': # invalid reply
                    print(data['error'])
                    self.state = 0 # send last message again
                    s.close()
                    continue
                self.PU_AS = data["PU_AS"]
                self.PR_C = data["PR_C"]
                self.PU_C = data["PU_C"]
                self.cert_encrypted = data["cert_encrypted"]
                ts = data["TS2"]
                lt = data["LT2"]
                signature = data["signature"]
                # check timestamp
                t1 = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S.%f')
                t2 = datetime.now()
                l = datetime.strptime(lt, '%H:%M:%S')
                delta = timedelta(hours=l.hour, minutes=l.minute, seconds=l.second)
                status_time = False
                if t2-t1 <= delta:
                    status_time = True
                print(str(self.state) + ' Timestamp Status:' + str(status_time))
                # check hash
                status_hash = False
                if sha_hash(bytes(self.PU_AS + self.PR_C + self.cert_encrypted, encoding="utf-8")) == signature:
                    status_hash = True
                print(str(self.state) + ' Hash Status:' + str(status_hash))
                if status_hash and status_time:
                    # next state
                    self.state = 2
                else:
                    # previous state
                    self.state = 0
                s.close()
            if (self.state == 2):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((self.HOST, self.port_AS))
                # sign hash of message
                M = self.ID + self.PU_C + self.cert_encrypted
                signature = self.sign_data(RSA.importKey(self.PR_C) , bytes(sha_hash(bytes(M, encoding="utf-8")),encoding="utf-8"))
                signature = signature.decode('utf-8')
                # timestamp
                TS3 = datetime.now()
                LT3 = timedelta(seconds=5)
                # final message
                msg = {"ID": self.ID,'PU_C': self.PU_C, "cert_encrypted": self.cert_encrypted, "TS3": str(TS3), "LT3": str(LT3), 'signature': signature}
                # encrypt key
                key = ''.join(random.choices(string.ascii_uppercase + string.digits, k = 5))
                key_enc = rsa_encrypt(RSA.importKey(self.PU_AS), bytes(key, encoding="utf-8"))
                # encrypt message
                msg_enc = symmetric_encrypt(key, json.dumps(msg))
                data = json.dumps({"message": msg_enc.decode("utf-8"), "key": key_enc.hex()})
                # send message
                s.sendall(bytes(data, encoding="utf-8"))
                # next state
                self.state = 3
            if (self.state == 3):
                # receive
                data = s.recv(4096)
                data = json.loads(data)
                msg_enc = data["message"]
                key_enc = bytes.fromhex(data["key"])
                # decrypt key
                key = rsa_decrypt(RSA.importKey(self.PR_C), key_enc)
                # decrypt message
                message = symmetric_decrypt(key.decode("utf-8"), msg_enc)
                data = json.loads(message)
                # check validity
                if data['validity'] == 'NO': # invalid reply
                    print(data['error'])
                    if data['error'] == 'server: NOT Allowed to Vote':
                        self.state = 0 # back to beginning
                    else:
                        self.state = 2 # send last message again
                    s.close()
                    continue
                # extract data
                self.ticket_encrypted = data['ticket_encrypted']
                self.SK_voter = data['SK_voter']
                self.PU_VS = data["PU_VS"]
                ts = data["TS4"]
                lt = data["LT4"]
                signature = data["signature"]
                # check timestamp
                t1 = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S.%f')
                t2 = datetime.now()
                l = datetime.strptime(lt, '%H:%M:%S')
                delta = timedelta(hours=l.hour, minutes=l.minute, seconds=l.second)
                status_time = False
                if t2-t1 <= delta:
                    status_time = True
                print(str(self.state) + ' Timestamp Status:' + str(status_time))
                # check hash
                status_hash = False
                M = self.ticket_encrypted + self.SK_voter + self.PU_VS
                if self.verify_sign(RSA.importKey(self.PU_AS), signature, bytes(sha_hash(bytes(M, encoding="utf-8")), encoding='utf-8')):
                    status_hash = True
                print(str(self.state) + ' Hash Status:' + str(status_hash))
                if status_hash and status_time:
                    # next state
                    self.state = 4
                else:
                    # previous state
                    self.state = 2
                s.close()
            if (self.state == 4):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((self.HOST, self.port_VS))
                # choose vote
                self.choose_vote()
                if self.VOTE == "cancel":
                    self.state = 6
                    s.close()
                    continue
                # encrypt hash of vote
                vote_encrypted = symmetric_encrypt(self.SK_voter, sha_hash(bytes(str(self.VOTE), encoding="utf-8")))
                # build message
                M = str(self.VOTE) + vote_encrypted.hex() + self.ticket_encrypted
                # hash whole message
                signature = sha_hash(bytes(M, encoding="utf-8"))
                # final message
                msg = {'vote': str(self.VOTE),'vote_encrypted': vote_encrypted.decode('utf-8'), 'ticket_encrypted': self.ticket_encrypted, 'signature': signature}
                # encrypt key
                key = ''.join(random.choices(string.ascii_uppercase + string.digits, k = 5))
                key_enc = rsa_encrypt(RSA.importKey(self.PU_VS), bytes(key, encoding="utf-8"))
                # encrypt message
                msg_enc = symmetric_encrypt(key, json.dumps(msg))
                data = json.dumps({"message": msg_enc.decode("utf-8"), "key": key_enc.hex()})
                # send message
                s.sendall(bytes(data, encoding="utf-8"))
                # next state
                self.state = 5
            if (self.state == 5):
                # receive
                data = s.recv(4096)
                data = json.loads(data)
                msg_enc = data['message']
                key_enc = bytes.fromhex(data['key'])
                # decrypt key
                key = rsa_decrypt(RSA.importKey(self.PR_C), key_enc)
                # decrypt message
                message = symmetric_decrypt(key.decode('utf-8'), msg_enc)
                data = json.loads(message)
                # check validity
                if data['validity'] == 'NO': # invalid reply
                    print(data['error'])
                    if data['error'] == 'server: Invalid Vote Ticket':
                        self.state = 0 # get back to beginning
                    else:
                        self.state = 4 # send last message again
                    s.close()
                    continue
                # extract data
                status_vote = data['status']
                print(str(self.state) + ' Vote Status:' + status_vote)
                signature = data['signature']
                # check hash
                status_hash = False
                if self.verify_sign(RSA.importKey(self.PU_VS), signature, bytes(sha_hash(bytes(status_vote, encoding="utf-8")), encoding='utf-8')):
                    status_hash = True
                print(str(self.state) + ' Hash Status:' + str(status_hash))
                if status_vote == 'SUCCESSFUL' and status_hash:
                    # next state
                    self.state = 6
                    print("Voting successfull!")
                else:
                    # previous state
                    self.state = 6
                    print("You have voted before")
                s.close()
                if self.state == 6:
                    break



    def choose_vote(self):
        while True:
            print('Choose your vote option please: 1 2 3 cancel')
            v1 = int(input())
            print('Confirm your vote option please: 1 2 3 cancel')
            v2 = int(input())
            if v1 == v2:
                break
            else:
                print('Error: different votes')
        self.VOTE = v1
        return


    def verify_sign(self, PU, signature, data):
        signer = PKCS1_v1_5.new(PU)
        digest = SHA256.new()
        digest.update(data)
        if signer.verify(digest, b64decode(signature)):
            return True
        else:
            return False


    def sign_data(self, PR, data):
        signer = PKCS1_v1_5.new(PR)
        digest = SHA256.new()
        digest.update(data)
        sign = signer.sign(digest)
        return b64encode(sign)


c = Client(1980, 1981, 1982)
c.connect()
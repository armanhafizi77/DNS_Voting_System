import socket, json, random, string
from Crypto.PublicKey import RSA
from encrypt_decrypt import rsa_decrypt, rsa_encrypt
from symmetric_enc_dec import symmetric_decrypt, symmetric_encrypt
from sha_hash import sha_hash
from Crypto.Signature import PKCS1_v1_5
from Crypto.Hash import SHA256
from base64 import b64decode, b64encode
from datetime import datetime, timedelta

def generate_keys(PR_NAME, PU_NAME):
    key = RSA.generate(1024)
    pub_key = key.publickey()
    private_key = key.exportKey()
    open(PR_NAME, 'wb').write(private_key)
    public_key = pub_key.exportKey()
    open(PU_NAME, 'wb').write(public_key)

class CA:
    HOST = "127.0.0.1"

    def __init__(self, port):
        self.PORT = port
        f = open('CA_DB/info.txt', 'wt')
        # ID Name Key
        f.write('0000000001,Arman,False\n')
        f.write('0000000002,Amir Hossein,False\n')
        f.write('0000000003,Sepideh,False\n')
        f.write('0000000004,Kiana,False\n')
        f.write('0000000005,Taha,False\n')
        f.close()
        log = open('CA_DB/log.txt', 'wt')
        log.close()

    def initiate(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.HOST, self.PORT))
            s.listen()
            while True:
                conn, addr = s.accept()
                with conn:
                    print('Connected: ', addr)
                    data = conn.recv(4096)
                    data = json.loads(data)
                    msg_enc = data["message"]
                    key_enc = bytes.fromhex(data["key"])
                    # decrypt key
                    PR_CA = RSA.importKey(open('PR_CA.key', "rb").read())
                    key = rsa_decrypt(PR_CA, key_enc)
                    # decrypt message
                    message = symmetric_decrypt(key.decode("utf-8"), msg_enc)
                    # logging received data
                    log = open('CA_DB/log.txt', 'a')
                    log.write('received from {}: '.format(addr))
                    log.write(message)
                    log.write('\n')
                    log.close()
                    # extract data
                    data = json.loads(message)
                    enc_signature = data["signature"]
                    ID_C = data["ID"]
                    name = data["NAME"]
                    # Handle bad ID format(send error if ID is not 10 digits)
                    if (not len(ID_C) == 10 or not ID_C.isnumeric()):
                        message = {'validity':'NO', 'error': 'server: Incorrect ID format'}
                        K_C = ID_C + 'S3'
                        # logging received data
                        log = open('CA_DB/log.txt', 'a')
                        log.write('sent to {}: '.format(addr))
                        log.write(message)
                        log.write('\n')
                        log.close()
                        data = symmetric_encrypt(K_C, json.dumps(message))
                        conn.sendall(data)
                        continue
                    ts = data["TS1"]
                    lt = data["LT1"]
                    # decrypt hash
                    K_C = ID_C + 'S3'
                    signature = symmetric_decrypt(K_C, enc_signature)
                    # check timestamp
                    t1 = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S.%f')
                    t2 = datetime.now()
                    l = datetime.strptime(lt, '%H:%M:%S')
                    delta = timedelta(hours=l.hour, minutes=l.minute, seconds=l.second)
                    status_time = False
                    if t2-t1 <= delta:
                        status_time = True
                    print('Timestamp Status:'+str(status_time))
                    # check hash
                    status_hash = False
                    if sha_hash(bytes(ID_C + name, encoding="utf-8")) == signature:
                        status_hash = True
                    print('Hash Status:'+str(status_hash))
                    if status_hash == False:
                        # final message
                        message = {'validity':'NO', 'error': 'server: Wrong Hash'}
                    elif status_time == False:
                        # final message
                        message = {'validity':'NO', 'error': 'server: Timstamp Expired'}
                    else: # every thing is fine
                        # read database
                        f = open('CA_DB/info.txt', 'r')
                        line = f.readlines()
                        f.close()
                        flag_exists = False
                        for i in range(len(line)):
                            # find client
                            if line[i].split(',')[0] == ID_C and line[i].split(',')[1] == name:
                                flag_exists = True
                                if line[i].split(',')[2] == 'False\n':
                                    # write in database
                                    f = open('CA_DB/info.txt', 'w')
                                    line[i] = ID_C + ',' + name + ',True\n'
                                    line_new = ''.join(line)
                                    f.write(line_new)
                                    f.close()
                                    # generate PU PR for that person
                                    PR_NAME = 'CA_DB/PR_' + ID_C + '.key'
                                    PU_NAME = 'CA_DB/PU_' + ID_C + '.key'
                                    generate_keys(PR_NAME, PU_NAME)
                                # read keys
                                PR_C = open('CA_DB/PR_'+ID_C+'.key', "r", encoding="utf-8").read()
                                PU_C = open('CA_DB/PU_'+ID_C+'.key', "r", encoding="utf-8").read()
                                PU_AS = open("PU_AS.key", "r", encoding="utf-8").read()
                                # certification
                                certification = {"ID": ID_C, "PU_C": PU_C}
                                certification = bytes(json.dumps(certification), encoding = 'utf-8')
                                # sign certification
                                PR_CA = RSA.importKey(open('PR_CA.key', "rb").read())
                                cert_encrypted = self.sign_data(PR_CA, certification)
                                cert_encrypted =  cert_encrypted.decode('utf-8')
                                # hash message with signature
                                M = PU_AS + PR_C + cert_encrypted # raw message
                                signature = sha_hash(bytes(M, encoding="utf-8"))
                                # timestamp
                                TS2 = datetime.now()
                                LT2 = timedelta(seconds=5)
                                # final message
                                message = {'validity':'YES', "PU_AS": PU_AS, "PR_C": PR_C, 'PU_C': PU_C, "cert_encrypted": cert_encrypted, "TS2": str(TS2), "LT2": str(LT2), "signature": signature}
                                break
                        if (not flag_exists):
                            message = {'validity':'NO', 'error': 'server: Name or ID does not exist'} 
                    # logging sent data
                    log = open('CA_DB/log.txt', 'a')
                    log.write('sent to {}: '.format(addr))
                    log.write(json.dumps(message))
                    log.write('\n')
                    log.close()
                    # encrypt message by K_C
                    data = symmetric_encrypt(K_C, json.dumps(message))
                    # send message
                    conn.sendall(data)

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
        
ca_ = CA(1980)
ca_.initiate()

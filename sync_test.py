import socket
import json
import subprocess
import time

POLL_INTERVAL_S = 0.1
SOCKET_ADDRESS = '/var/run/dsf/dcs.sock'
MM_BUFFER_SIZE = 65536


def sendblob(sock, blob):
    sock.sendall(json.dumps(blob).encode())

def getblob(sock, size):
    return json.loads(sock.recv(MM_BUFFER_SIZE).decode())

def dict_or_list_iter(obj):
    """ Returns a key/value iterator for a dict or a list """
    if isinstance(obj, list):
        return enumerate(obj)
    elif isinstance(obj, dict):
        return obj.items()
    else:
        return None

def index_exists(obj, idx):
    if isinstance(obj, dict):
        return idx in obj
    elif isinstance(obj, list):
        return idx < len(obj)
    else:
        return False

def recursive_update(target, patch):
    if patch == {}:
        return target
    
    it = dict_or_list_iter(patch)
    if not it:
        return patch
    
    for k, v in it:
        if index_exists(target, k):         
            target[k] = recursive_update(target[k], v)
        else:
            target[k] = v
           
    return target
    

def partial_update(state, template, patch):
    it = dict_or_list_iter(patch)
    if not it:
        return

    for k,v in it:
        if not index_exists(template, k):
            continue # Don't care about this whole sub-tree.
        t = template[k]
        if isinstance(t, str):
            # Sometimes we might want a whole subtree...
            if t in state:
                state[t] = recursive_update(state[t], v)
            else:
                state[t] = v
        else:
            partial_update(state, t, v)

            
template = {'heat' : {'heaters': {0 : {'current' : 'bed_temp'}}}, 'state' : {'uptime' : 'uptime', 'status' : 'status'}}

state = dict()

subscribe_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
subscribe_socket.connect(SOCKET_ADDRESS)
subscribe_socket.setblocking(True)


sendblob(subscribe_socket, {"mode":"subscribe","version": 8, "subscriptionMode": "Patch"})


partial_update(state, template, getblob(subscribe_socket, MM_BUFFER_SIZE))

while True:

    sendblob(subscribe_socket, {"command" : "Acknowledge"})
    blob = getblob(subscribe_socket, MM_BUFFER_SIZE)

    partial_update(state, template, blob)
    print(state)

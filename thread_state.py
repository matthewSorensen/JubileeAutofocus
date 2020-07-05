import threading
import socket
import time
import json
import copy


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

def keys_in_template(template):
    """ Traverse a template and return all keys that will eventually be used. """
    if isinstance(template, str):
        yield template
    else:
        it = dict_or_list_iter(template)
        if it:
            for k,v in it:
                yield from keys_in_template(v)



def sendblob(socket,obj):
    socket.sendall(json.dumps(obj).encode())

    
def getblob(socket, buffer_size = 65536):
    data = socket.recv(buffer_size).decode()
    return json.loads(data)


def worker_loop(socket_addr, state, template, idle_event, busy_event, terminate_event, state_lock):

    # Figure out which bits of state we're going to track
    if template is not None:
        for k in keys_in_template(template):
            state[k] = None
    # Connect to a socket for getting state updates
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socket_addr)
    sock.setblocking(True)

    sendblob(sock,{"mode":"subscribe","version": 8, "subscriptionMode": "Patch"})
    # Two messages to ignore, and then the full state
    getblob(sock) 
    getblob(sock)

    # Perform the first state update
    message = getblob(sock)
    with state_lock:
        if template:  
            partial_update(state, template, message)
        else:
            recursive_update(state, message)
    
    if message['state']['status'] == 'idle':
        idle_event.set()
        busy_event.clear()
    else:
        idle_event.clear()
        busy_event.set()
        

        
    while not terminate_event.is_set():
        # Let the socket know we got that, and get a new update
        sendblob(sock, {"command" : "Acknowledge"})
        message = getblob(sock)
        with state_lock:
            # Apply the update
            if template:
                partial_update(state, template, message)
            else:
                recursive_update(state, message)


        if 'state' in message:
            st = message['state']
            if 'status' in st:
                new_status = st['status']
                if new_status != 'idle':
                    busy_event.set()
                    idle_event.clear()
                else:
                    busy_event.clear()
                    idle_event.set()

    # Once we get the signal to terminate, close the socket and die
    sock.close()



class MachineConnection:

    def __init__(self, socket):

        self.idle_event = threading.Event()
        self.busy_event = threading.Event()
        self.terminate_event = threading.Event()
        self.state_lock = threading.Lock()
        self.worker = None
        self.state = {}
        self.template = {}
        self.socket_address = socket

    def __enter__(self):
        # Start the thread that polls state
        self.worker = threading.Thread(target = worker_loop,
                                       args = (self.socket_address, self.state,
                                               self.template, self.idle_event, self.busy_event,
                                               self.terminate_event, self.state_lock))
        self.worker.start()
        # Open a socket for sending gcode from this thread as well
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_address)
        self.sock.setblocking(True)

        sendblob(self.sock, {"mode":"command","version": 8})
        getblob(self.sock) # Ignore a welcome message - should check it...
        
        return self

    def gcode(self, codes):
        
        if isinstance(codes, str):
            codes = [codes]

        print(codes)
        for g in codes:
            sendblob(self.sock, {"code" : g, "channel" : 0, "command" : "SimpleCode"})
            getblob(self.sock) # Again, should check this...

        if self.busy_event.wait(1):
            self.idle_event.wait()
        # Presumably, enough time haspassed that the machine has had a chance to update its status.
        # This may not be correct.
    
    def current_state(self):
        with self.state_lock:
            return copy.deepcopy(self.state)
    
    def __exit__(self, type, value, tb):
        # Signal the worker thread to terminate, and join it
        self.terminate_event.set()
        self.worker.join()
        # Clean up our command socket as well
        self.sock.close()

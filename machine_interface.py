import threading
import socket
import time
import json
import copy
import numpy as np

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


def ignoreblob(socket, buffer_size = 65536):
    socket.recv(buffer_size).decode()


    
internal_template = {'move': {'axes' : {0 : {'userPosition': 'x'},
                                        1 : {'userPosition': 'y'},
                                        2 : {'userPosition': 'z'},
                                        3 : {'userPosition': 'u'}}}}


def worker_loop(socket_addr, state, internal_state, template, idle_event, busy_event, terminate_event, ready_event, state_lock):

    # Figure out which bits of state we're going to track
    if template is not None:
        for k in keys_in_template(template):
            state[k] = {}
    # Connect to a socket for getting state updates
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socket_addr)
    sock.setblocking(True)

    sendblob(sock,{"mode":"subscribe","version": 8, "subscriptionMode": "Patch"})
    # Two messages to ignore, and then the full state
    ignoreblob(sock) 
    ignoreblob(sock)

    # Perform the first state update
    message = getblob(sock)
    with state_lock:
        if template:  
            partial_update(state, template, message)
        else:
            recursive_update(state, message)
        partial_update(internal_state, internal_template, message)
    
    if message['state']['status'] == 'idle':
        idle_event.set()
        busy_event.clear()
    else:
        idle_event.clear()
        busy_event.set()
        

    ready_event.set()
        
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

            partial_update(internal_state, internal_template, message)

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

    def __init__(self, socket, template = None):

        self.idle_event = threading.Event()
        self.busy_event = threading.Event()
        self.terminate_event = threading.Event()
        self.ready_event = threading.Event()
        self.state_lock = threading.Lock()
        self.worker = None
        self.state = {}
        self.internal_state = {}
        if template is None:
            self.template = {}
        else:
            self.template = template
        self.socket_address = socket

    def __enter__(self):
        # Start the thread that polls state
        self.worker = threading.Thread(target = worker_loop,
                                       args = (self.socket_address, self.state, self.internal_state,
                                               self.template, self.idle_event, self.busy_event,
                                               self.terminate_event, self.ready_event, self.state_lock))
        self.worker.start()
        self.ready_event.wait()
        # Open a socket for sending gcode from this thread as well
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_address)
        self.sock.setblocking(True)

        sendblob(self.sock, {"mode":"command","version": 8})
        ignoreblob(self.sock) # Ignore a welcome message - should check it...
        
        return self

    def gcode(self, codes, block = True):
        
        if isinstance(codes, str):
            codes = [codes]

        for g in codes:
            sendblob(self.sock, {"code" : g, "channel" : 0, "command" : "SimpleCode"})
            getblob(self.sock) # Again, should check this...

        if block and self.busy_event.wait(1):
            self.idle_event.wait()

    def move(self,*args,**kwargs):

        n, moves = len(args), {}
        sequence = ['X','Y','Z','E']
        if n == 1:
            args = args[0]
            n = len(args)
        if n > len(sequence):
            return
        for i,v in enumerate(args):
            moves[sequence[i]] = v
        for s in sequence:
            if s in kwargs:
                moves[s] = kwargs[s]
        if 'f' in kwargs:
            moves['F'] = kwargs['f']

        gcode = 'G0 ' + ' '.join(axis + str(value) for axis, value in moves.items())
        
        if 'block' in kwargs:
            self.gcode(gcode, block = kwargs['block'])
        else:
            self.gcode(gcode)


    def xyzu(self):
        vect = np.empty(4)
        with self.state_lock:
            vect[0] = self.internal_state['x']
            vect[1] = self.internal_state['y']
            vect[2] = self.internal_state['z']
            vect[3] = self.internal_state['u']
        return vect

    def is_busy(self):
        return self.busy_event.is_set()
        
    def current_state(self):
        with self.state_lock:
            return copy.deepcopy(self.state)
    
    def __exit__(self, type, value, tb):
        # Signal the worker thread to terminate, and join it
        self.terminate_event.set()
        self.worker.join()
        # Clean up our command socket as well
        self.sock.close()

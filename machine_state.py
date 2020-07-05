import socket
import json
import subprocess
import time
import asyncio

SOCKET_ADDRESS = '/var/run/dsf/dcs.sock'
MM_BUFFER_SIZE = 65536


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

def initialize_partial_state(state, template):
    """ Build an empty state object with slots for all of the values we're tracking,
    and adjust the template to make sure to track the machine status. """

    for k in keys_in_template(template):
        state[k] = None
    idle_name = 'idle'
    while idle_name in state:
        idle_name += "_"
    # Then make sure the idle status is in the template
    if 'state' in template:
        if 'status' in template['state']:
            # It's already in the state, so use the original name
            idle_name = template['state']['status']
        else:
            state[idle_name] = None
            template['state']['status'] = idle_name
    else:
        state[idle_name] = None
        template['state'] = {'status' : idle_name}
        
    return template, idle_name
 

async def sendblob(writer,obj):
    writer.write(json.dumps(obj).encode())
    await writer.drain()

async def getblob(reader):
    data = await reader.read(MM_BUFFER_SIZE)
    return json.loads(data.decode())
                  
    
async def track_machine_state(state, template = None, idle_event = None, die_event = None):
    
    status, idle_key  = None, None
    if template is not None:
        template, idle_key = initialize_partial_state(state, template)
    
    reader, writer = await asyncio.open_unix_connection(SOCKET_ADDRESS)
    await sendblob(writer, {"mode":"subscribe","version": 8, "subscriptionMode": "Patch"})

    
    message = await getblob(reader)

    if template:  
        partial_update(state, template, message)
        status = state[idle_key]
    else:
        recursive_update(state, message)
        status = state['state']['status']

    if idle_event:
        if status == 'idle':
            idle_event.set()
        else:
            idle_event.clear()

    terminate = lambda: True
    if die_event is not None:
        terminate = lambda: not die_event.is_set()
   
    while terminate():

        await sendblob(writer,{"command" : "Acknowledge"})
            
        message = await getblob(reader)
        new_status = None

        if template:
            partial_update(state, template, message)
            new_status = state[idle_key]
        else:
            recursive_update(state, message)
            new_status = state['state']['status']
    
        if new_status == 'idle' and idle_event is not None:
            idle_event.set() # Wake everyone up!

        status = new_status

    writer.close()
    await writer.wait_closed()

async def command_connection():
    """ Open a socket and set it up for running commands """

    reader, writer = await asyncio.open_unix_connection(SOCKET_ADDRESS)
    await sendblob(writer, {"mode":"command","version": 8})
    await getblob(reader)

    return reader, writer


async def run_commands(connection, idle, commands):

    
    for g in commands:
        await sendblob(connection[1], {"code" : g, "channel" : 0, "command" : "SimpleCode"})
        await connection[0].read(MM_BUFFER_SIZE)
        idle.clear()
    # May take a little bit for the machine to become busy...
    await idle.wait()

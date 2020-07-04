import asyncio
from machine_state import sendblob, getblob, track_machine_state

SOCKET_ADDRESS = '/var/run/dsf/dcs.sock'
MM_BUFFER_SIZE = 65536


async def initialize_connection():
    """ Open a socket and set it up for running commands """

    reader, writer = await asyncio.open_unix_connection(SOCKET_ADDRESS)
    await sendblob(writer, {"mode":"command","version": 8})
    await getblob(reader)

    return reader, writer


async def run_commands(connection, idle, commands):

    await idle.wait()
    
    for g in commands:
        await sendblob(connection[1], {"code" : g, "channel" : 0, "command" : "SimpleCode"})
        await connection[0].read(MM_BUFFER_SIZE)
        idle.clear()
    # May take a little bit for the machine to become busy...
    await idle.wait()


async def main():

    """ Test running and blocking on gcode """

    state = {}
    idle_flag = asyncio.Event()
    idle_flag.clear()
    
    status_loop = asyncio.create_task(track_machine_state(state, {'state' : {'status' : 'idle'}}, idle_flag))


    conn = await initialize_connection()

    print("Running commands")
    await run_commands(conn, idle_flag, ["G0 Z10", "G0 Z20", "G0 Z10"])
    print("Running done")

    await status_loop

asyncio.run(main())
    
    

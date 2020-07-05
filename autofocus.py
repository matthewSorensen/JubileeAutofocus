import cv2
from imutils.video import WebcamVideoStream
import numpy as np
import asyncio
import janus
from machine_state import sendblob, getblob, track_machine_state, command_connection, run_commands


def CMSL(img, window):
    """
        Contrast Measure based on squared Laplacian according to
        'Robust Automatic Focus Algorithm for Low Contrast Images
        Using a New Contrast Measure'
        by Xu et Al. doi:10.3390/s110908281
        window: window size= window X window"""
    ky1 = np.array(([0.0, -1.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.0]))
    ky2 = np.array(([0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, -1.0, 0.0]))
    kx1 = np.array(([0.0, 0.0, 0.0], [-1.0, 1.0, 0.0], [0.0, 0.0, 0.0]))
    kx2 = np.array(([0.0, 0.0, 0.0], [0.0, 1.0, -1.0], [0.0, 0.0, 0.0]))
    g_img = abs(cv2.filter2D(img, cv2.CV_32F, kx1)) + \
                abs(cv2.filter2D(img, cv2.CV_32F, ky1)) + \
                abs(cv2.filter2D(img, cv2.CV_32F, kx2)) + \
                abs(cv2.filter2D(img, cv2.CV_32F, ky2))
    return cv2.boxFilter(g_img * g_img,-1,(window, window),normalize=True)

def cv_worker_thread(qs):

    in_q, out_q = qs
    cam = cv2.VideoCapture(0)

    while True:
        g = in_q.get()
        if g is None:
            break
        ret, frame = cam.read()
        out_q.put(CMSL(frame, 10).mean())
        
    cam.release()
    out_q.join()


async def worker_thread(qs, conn, idle):
    inq, outq = qs
    
    for z in range(165, 175):
        
        await run_commands(conn, idle, [f"""G0 Z{z}"""])

    await inq.put(0)
    val = await outq.get()
    outq.task_done()
    print(val)
    await inq.put(None)


async def async_main(qs):

    """ Test running and blocking on gcode """

    inq, outq = qs
    
    loop = asyncio.get_event_loop()

    idle_flag = asyncio.Event()
    die_flag = asyncio.Event()
    
    
    status_loop = asyncio.create_task(track_machine_state({}, {}, idle_flag, die_flag))
    conn = await command_connection()


    for z in range(160, 180):
        
        await run_commands(conn, idle_flag, [f"""G0 Z{z}"""])
        
        await inq.put(0)
        val = await outq.get()
        print(val)
        outq.task_done()
        

    die_flag.set()
    await status_loop
    await qs[0].put(None)



async def main():

    """ Test running and blocking on gcode """

    inq,outq = janus.Queue(),janus.Queue()
  
    
    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(None, cv_worker_thread, (inq.sync_q, outq.sync_q))
    await async_main((inq.async_q,outq.async_q))
    await fut
    inq.close()
    outq.close()
    await outq.wait_closed()
    
    
asyncio.run(main())

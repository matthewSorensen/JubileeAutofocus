import cv2
from imutils.video import WebcamVideoStream
import numpy as np
import asyncio
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



async def main():

    """ Test running and blocking on gcode """

    loop = asyncio.get_event_loop()

    idle_flag = asyncio.Event()
    die_flag = asyncio.Event()
    
    
    status_loop = asyncio.create_task(track_machine_state({}, {}, idle_flag, die_flag))
    conn = await command_connection()


    for z in range(165, 175):
        
        await run_commands(conn, idle_flag, [f"""G0 Z{z}"""])
        print("Frame")
        await asyncio.sleep(1)


    die_flag.set()
    await status_loop

asyncio.run(main())

import asyncio
import janus
import cv2
import numpy as np



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

def threaded(in_q, out_q):

    cam = cv2.VideoCapture(0)

    while True:
        g = in_q.get()
        if g is None:
            break
        ret, frame = cam.read()
        out_q.put(CMSL(frame, 10).mean())
        
    cam.release()
    out_q.join()


async def async_coro(in_q,out_q):

    for i in range(100):
        await in_q.put(0)
        val = await out_q.get()
        print(val)
        out_q.task_done()
    await in_q.put(None)

async def main():
    inq,outq = janus.Queue(),janus.Queue()
  
    
    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(None, threaded, inq.sync_q, outq.sync_q)
    await async_coro(inq.async_q,outq.async_q)
    await fut
    inq.close()
    outq.close()
    await outq.wait_closed()


asyncio.run(main())

import cv2
import numpy as np
import thread_state
import time
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


print("Establishing camera connection")
cam = cv2.VideoCapture(0)

with thread_state.MachineConnection('/var/run/dsf/dcs.sock') as m:

    for z in range(150, 190):
        
        m.gcode(f"""G0 Z{z}""")
        
        ret, frame = cam.read()
        print(z,CMSL(frame, 10).mean())
        
        
cam.release()


import numpy as np
import time
import math
import random
import sys
import json
import tempfile
import shutil
import cv2
import os
import picamera
from machine_interface import MachineConnection



def frame_getter(resolution, camera):

    def ret():
        output = np.empty((resolution[1], resolution[0], 3), dtype=np.uint8)
        camera.capture(output, 'rgb', use_video_port = True)
        return np.transpose(output, axes = (1,0,2))

    return ret


if __name__ == '__main__':
    
    if len(sys.argv) < 2:
        exit()


    targets = []

    for x in sys.argv[1:]:
        parts = x.split(',')
        if len(parts) != 3:
            exit()
        targets.append((float(parts[0]),float(parts[1]),float(parts[2])))

    if len(targets) == 0:
        exit()

    with open("camera_cal.json","r") as f:
        cal  = json.load(f)


        
    with MachineConnection('/var/run/dsf/dcs.sock') as m:

        with picamera.PiCamera() as camera:
    
            camera.resolution = cal['resolution']
            camera.framerate = 24
            time.sleep(2)

            tmp = tempfile.mkdtemp()
            getter = frame_getter(cal['resolution'], camera)

            meta = {}
            
            for i,(x,y,z) in enumerate(targets):
                m.move(x,y,z + cal['bed_focus'])
                cv2.imwrite(os.path.join(tmp,str(i) + ".png"), getter())
                meta[i] = [x,y,z]


            with open(os.path.join(tmp,"meta.json"), "w") as f:
                json.dump({'cal':cal, 'photos':meta}, f)
                                   
            os.system(f"""tar -cf - -C {tmp} .""")

                
            shutil.rmtree(tmp)

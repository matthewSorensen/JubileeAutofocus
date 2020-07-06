import cv2
import numpy as np
import thread_state
import time
import math
import random



def find_single_point(image, blur = 5, thresh = 100):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (blur, blur), 0)
    thresh = cv2.threshold(blurred, thresh, 255, cv2.THRESH_BINARY)[1]
    area = image.shape[0] * image.shape[1]
    results = []
    for c in cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)[0]:
        M = cv2.moments(c)
        if M['m00'] > 0.8 * area:
            continue # Too big
        # Should check that it doesn't intersect the boundary of the image...
        results.append((M['m00'],int(M['m10']/M['m00']),int(M['m01']/M['m00'])))

    return results


template = {'move': {'axes' : {0 : {'userPosition': 'x'},
                               1 : {'userPosition': 'y'},
                               2 : {'userPosition': 'z'},
                               3 : {'userPosition': 'u'}}}}


# G0 Z198.18024587522453

print("Establishing camera connection")
cam = cv2.VideoCapture(0)


with thread_state.MachineConnection('/var/run/dsf/dcs.sock', template = template) as m:

    m.gcode("G0 X150 Y150 Z198.18024587522453")
    
    radius = 4
    points = 20
    position = m.current_state()

    x,y = position['x'], position['y']
    results = []
    for i in range(points):
        dx = 2 * radius * (random.random() - 0.5)
        dy = 2 * radius * (random.random() - 0.5)

        m.gcode(f"""G0 X{x + dx} Y{y + dy}""", block = True)
        
        frame = None
        for j in range(5):
            ret, frame = cam.read()
        cv2.imwrite(f"""img/{i}.png""",frame)

        results.append((x + dx, y + dy, find_single_point(frame)))
        
    m.gcode(f"""G0 X{x} X{y}""")
    print(results)


    
cam.release()

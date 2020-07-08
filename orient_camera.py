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
        results.append(np.array([int(M['m10']/M['m00']),int(M['m01']/M['m00'])]))

    if len(results) != 1:
        print("Image ambiguous!")
        return None

    return results[0]

def get_fresh_frame(cam, n = 5):
    """ For some reason, we need to read a few frames in order to get a fresh one. 
    This is very annoying. """
    frame = None
    for j in range(5):
        ret, frame = cam.read()
    return frame
    

def least_square_mapping(calibration_points):
    """Compute a 2x2 map from displacement vectors in screen space
    to real space. """
    n = len(calibration_points)
    real_coords, pixel_coords = np.empty((n,2)),np.empty((n,2))
    
    for i, (r,p) in enumerate(calibration_points):
        real_coords[i] = r
        pixel_coords[i] = p

    A = np.vstack([pixel_coords[:,0],pixel_coords[:,1],np.ones(n)]).T
    transform = np.linalg.lstsq(A, real_coords, rcond = None)

    return transform[0][0:2,:], max(*transform[1])
    


template = {'move': {'axes' : {0 : {'userPosition': 'x'},
                               1 : {'userPosition': 'y'},
                               2 : {'userPosition': 'z'},
                               3 : {'userPosition': 'u'}}}}


# G0 Z198.18024587522453

print("Establishing camera connection")
cam = cv2.VideoCapture(0)


with thread_state.MachineConnection('/var/run/dsf/dcs.sock', template = template) as m:

    m.gcode("G0 X147 Y148 Z198.18024587522453")
    
    radius = 4
    points = 20
    position = m.current_state()

    xy = np.array([position['x'], position['y']])
    results = []
    for i in range(points):
        # Choose a random point within a certain (Manhattan) radius of the center...
        target = 2 * radius * (np.random.rand(2) - 0.5) + xy
        # ...go there, and...
        m.gcode(f"""G0 X{target[0]} Y{target[1]}""")
        # ...take a photo!
        pxy = find_single_point(get_fresh_frame(cam))
        print(f"""Data point: {target[0]},{target[1]} vs. {pxy[0]},{pxy[1]}""")        
        results.append((target, pxy))

        
    matrix, residual = least_square_mapping(results)

    print(matrix, residual)

    # Now move the centroid of the dot to the center of the screen,
    # take a snap, and write that out as a human-checkable certificate
    center =np.array([640 / 2,480 / 2])
    point = matrix.T @ (center - results[0][1]) + results[0][0]
    m.gcode(f"""G0 X{point[0]} Y{point[1]}""")
    frame = get_fresh_frame(cam)
    # make some simple cross hairs too
    frame = np.array(frame)
    frame[:, 320,:] = 255, 0, 255
    frame[240, :,:] = 255, 0, 255
    cv2.imwrite(f"""cal_certificate.png""",frame)
    
                             
    m.gcode(f"""G0 X{xy[0]} X{xy[1]}""")
    


    
cam.release()

import cv2
import numpy as np
import time
import math
import random
import sys
import json

from machine_interface import MachineConnection

def find_single_point(image, blur = 5, thresh = 100):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (blur, blur), 0)
    thresh = cv2.threshold(blurred, thresh, 255, cv2.THRESH_BINARY)[1]
    area = image.shape[0] * image.shape[1]
    results = []
    y,x,_ = image.shape
    for c in cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)[0]:
        M = cv2.moments(c)
        if M['m00'] > 0.8 * area:
            continue # Too big
        # Should check that it doesn't intersect the boundary of the image...
        results.append(np.array([M['m10']/M['m00'] - x/2,M['m01']/M['m00'] - y/2]))

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

    return transform[0][0:2,:].T, max(*transform[1])
    

if __name__ == '__main__':

    
    if len(sys.argv) < 2:
        print("Usage: calibrate_camera.py <bed focus height>")
        exit()
        
    focus_height = float(sys.argv[1])
    
    print("Establishing camera connection")
    cam = cv2.VideoCapture(0)


    with MachineConnection('/var/run/dsf/dcs.sock') as m:

        print("Moving to focus")
        m.move(Z = focus_height)
        
        radius = 4
        points = 20
        position = m.current_state()

        xy = m.xyzu()[0:2]
        results = []
        for i in range(points):
            # Choose a random point within a certain (Manhattan) radius of the center...
            target = 2 * radius * (np.random.rand(2) - 0.5) + xy
            # ...go there, and...
            m.move(target)
            # ...take a photo!
            pxy = find_single_point(get_fresh_frame(cam))
            print(f"""Data point: {target[0]},{target[1]} vs. {pxy[0]},{pxy[1]}""")        
            results.append((target, pxy))

        
        matrix, residual = least_square_mapping(results)
        u, sigma, v = np.linalg.svd(matrix)
        print("Residual error ", residual)

        # Write out the calibration data
        cal = {'bed_focus' : focus_height,
               'transform' : matrix.tolist(),
               'scaling_range' : [min(sigma), max(sigma)],
               'rotation' :  180 * math.acos(u[0,0]) / math.pi}
        print("Calibration file writen to camera_cal.json")
        with open("camera_cal.json","w") as j:
            json.dump(cal, j)
        # Now move the centroid of the dot to the center of the screen,
        # take a snap, and write that out as a human-checkable certificate
        point = results[0][0] - matrix @ (results[0][1])
        m.move(point)
        frame = get_fresh_frame(cam)
        # make some simple cross hairs too
        frame = np.array(frame)
        frame[:, 320,:] = 255, 0, 255
        frame[240, :,:] = 255, 0, 255
        fp = "cal_certificate.png"
        print("Check image written to " + fp)
        cv2.imwrite(fp,frame)

        m.move(xy)


    
    cam.release()

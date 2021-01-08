import numpy as np
import time
import math
import random
import sys
import json
import picamera

import cv2
from machine_interface import MachineConnection







def find_single_point(frame,gain = 3.0):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    pix = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, gain, minDist = 100)

    if pix is None:
        return None

    pix = pix[0,:]
    
    if pix.shape[0] != 1:
        return None

    x,y = pix[0,0:2]
    size = frame.shape
    
    return (x / size[1]) - 0.5, (y / size[0]) - 0.5

    
    
def least_square_mapping(calibration_points):
    """Compute a 2x2 map from displacement vectors in screen space
    to real space. """
    n = len(calibration_points)
    real_coords, pixel_coords = np.empty((n,2)),np.empty((n,2))
    
    for i, (r,p) in enumerate(calibration_points):
        real_coords[i] = r
        pixel_coords[i] = p
        
    x,y = pixel_coords[:,0],pixel_coords[:,1]
    A = np.vstack([x**2,y**2,x * y, x,y,np.ones(n)]).T
    transform = np.linalg.lstsq(A, real_coords, rcond = None)
    return transform[0], transform[1].mean()

def frame_getter(resolution, camera):

    def ret():
        output = np.empty((resolution[1], resolution[0], 3), dtype=np.uint8)
        camera.capture(output, 'rgb', use_video_port = True)
        return np.transpose(output, axes = (1,0,2))

    return ret


def collect_random_points(center, radius, evaluate_location, points = 10):

    for _ in range(points):
        target = 2 * radius * (np.random.rand(2) - 0.5) + center
        pxy = evaluate_location(target)

        if pxy is None:
            print(f"""CV failed at {target[0]}, {target[1]}""")
        else:
            print(f"""Data point: {target[0]},{target[1]} vs. {pxy[0]},{pxy[1]}""") 
            yield target, pxy

def collect_grid_points(transform, evaluate, border = 0.1, n = 5):
    for x in np.linspace(border - 0.5, 1 - border - 0.5, n):
        for y in np.linspace(border - 0.5 , 1 - border -0.5, n):
            v = np.array([x**2, y **2, x * y, x, y, 1.0])
            target = transform.T @ v
            pxy = evaluate(target)

            
            if pxy is None:
                print(f"""CV failed at {target[0]}, {target[1]}""")
            else:
                print(f"""Data point: {target[0]},{target[1]} vs. {pxy[0]},{pxy[1]}""") 
                yield target, pxy
            
def decorate_image(img):
    x,y,_ = img.shape
    
    # make some simple cross hairs too
    img[:, y //2,:] = 255, 0, 255
    img[x //2, :,:] = 255, 0, 255
    

if __name__ == '__main__':

    
    if len(sys.argv) < 2:
        print("Usage: calibrate_camera.py <bed focus height>")
        exit()
        
    focus_height = float(sys.argv[1])

    print("Establishing machine connection...")
    with MachineConnection('/var/run/dsf/dcs.sock') as m:

        with picamera.PiCamera() as camera:
    
            camera.resolution = (1648,1232)
            camera.framerate = 24
            time.sleep(2)
            print("...camera connection established")

            frames = frame_getter(camera.resolution, camera)
        
            print("Moving to focus")
            m.move(Z = focus_height)
        
            radius = 10
            points = 20
            position = m.current_state()

            xy = m.xyzu()[0:2]


            def evaluate_at_point(p):
                m.move(p, F= 10000)
                return find_single_point(frames())

            print("Begining rough pass")
            results = list(collect_random_points(xy, 10, evaluate_at_point))

            if len(results) < 5:
                print("Too many failures")
                exit()
            

            transform, residual = least_square_mapping(results)

            print("Begining fine pass")
            results += list(collect_grid_points(transform, evaluate_at_point))

            frame = frames()
            transform, residual = least_square_mapping(results)
            
            linear_part = transform[:-1,:]
            _,sigma,_ = np.linalg.svd(linear_part[-2:,:] @ np.diag([1 / frame.shape[0], 1 / frame.shape[1]]))
            
            
            # Write out the calibration data
            cal = {'bed_focus' : focus_height,
                   'transform' : transform[:-1,:].tolist(),
                   'resolution' : camera.resolution,
                   'scale': [min(sigma),max(sigma)]}
            with open("camera_cal.json","w") as j:
                json.dump(cal, j)

            print("Calibration file writen to camera_cal.json")
             # Now move the centroid of the dot to the center of the screen,
            # take a snap, and write that out as a human-checkable certificate
            point = transform.T @ np.array([0, 0, 0, 0, 0, 1])
            
            m.move(point)
            frame = frames()
            decorate_image(frame)
            fp = "cal_certificate.png"
            print("Check image written to " + fp)
            cv2.imwrite(fp,frame)
            
            m.move(xy)


import cv2
import time
import math
import random
import sys
import json

import numpy as np

from scipy.spatial import KDTree
from machine_interface import MachineConnection

def get_fresh_frame(cam, n = 5):
    """ For some reason, we need to read a few frames in order to get a fresh one. 
    This is very annoying. """
    frame = None
    for j in range(5):
        ret, frame = cam.read()
    return frame

def circle_settings(calibration, description, tol = 0.2):
    lo, hi = calibration["scaling_range"]
    dist = int((1 - tol) * description["spacing"] / lo)
    radius = 0.5 * description['diameter']
    return dist, int((1 - tol) * radius / lo), int((1 + tol) * radius / hi)

def find_all_circles(frame, settings, gain = 3.0):
    md,minr,maxr = settings
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    y,x,_ = frame.shape
    return cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, 3.0, 
                            minDist = md, minRadius = minr, maxRadius = maxr)[0][:,0:2] - np.array([x/2,y/2])

plate_description = {"spacing" : 4.5, "diameter" : 2.5, "grid" : [7,12], 'thickness' : 0.3}

with open("camera_cal.json") as f:
    cal = json.loads(f.read())

transform = np.array(cal['transform'])

vision_settings = circle_settings(cal, plate_description)

print("Establishing video connection")
cam = cv2.VideoCapture(0)

print("Initializing machine connection")
with MachineConnection('/var/run/dsf/dcs.sock') as m:

    
    m.move(Z = cal['bed_focus'] + plate_description['thickness'])
    
    x_max, vect = -1, None
    for v in find_all_circles(get_fresh_frame(cam), vision_settings):
        x,y = v
        if x > x_max:
            x_max = x
            vect = v

    point = m.xyzu()[0:2] - transform @ vect
    m.move(point)


    
cam.release()

    

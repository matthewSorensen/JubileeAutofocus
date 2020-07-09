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

def circle_settings(calibration, diameter, spacing, tol = 0.2):
    lo, hi = calibration["scaling_range"]
    dist = int((1 - tol) * spacing / lo)
    radius = 0.5 * diameter
    return dist, int((1 - tol) * radius / lo), int((1 + tol) * radius / hi)

def find_all_circles(frame, settings, gain = 2.2):
    md,minr,maxr = settings
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    y,x,_ = frame.shape
    return cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, gain, 
                            minDist = md, minRadius = minr, maxRadius = maxr)[0][:,0:2] - np.array([x/2,y/2])


def estimate_basis(points):
    # Find all of the angles of vectors between nearest neighbors,
    # with the quadrant quotiented out
    theta, n = 0,0
    for i,j in KDTree(realspace).query_pairs(0.9 * math.sqrt(2) * plate_description['spacing']):
        v = realspace[i] - realspace[j]
        # Expand the angle by 4x, and wrap back into the unit circle
        theta += np.angle((v[0] + 1j * v[1])**4)
        n += 1
    theta /= 4 * n
    phi = theta + math.pi / 2
    return np.array([np.cos(theta),np.sin(theta)]),np.array([np.cos(phi),np.sin(phi)])

def circle_callback(cam, settings, transform):

    def f():
        return find_all_circles(get_fresh_frame(cam), settings) @ transform.T
    return f

def center_nearest_circle(circles, machine, iterations = 3):

    for _ in range(iterations):
        distance, point = 100000, None
        for c in circles():
            d = c.dot(c)
            if d < distance:
                distance = d
                point = c
                
        print("Centering ", point)
        m.move(m.xyzu()[0:2] - point)


def follow_vector(circles, vector, machine):

    while True:
    
        centers = circles()
        best = np.argmax(centers.dot(vector))
        closest = np.argmin(np.sum(centers**2, axis = 1))

        
        if best != closest:
            point = m.xyzu()[0:2] - centers[best]
            print("Moving to ", point)
            m.move(point)
        else:
            break

    center_nearest_circle(circles, machine, iterations = 1)
    return m.xyzu()[0:2]



plate_description = {"spacing" : 4.5, 
                     "diameter" : 2.5, 
                     "grid" : [7,12], 
                     "thickness": 0.3,
                     # What are these offsets measured relative to? Hard to explain...
                     "fiducials" : {
                         "measurement_location" : 8.763, # in terms of short axis
                         "diameter" : 3.175,
                         "long_spacing" : [3.492 - 0.4,3.492 + 0.4],
                         "short_spacing": [0,0.4],
                         "distance" : 6.985 # Used only for circle finding
                     }} 

def in_band(dim, band):
    return dim > band[0] and dim < band[1]

def find_fiducals(frame, desc, cal, transform, vects, tol = 0.2):
    fid = desc['fiducials']
    settings = circle_settings(cal,fid['diameter'], fid['distance'])
    lb,sb = fid['long_spacing'], fid['short_spacing']
    lv,sv = vects
    n = 0
    mean = np.zeros(2)
    for x in find_all_circles(frame, settings, gain = 3.0) @ transform.T:
        if in_band(abs(sv.dot(x)), sb) and in_band(abs(lv.dot(x)),lb):
            n += 1
            mean += x
            
    if n == 2:
        return mean / 2

def write_with_cross(fp, img):
    
    img = img.copy()

    img[:, 320,:] = 255, 0, 255
    img[240, :,:] = 255, 0, 255

    cv2.imwrite(fp, img)


with open("camera_cal.json") as f:
    cal = json.loads(f.read())

transform = np.array(cal['transform'])

vision_settings = circle_settings(cal, plate_description['diameter'], plate_description['spacing'])

print("Establishing video connection")
cam = cv2.VideoCapture(0)

print("Initializing machine connection")
with MachineConnection('/var/run/dsf/dcs.sock') as m:

    
    m.move(150, 150 , cal['bed_focus'] + plate_description['thickness'])


    circles = circle_callback(cam, vision_settings, transform)

    start =  m.xyzu()[0:2]
    realspace = circles() + m.xyzu()[0:2]
    u,v = estimate_basis(realspace)

    
    first_corner = follow_vector(circles, u + v, m)
    write_with_cross("fiducials/corner1.png",get_fresh_frame(cam))

    m.move(start)
    second_corner = follow_vector(circles, 0 - u - v, m)
    write_with_cross("fiducials/corner2.png",get_fresh_frame(cam))

    fiducials = None

    for i,(a,b) in enumerate([[first_corner,second_corner],[second_corner, first_corner]]):
        if fiducials is not None:
            break
        
        diag = b - a
        lv,sv = (u,v) if abs(u.dot(diag)) > abs(v.dot(diag)) else (v,u)

        reference_point = a + 0.5 * lv * lv.dot(diag)
        offset = plate_description['fiducials']['measurement_location'] * sv

        for sign in [-1,1]:

            print("Checking for fiducials at ", reference_point + sign * offset)
            m.move(reference_point + sign * offset)
            f = find_fiducals(get_fresh_frame(cam), plate_description, cal, transform, (lv,sv))
            if f is not None:
                print("Found fiducials")
                fiducials = f + m.xyzu()[0:2], (a,b), sv, lv
                break


    origin, lower_left, upper_right = None, None, None
        
            
    f,(start,end), short, longv = fiducials
    centroid = (f + start + end) / 3
    vector = f - centroid
    orientation = np.array([vector[1],-1 * vector[0]])
    
    bottom, top = None, None
    dstart, dend = math.sqrt(sum((start - f)**2)), math.sqrt(sum((end - f)**2))
    if dstart < dend:
        bottom = start
        top = end
    else:
        bottom = end
        top = start

    if orientation.dot(f - bottom) > 0:

        origin = top
        print("Centering on upper right")
        m.move(bottom + short * short.dot(top - bottom))
        center_nearest_circle(circles, m, iterations = 2)
        upper_right = m.xyzu()[0:2]

        print("Centering on lower left")
        m.move(bottom + longv * longv.dot(top - bottom))
        center_nearest_circle(circles, m, iterations = 2)
        upper_right = m.xyzu()[0:2]
        
    else:
        print("Centering on origin")
        m.move(bottom + short * short.dot(top - bottom))
        center_nearest_circle(circles, m, iterations = 2)
        origin = m.xyzu()[0:2]
        lower_left = bottom
        upper_right = top


    m.move(origin)
    write_with_cross("fiducials/origin.png", get_fresh_frame(cam))
    m.move(upper_right)
    write_with_cross("fiducials/upper_right.png", get_fresh_frame(cam))
    m.move(lower_left)
    write_with_cross("fiducials/lower_left.png", get_fresh_frame(cam))

    blob = {'origin' : origin.tolist(),'ur' : upper_right.tolist(),'ll' : lower_left.tolist()}
    with open("orientation.json", "w") as f:
        json.dump(blob, f)

cam.release()

    

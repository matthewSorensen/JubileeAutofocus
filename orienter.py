import cv2
import numpy as np
import os
import matplotlib
import matplotlib.pyplot as plt
import math
import json
import sys


class CameraCal:
    def __init__(self, blob):
        self.blob = blob
        self.matrix = np.array(self.blob['transform'])
        self.size = self.blob['resolution']
        self.scale = self.blob['scale']
        
    def px_to_real(self, x, y):
        x = (x / self.size[1]) - 0.5
        y = (y / self.size[0]) - 0.5
     
        return self.matrix.T @ np.array([x**2,y**2,x * y, x, y])
    
    def distance_to_px_range(self, distance, slop = 0.1):
        return int((1 - slop) * distance / self.scale[1]), int((1 + slop) * distance / self.scale[0])



class DotManager:

    def __init__(self, ax, radius = 10):
        self.ax = ax
        self.radius = radius
        self.points = []
        

    def handle_event(self, event):
        if event.button != 1:
            return

        x,y = event.xdata, event.ydata
        # Isn't a linear search slow? Yeah, but small n and updatable quadtrees
        # requires dependencies
        def purge(elem):
            px,py,patch = elem
            if ((px -x)**2 + (py - y)**2) < self.radius**2:
                patch.remove()
                return False
            return True

        n = len(self.points)
        self.points = [e for e in self.points if purge(e)]
        
        if n == len(self.points) and event.dblclick:
            c = matplotlib.patches.Circle((event.xdata, event.ydata), radius = self.radius, color = 'b')
            ax.add_patch(c)
            self.points.append((event.xdata, event.ydata, c))

        plt.draw()

def solve_from_points(camera, points, origin, grid = (12, 7)):

    n = len(points)

    if n != 4:
        print(f"Need exactly 4 points - {n} provided. Failing.")
        exit()

    packed = np.empty((4,2))
    for i,(x,y,_) in enumerate(points):
        packed[i,:] = camera.px_to_real(x,y)
    # Setup a least squares system to find the spacing and rotation of the plate
    mu = np.mean(packed, axis = 0)
    n,m = (grid[0] - 1) / 2, (grid[1] - 1) / 2
    mat = np.array([[0 - n, m],[0-m, 0-n], [0-n, 0 - m],[m, 0 - n], [n,0-m],[m, n],[n,m],[-m,n]])
    # Solve it for the vectors along the long and short directions
    long = np.linalg.lstsq(mat, (packed - mu).flatten(), rcond = None)[0]
    # Get the other vector and first well
    short = np.array([0 - long[1], long[0]])
    zero = ((mat @ long).reshape(4,2) + mu)[0,:]

    return {'origin' : (zero + origin[0:2]).tolist(), 'z' : origin[2], 'grid': grid, 'v1' : long.tolist(), 'v2' : short.tolist()}





if len(sys.argv) < 3:

    print("usage: picker.py <output directory> <plate locations>")
    exit()

directory = sys.argv[1]
locations = ' '.join(sys.argv[2:])


print("Taking photographs")

os.system(f"""ssh pi@jubilee.local sudo python3 colony/grab_frame.py {locations} > {directory}.tar""")
print("Extracting photographs")
os.system(f"""rm -rf {directory}""")
os.system(f"""mkdir {directory}""")
os.system(f"""tar -xf {directory}.tar -C {directory}""")
os.system(f"""rm {directory}.tar """)


with open(os.path.join(directory,"meta.json"),"r") as f:
    meta = json.load(f)

cal = CameraCal(meta['cal'])
plates = {}
n = 0

for key, origin in meta['photos'].items():


    img = cv2.imread(os.path.join(directory, key + ".png"))

    fig, ax = plt.subplots()
    ax.imshow(img)
    
    dots = DotManager(ax)
    cid = fig.canvas.mpl_connect('button_press_event', dots.handle_event)    
    plt.show()
    
    plates['key'] = solve_from_points(cal,dots.points, meta['photos'][key])
    

meta['plates'] = plates

with open(os.path.join(directory, "meta.json"),"w") as f:
    json.dump(meta, f)


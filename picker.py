import cv2
import numpy as np
import os
import matplotlib
import matplotlib.pyplot as plt
import math
import json
import sys


#    def px_to_real(self, x, y)
#        x = (x / self.size[1]) - 0.5
#        y = (y / self.size[0]) - 0.5
#        return self.matrix.T @ np.array([x**2,y**2,x * y, x, y])   
#    def distance_to_px_range(self, distance, slop = 0.1):
#        return int((1 - slop) * distance / self.scale[1]), int((1 + slop) * distance / self.scale[0])



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
        if event.dblclick or event.button != 1:
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
        
        if n == len(self.points):
            c = matplotlib.patches.Circle((event.xdata, event.ydata), radius = self.radius, color = 'b')
            ax.add_patch(c)
            self.points.append((event.xdata, event.ydata, c))

        plt.draw()

            
def annotate_image(image, points, path, starting_number = 0, radius = 20):

    fig, ax = plt.subplots()
    ax.imshow(img)

    for i,(x,y,_) in enumerate(points):
        ax.text(x + radius, y, str(i + starting_number), c = 'm')
        c = matplotlib.patches.Circle((x,y), radius = radius, ec = 'g', fill = False)
        ax.add_patch(c)
    
    fig.savefig(path, bbox_inches='tight')
    plt.close()


def sample_records(points, camera_cal, photo_origin, plate_number = 0, starting_number = 0):

    origin = np.array(photo_origin)
    
    for i,(x,y,_) in enumerate(points):

        rx,ry = camera_cal.px_to_real(x,y)
        n = starting_number + i
        blob = {'plate' : plate_number, 'number' : n,
                'px': x, 'py' : y, 'origin' : photo_origin,
                'x' : rx + origin[0], 'y' : ry + origin[1], 'z' : origin[2]}

        yield n,blob



# go and get some photos... slowly...

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

# unpack the photos

with open(os.path.join(directory,"meta.json"),"r") as f:
    meta = json.load(f)

cal = CameraCal(meta['cal'])
samples = {}
n = 0

for key, origin in meta['photos'].items():


    img = cv2.imread(os.path.join(directory, key + ".png"))

    fig, ax = plt.subplots()
    ax.imshow(img)
    dots = DotManager(ax)
    cid = fig.canvas.mpl_connect('button_press_event', dots.handle_event)    
    plt.show()

    
    annotate_image(img, dots.points,os.path.join(directory, f"""samples_{key}.pdf"""), starting_number = len(samples))
    for i,blob in sample_records(dots.points, cal, origin, int(key), len(samples)):
        samples[i] = blob

meta['samples'] = samples

with open(os.path.join(directory, "meta.json"),"w") as f:
    json.dump(meta, f)

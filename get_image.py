import subprocess
import tempfile
from matplotlib import pyplot
import numpy as np
from PIL import Image
import sys

def get_image(user = 'pi', domain = 'jubilee.local'):

    with tempfile.TemporaryFile() as out:
        subprocess.run(["ssh",f"""{user}@{domain}""", "fswebcam -r 640x480 --no-banner -"], stdout = out)
        return np.asarray(Image.open(out))




    

img = get_image().copy()


img[:, 320,:] = 255, 0, 255
img[240, :,:] = 255, 0, 255

    
if len(sys.argv) == 2:
    im = Image.fromarray(img)
    im.save(sys.argv[1])
else:
    pyplot.imshow(img)
    pyplot.show()

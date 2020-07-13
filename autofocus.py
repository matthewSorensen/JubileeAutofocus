import cv2
import numpy as np
import thread_state
import time
import math

def CMSL(img, window):
    """
        Contrast Measure based on squared Laplacian according to
        'Robust Automatic Focus Algorithm for Low Contrast Images
        Using a New Contrast Measure'
        by Xu et Al. doi:10.3390/s110908281
        window: window size= window X window"""
    ky1 = np.array(([0.0, -1.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.0]))
    ky2 = np.array(([0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, -1.0, 0.0]))
    kx1 = np.array(([0.0, 0.0, 0.0], [-1.0, 1.0, 0.0], [0.0, 0.0, 0.0]))
    kx2 = np.array(([0.0, 0.0, 0.0], [0.0, 1.0, -1.0], [0.0, 0.0, 0.0]))
    g_img = abs(cv2.filter2D(img, cv2.CV_32F, kx1)) + \
                abs(cv2.filter2D(img, cv2.CV_32F, ky1)) + \
                abs(cv2.filter2D(img, cv2.CV_32F, kx2)) + \
                abs(cv2.filter2D(img, cv2.CV_32F, ky2))
    return cv2.boxFilter(g_img * g_img,-1,(window, window),normalize=True)


invphi = (math.sqrt(5) - 1) / 2  # 1 / phi
invphi2 = (3 - math.sqrt(5)) / 2  # 1 / phi^2

def gss(f, a, b, tol=1e-5):

    (a, b) = (min(a, b), max(a, b))
    h = b - a
    if h <= tol:
        return (a, b)

    # Required steps to achieve tolerance
    n = int(math.ceil(math.log(tol / h) / math.log(invphi)))

    c = a + invphi2 * h
    d = a + invphi * h
    yc = f(c)
    yd = f(d)

    for k in range(n-1):
        if yc < yd:
            b = d
            d = c
            yd = yc
            h = invphi * h
            c = a + invphi2 * h
            yc = f(c)
        else:
            a = c
            c = d
            yc = yd
            h = invphi * h
            d = a + invphi * h
            yd = f(d)

    if yc < yd:
        return (a, d)
    else:
        return (c, b)




def electric_slide(z_span, machine, camera):

    from_z, to_z = z_span
    m.gcode(f"""G0 Z{from_z}""", block = True)

    
    ret, frame = cam.read()
    best = CMSL(frame, 10).mean()
    t_start = time.time()
    best_t = t_start
    
    m.gcode(f"""G0 Z{to_z}""", block = False)
    time.sleep(0.5)
    while machine.is_busy():
        
        ret, frame = cam.read()
        t = time.time()
        score = CMSL(frame, 10).mean()
        print(score)
        if score > best:
            best = score
            best_t = t
        
    t_end = time.time()
    interp = (best_t - t_start) / (t_end - t_start)

    return (from_z + (to_z - from_z) * interp)


def oversampled_focus(zrange, steps, grid, center, machine, camera, scale = 2):

    lo, hi = zrange

    for i in range(steps):
        z = lo + (hi - lo) * i / steps
        m.gcode(f"""G0 Z{z}""")

        for j in range(grid):
            x = (j / grid) * scale + center[0]
            
            for k in range(grid):
                y = (k / grid) * scale + center[1]
                m.gcode(f"""G0 X{x} Y{y}""")
                ret, frame = cam.read()
                score = CMSL(frame, 10).mean()

                print(z, score)


def linear_search(lo,hi,steps, machine, camera):

    best = None
    best_z = None
    
    for z in np.linspace(lo,hi, steps):
        
        m.gcode(f"""G0 Z{z}""")
        ret, frame = cam.read()
        score = CMSL(frame, 10).mean()
        print(z, score)
        if best is None or score > best:
            best = score
            best_z = z

    return best_z, best


       
print("Establishing camera connection")
cam = cv2.VideoCapture(0)

with thread_state.MachineConnection('/var/run/dsf/dcs.sock') as m:
    
    def objective(z):
        
        m.gcode(f"""G0 Z{z}""")
        ret, frame = cam.read()
        return CMSL(frame, 10).mean()

    best_z, _ = linear_search(20, 200, 100, m, cam)
    print("Second search")
    best_z, _ = linear_search(best_z - 20,best_z, 100, m, cam)

    print("Final tuning")
    a,b = gss(objective, best_z- 2, best_z + 2 , 0.05)

    print(0.5 * (a + b))
    print(objective(0.5 * (a + b)))
    
    #oversampled_focus((z - 0.25, 56.97900690713337 + 0.25), 20, 5, (150, 150), m, cam)
    
cam.release()

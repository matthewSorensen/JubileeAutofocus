

#z clearance 24.98

# z dip: 16

# z touch: 13.75

# When commanded at 150 150, spot is really at 160.1, 131

# well 1:
#G0 Y50 X150

# well 2:
#G0 Y50 X170

# well 3
#G0 Y50 X190
import time
import math
import random
import sys
import json
import numpy as np
from machine_interface import MachineConnection



with open("orientation.json") as f:
    orientation = json.loads(f.read())

origin = np.array(orientation['origin'])
ll = np.array(orientation['ll'])
ur = np.array(orientation['ur'])

dx = (ur - origin) / 11
dy = (ll - origin) / 6

with open("camera_cal.json") as f:
    cal = json.loads(f.read())

z_clearance = 25
z_dip = 16
z_transfer = 13.75

offset = np.array([-10.1,19])

wells = [[f"""G0  Z{z_clearance}""", "G0 X150 Y50"],[f"""G0  Z{z_clearance}""", "G0 X170 Y50"],[f"""G0  Z{z_clearance}""", "G0 X190 Y50"]]
dip = [f"""G0 Z{z_dip}""",f"""G0 Z{z_clearance}"""]    
dot = [f"""G0 Z{z_transfer}""",f"""G0 Z{z_clearance}"""]    

print("Initializing machine connection")
with MachineConnection('/var/run/dsf/dcs.sock') as m:

    for i in range(3):
    
        m.gcode(wells[0])
        m.gcode(dip)    
        m.move(origin + i * dx + offset)
        m.gcode(dot)


    m.gcode(wells[2])
    m.gcode(dip)    
    m.gcode(dip)    

    
    for i in range(3):
    
        m.gcode(wells[1])
        m.gcode(dip)    
        m.move(origin + i * dx + dy + offset)
        m.gcode(dot)


    m.move(origin, Z = cal['bed_focus'] + 0.3)

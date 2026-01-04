# Getting Started with ArduPilot, DroneKit, and Mission Planner (SITL)

This guide walks you through setting up a Python environment, installing DroneKit, running ArduPilot SITL through Mission Planner, and testing vehicle control using Python scripts.

> [!NOTE]
> We'll eventually create a clean repo containing the required .py files and reqs

---

## 1. Create a New Python Virtual Environment

Open **Windows CMD** and run:

```cmd
python -m venv dronekit3
```

---

## 2. Activate the Environment

```cmd
cd dronekit3
Scripts\activate.bat
```

You should now see the environment name prefixed in your terminal, e.g.:

```
(dronekit3) C:\Users\you\py\dronekit3>
```

---

## 3. Install Required Python Packages

```cmd
pip install dronekit pymavlink future pyyaml
```

---

## 4. Patch DroneKit Deprecation Issue

DroneKit currently references a deprecated Python class. Apply this quick patch:

### Create the patch file

```cmd
edit dronekitpatch.py
```

Paste the following into the editor:

```python
"""
This script modifies the DroneKit __init__.py file to replace deprecated
'collections.MutableMapping' with 'collections.abc.MutableMapping'.
"""
from pathlib import Path

p = Path('Lib/site-packages/dronekit/__init__.py')
data = p.read_text()
data = data.replace('collections.MutableMapping', 'collections.abc.MutableMapping')

p.write_text(data)
print("Dronekit __init__.py patched successfully.")
```

Save (Ctrl+S) and exit (Ctrl+Q).

### Run the patch

```cmd
python dronekitpatch.py
```

---

## 5. Test DroneKit Installation

With the virtual environment still active:

```cmd
python
```

Inside Python:

```python
import dronekit
exit()
```

If no errors appear, DroneKit is installed correctly.

---

## 6. Install Mission Planner

Download and install Mission Planner:

**https://ardupilot.org/planner/docs/mission-planner-installation.html**

---

## 7. Launch SITL in Mission Planner

1. Open **Mission Planner** from the Windows Start Menu.
2. Click **Simulation**.

<img width="976" height="460" alt="image" src="https://github.com/user-attachments/assets/401f438d-f897-4c35-8be7-1cf79ef89d89" />

3. Select **MultiRotor** firmware.

<img width="973" height="461" alt="image" src="https://github.com/user-attachments/assets/f81964a6-925e-4925-85d2-8c538491f1ba" />

4. Return to the **Data** tab (top-right of window).

5. Open the **Actions** panel.

<img width="1203" height="623" alt="image" src="https://github.com/user-attachments/assets/fff80cd8-0f1e-4755-af71-6766725f1544" />


Mission Planner will automatically start SITL and listen on:

```
tcp:127.0.0.1:5763
```

---

## 8. Test DroneKit Connection to SITL

Create a test script:

```cmd
edit connect_and_read.py
```

Paste the following:

```python
import time
from dronekit import connect

# Mission Planner SITL default address
connection_string = "tcp:127.0.0.1:5763"

vehicle = connect(connection_string, wait_ready=True)
print("Connected to vehicle:", vehicle)

time.sleep(1)

for i in range(20):
    print('\nTime:', round(time.time()))
    print('Mode:', vehicle.mode)
    print('Battery:', vehicle.battery)
    print('Location:', vehicle.location)
    print('Attitude:', vehicle.attitude)
    print('Velocity:', vehicle.velocity)
    print('Groundspeed:', vehicle.groundspeed)
    time.sleep(1)

print('Connection test complete')
vehicle.close()
exit()
```

Run it:

```cmd
python connect_and_read.py
```

In the terminal, you should see live telemetry printed every second.

---

## 9. Manual Arm and Takeoff in Mission Planner

1. In Mission Planner **Actions** panel, change the Mode dropdown to **GUIDED** and then click **Arm/Disarm**.

<img width="463" height="636" alt="image" src="https://github.com/user-attachments/assets/dbe7a083-eff3-4d4a-b43f-70f39e865701" />

> [!IMPORTANT]
> **After arming, you have ~10 seconds to take off before auto‑disarm.**
> This is a default safety parameter in the vehicles. If you don't takeoff by then, just rearm and try again.

2. Right‑click the map → **Takeoff** → enter altitude.

<img width="1216" height="638" alt="image" src="https://github.com/user-attachments/assets/293fe84f-cc80-4754-ac20-004224c26846" />

---

## 10. Monitor SITL Vehicle While Commanding from Mission Planner

With SITL running, run your telemetry script again:

```cmd
python connect_and_read.py
```

In Mission Planner:

- Right‑click the map
- Select **Fly to Here**
- Confirm altitude

<img width="445" height="396" alt="image" src="https://github.com/user-attachments/assets/95c6533f-ff7f-4c37-8337-75d9b6edc025" />

In the terminal used to start the python script, you should see DroneKit telemetry update as the vehicle moves.

---

## 11. Control the Vehicle with DroneKit (Python)

Create a new script:

```cmd
edit test_flight.py
```

Paste the following:

```python
import time
from dronekit import connect, VehicleMode, LocationGlobalRelative

# Mission Planner SITL default address
connection_string = "tcp:127.0.0.1:5763"

vehicle = connect(connection_string, wait_ready=True)
print("Connected to vehicle:", vehicle)

time.sleep(1)
print('\nBegin DroneKit flight test.\n')

# Ensure GUIDED mode
if not vehicle.mode == VehicleMode("GUIDED"):
    print("Switching to GUIDED for takeoff")
    vehicle.mode = VehicleMode("GUIDED")
    time.sleep(1)

# Takeoff if not already airborne
if vehicle.location.global_relative_frame.alt < 1:
    print("Vehicle not airborne. Starting takeoff sequence.")
    vehicle.armed = True

    while not vehicle.armed:
        print("Arming vehicle...")
        time.sleep(1)
    print("Vehicle is armed.")
    time.sleep(1)

    print("Taking off to 10 meters...")
    vehicle.simple_takeoff(10)

    while vehicle.location.global_relative_frame.alt < 9:
        print(f'Taking off. Alt={round(vehicle.location.global_relative_frame.alt)}')
        time.sleep(1)
    print("Takeoff Complete")
    time.sleep(1)

# Cycle through modes
for m in ['AUTO', 'BRAKE', 'GUIDED']:
    vehicle.mode = VehicleMode(m)
    print("Vehicle mode changed to:", m)
    time.sleep(2)

# Move to a nearby coordinate
destination = LocationGlobalRelative(
    lat=vehicle.location.global_relative_frame.lat + 0.0002,
    lon=vehicle.location.global_relative_frame.lon + 0.0002,
    alt=vehicle.location.global_relative_frame.alt
)
print("New GUIDED destination:", destination)
vehicle.simple_goto(destination)
time.sleep(2)

while vehicle.airspeed > 0.2:
    print('Moving to destination...')
    time.sleep(2)

print('GoTo coordinate test complete')
time.sleep(1)

# Change altitude
print("New altitude target: 30 meters")
destination = LocationGlobalRelative(
    lat=vehicle.location.global_relative_frame.lat,
    lon=vehicle.location.global_relative_frame.lon,
    alt=30
)
vehicle.simple_goto(destination)

while abs(vehicle.location.global_relative_frame.alt - destination.alt) > 1:
    print("Moving to 30m Rel Alt. Current:", vehicle.location.global_relative_frame.alt)
    time.sleep(2)

print('Altitude test complete')
time.sleep(1)

# Return to launch
print('Returning to launch...')
vehicle.mode = VehicleMode('RTL')
time.sleep(1)

while vehicle.mode.name == 'RTL':
    if vehicle.location.global_relative_frame.alt < 1.0:
        break
    print('Returning to Launch...')
    time.sleep(2)

print('Vehicle landed.')
print('Connection test complete')
vehicle.close()
exit()
```

Run it:

```cmd
python test_flight.py
```

---

## You're Ready to Build Autonomous Missions

You now have:

- A working DroneKit Python environment  
- Mission Planner SITL running locally  
- Verified telemetry and control  
- A full example of autonomous takeoff, navigation, altitude change, and RTL  

You can now expand into autonomous missions, waypoint uploads, guided navigation, and more.

---
## Link Unreal Engine to SITL
1. Request url to download standalone .exe that launches the game
2. [Instructions](unreal_instructions.md)

---
## MavProxy
[MavProxy Docs](https://ardupilot.org/mavproxy/)

[Download MavProxy for Windows](https://firmware.ardupilot.org/Tools/MAVProxy/)

Download and install MavProxy for Windows. The installer should add 'mavproxy' to Windows paths, so you can start it by calling `mavproxy` in cmd terminal

### Sample MavProxy Connections

Format is: 

```
mavproxy --master=<flight controller or SITL> --out=<relay connection 1> --out=<relay connection 2>
```

1. Windows Mission Planner SITL - MavProxy - DroneKit Python

    With paths:
    - SITL: `tcp:127.0.0.1:5763`
    - DroneKit: `udp:127.0.0.1:14551`
  
    Start in cmd terminal:
   
   ```
   mavproxy --master=tcp:127.0.0.1:5763 --out=udp:127.0.0.1:14551
   ```

2. Docker SITL - DroneKit Python - Mission Planner GCS
...

   

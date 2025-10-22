"""
flight_manual - basic_demo.py
by igsxf 
https://github.com/igsxf22/flight_manual/
April 2024
add Gemini Lite Oct 2025

Basic demo with a few runnable commands to demonstrate
simple communication with vehicle through dronekit API
using LLM to interpret plain text inputs and return 
strucutured output

1. Launch a SITL Copter vehicle, ie from Mission Planner
2. Run this script
3. Enter Open AI API Key
4. Interact with the LLM in the console
5. Type 'exit' to end script

"""
import os
import json
from pathlib import Path
import time

from google import genai
from typing import Literal, Optional, List, TypedDict, Union
from pydantic import BaseModel, Field

print("If dronekit fails to import, see fix here:\n",
      'https://github.com/igsxf22/flight_manual?tab=readme-ov-file#fix-dronekit-import-issue')

from pymavlink import mavutil
from dronekit import connect, VehicleMode, LocationGlobal, LocationGlobalRelative


os.environ["GEMINI_API_KEY"] = '<Your Gemini API Key or Retrieve Key Method Here>'

# Commands: Pydantic objects with typed fields and a method to run the command with Dronekit
class cmd_GoToCoords(BaseModel):
    """ 
    Command: Go To Coordinates
            Go to coordinate specified by latitude, longitude and optional altitude
            Lat/Lon: decimal degrees, float. Alt: meters, float (optional)
            Frame is Relative unless explictly requested to "Global"
        key: cmd_GoToCoords
        values:
            {lat: float, lon: float, alt: Optional[float], frame: Literal["Relative", "Global"]}
        example: {"cmd_GoTo": {"lat": 38.9605, "lon": -77.3118, "alt": 20, "frame": "Relative"}}
    """
    lat: float = Field(..., description="Destination latitude, dec degrees")
    lon: float = Field(..., description="Destination longitude, dec degrees")
    alt: Optional[float] = Field(None, description="meters")
    frame: Literal["Relative", "Global"] = Field("Relative", description="Reference frame for the altitude")

    def run(self, vehicle):
        if self.alt is None:
            self.alt = vehicle.location.global_relative_frame.alt
        if self.frame == "Relative":
            dest = LocationGlobalRelative(self.lat, self.lon, self.alt)
        elif self.frame == "Global":
            dest = LocationGlobal(self.lat, self.lon, self.alt)
        vehicle.simple_goto(dest)
        

class cmd_Takeoff(BaseModel):
    """
    Command: Takeoff
            Take off to a specific altitude (meters)
            Alt is meters, default is 10.0 if None is provided
        key: cmd_Takeoff
        values: {"alt": float}
        example: {"cmd_Takeoff": {"alt": 10}}
    """
    alt: float = Field(10., description="meters")

    def run(self, vehicle):
        vehicle.simple_takeoff(self.alt)
        while not vehicle.location.global_relative_frame.alt>=self.alt*0.95:
            print(" Taking off... Altitude: ", vehicle.location.global_relative_frame.alt)
            time.sleep(1) 

        # Enable yaw commands with a simple_goto after takeoff
        vehicle.simple_goto(vehicle.location.global_relative_frame)
        time.sleep(0.5)
        print("Takeoff complete. Altitude: ", vehicle.location.global_relative_frame.alt)



class cmd_SetMode(BaseModel):
    """ 
    Command: Set Vehicle Mode
            Command to set the vehicle mode 
        key: cmd_SetMode
        values: {"GUIDED", "ALT_HOLD", "RTL", "AUTO"}
        example: {"cmd_SetMode": {"mode": "GUIDED"}}
    """
    mode: Literal["GUIDED", "ALT_HOLD", "RTL", "AUTO"]
    
    def run(self, vehicle):
        vehicle.mode = VehicleMode(self.mode)
            

class cmd_Arm(BaseModel):
    """
    Command: Arm Vehicle
            Arm or disarm the vehicle; True = arm, False = disarm
        key: cmd_Arm
        values: {"arm": bool}
        example: {"cmd_Arm": {"arm": True}}
    """
    arm: bool    
    
    def run(self, vehicle):
        vehicle.armed = True if self.arm else False


class cmd_GoToLocal(BaseModel):
    """
    Command: Go To Local Forward Right Up (FRU)
            Go to position relative to current location when request is in
            reference to the local frame (FRU) insead of the global frame (lat/lon).
            Back, Left, Down are negative values.
            Limited to 10 meters
            x: forward/backward (meters) y: right/left (meters) z: up/down (meters)
        key: cmd_GoToLocal
        values: {"x": float, "y": float, "z": float}
        example: {"cmd_GoToLocal": {"x": 10, "y": 0, "z": 0}}
    """
    x: float = 0
    y: float = 0
    z: float = 0

    def run(self, vehicle):
        msg = vehicle.message_factory.set_position_target_local_ned_encode(
            0, 0, 0, mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED,
            0b0000111111000111, 0, 0, 0,
            self.x, self.y, -self.z, 
            0, 0, 0, 0, 0)
        vehicle.send_mavlink(msg)
        print("Reminder: GoToLocal is not setup for Global frame coordinates, \
              only local FRU frame (ie North=Forward, East=Right)")

class cmd_SetYaw(BaseModel):
    """
    Command: Set Yaw
        Set the vehicle's yaw to a specific angle (degrees).
        Frame: "Relative" or "Global"
            - Relative: turn left/right by degrees (0 to -180 left, 0 to 180 for right)
            - Global: set yaw to absolute heading (0–360)
        key: cmd_SetYaw
        values: {"frame": Literal["Relative", "Global"], "yaw": float}
        example: {"cmd_SetYaw": {"frame": "Relative", "yaw": 25}}
    """
    frame: Literal["Relative", "Global"] = Field("Relative", description="Reference frame for the heading")
    yaw: float = Field(..., description="Yaw angle in degrees")

    def run(self, vehicle):
        yaw_speed = 90.0  # yaw speed deg/s

        if self.frame == "Relative":
            is_relative = 1  # yaw relative to current heading
            if self.yaw >= 0:
                direction = 1  # clockwise
            else:
                direction = -1  # counter-clockwise
            target_yaw = abs(self.yaw)
        
        elif self.frame == "Global":
            is_relative = 0  # yaw is an absolute angle
            current_yaw = vehicle.heading  # current heading in degrees
            target_yaw = self.yaw % 360  # normalize target yaw to [0, 360)

            # Calculate shortest direction
            delta_yaw = (target_yaw - current_yaw + 540) % 360 - 180
            if delta_yaw > 0:
                direction = 1  # clockwise
            else:
                direction = -1  # counter-clockwise
           
        # Create the CONDITION_YAW command
        msg = vehicle.message_factory.command_long_encode(
            0, 0, mavutil.mavlink.MAV_CMD_CONDITION_YAW, 0,
            target_yaw,   # param1: angle or relative offset
            yaw_speed,    # param2: yaw speed
            direction,    # param3: direction (-1 ccw, 1 cw)
            is_relative,  # param4: relative (1) or absolute (0)
            0, 0, 0
        )
        vehicle.send_mavlink(msg)

class CommandPromptOutput(BaseModel):
    """ Response from the LLM """
    speech_response: str = Field(
        ..., 
        description="A concise, simple operational response/acknowledgement from one pilot to another"
    )
    commands: List[str] = Field(
        ..., 
        description="List of commands parsed from the input"
    )


def parse_response_to_commands(response, available_cmds):
    """ Parse the response to runnable commands """
    cmds = response.parsed.commands
    cmds = [json.loads(i) for i in cmds]
    new_commands = []
    for c in cmds:
        cmd_name = list(c.keys())[0]

        # If the command name is in the list of all commands
        if cmd_name in [cmd.__name__ for cmd in available_cmds]:

            # ... Create an instance of the command class
            cmd_class = [cmd for cmd in available_cmds if cmd.__name__ == cmd_name][0]
            cmd = cmd_class(**c[cmd_name])
            new_commands.append(cmd)

    return new_commands


def run_commands(commands, vehicle, verbose=True):
    """ Run the commands on the vehicle if they have a run method """
    for c in commands:
        if hasattr(c, 'run'):
            c.run(vehicle)
            display_str = f"Running: {c.__class__.__name__} | {c.model_dump()}"
        else:
            display_str = f"Command: {c.__class__.__name__} has no run method."
            
        if verbose:
            print(display_str)

prompt_template = """
You are a drone control system. Your task is to convert user input into 
structured commands for the drone.

First, Decide if the user input is a command or a question. 
If it's a command, parse it into structured commands.
If it's a question, respond with a simple operational response based
your general knowledge, especially about drone operations.

Documentation and formatting for commands are:

{cmds_doc}

The user input is: 

{user_input}

Steps if input includes commands:
    1. Parse the user input to identify:
        - Individual actions requested in the input
        - The command best suited for each action

    2. Use the command class documents to create JSON string for each command
Return a JSON object with two fields:
- "speech_response": A concise, simple operational response/acknowledgement from one pilot to another
- "commands": A list of JSON strings, each representing a command to be executed
The response should be in the following JSON format:
{{
    "speech_response": "<concise operational response>",
    "commands": [
        "<JSON string of command 1>",
        "<JSON string of command 2>",
        ...
    ]
}}  
"""

system_prompt = """ 
You are an AI copilot for drone operations. 
Speak ultra-concisely with an operational tone.
"""

all_cmds = [
    cmd_SetMode, 
    cmd_Arm, 
    cmd_GoToCoords, 
    cmd_Takeoff, 
    cmd_GoToLocal, 
    cmd_SetYaw
    ]

cmds_doc = "\n\n".join([_cmd.__doc__ for _cmd in all_cmds])

if __name__ == "__main__":


    connection_string = 'tcp:127.0.0.1:5763'
    vehicle = connect(connection_string, wait_ready=True, baud=57600, rate=60)
    vehicle.mode = "GUIDED"
    print("Vehicle Connected.")


    client = genai.Client(
        api_key=os.getenv("GEMINI_API_KEY"),
    )

    while True:

        new_commands = []

        user_input = input("\nEnter command: ")

        if user_input.lower() == "exit":
            break

        # print(prompt_template.format(cmds_doc=cmds_doc, user_input=user_input))

        start_time = time.time()

        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt_template.format(
                cmds_doc=cmds_doc, 
                user_input=user_input
                ),
            config={
                'temperature': 0.0,
                "response_mime_type": "application/json",
                "response_schema": CommandPromptOutput,
            },
        )

        print("\nLLM Response:")
        print(response.parsed.model_dump_json(indent=2))

        
        new_commands = parse_response_to_commands(response, all_cmds)
        run_commands(new_commands, vehicle)

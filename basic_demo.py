import os
import json
import time

from openai import OpenAI
from typing import Literal, Optional, List
from pydantic import BaseModel, Field

from pymavlink import mavutil
from dronekit import connect, VehicleMode, LocationGlobal, LocationGlobalRelative

# os.environ["OPENAI_API_KEY"] = <YOUR API KEY>

if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = input("OpenAI API key: ")

# Connect to the vehicle - this is the default for Mission Planner SITL
connection_string = 'tcp:127.0.0.1:5763'
vehicle = connect(connection_string, wait_ready=True, baud=57600, rate=60)
vehicle.mode = "GUIDED"
print("Vehicle Connected.")

class cmd_GoToCoords(BaseModel):
    """ 
    Command: Go To Coordinates
            Go to coordinate specified by latitude, longitude and optional altitude
            Lat/Lon: decimal degrees, float. Alt: meters, float (optional)
            Frame is Relative unless explictly requested to "Global"
        key: cmd_GoToCoords
        values:
            {lat: float, lon: float, alt: Optional[float], frame: Literal["Relative", "Global"]}
        example: {"cmd_GoTo": {"lat": 38.947, "lon": -77.475, "alt": 20, "frame": "Relative"}}
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
        key: cmd_Takeoff
        values: {"alt": float}
        example: {"cmd_Takeoff": {"alt": 10}}
    """
    alt: float = Field(..., description="meters")

    def run(self, vehicle):
        vehicle.simple_takeoff(self.alt)


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
    x: float = Field(..., le=-10., ge=10)
    y: float = Field(..., le=-10., ge=10)
    z: float = Field(..., le=-10., ge=10)

    def run(self, vehicle):
        msg = vehicle.message_factory.set_position_target_local_ned_encode(
            0, 0, 0, mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED,
            0b0000111111000111, 0, 0, 0,
            self.x, self.y, -self.z, 
            0, 0, 0, 0, 0)
        vehicle.send_mavlink(msg)


class cmd_SetHeading(BaseModel):
    """
    Command: Set Heading
            Set the vehicle's yaw to a specific angle (degrees)
            Frame: "Relative" or "Global" = If the request is local (like turn left, add degrees, etc)
            vs global (like turn to 90 degrees, set heading to North, etc)
            Format local -180 to 180 degrees (relative to the vehicle's current heading)
            Format global: 0 to 360 degrees (absolute heading)
        key: cmd_SetHeading
        values: {"frame": Literal["Relative", "Global"], "yaw": float}
        example: {"cmd_SetHeading": {"frame": "Relative", "yaw": 25}}
    """
    frame: Literal["Relative", "Global"] = Field("Relative", description="Reference frame for the heading")
    yaw: float = Field(..., description="Yaw angle in degrees")

    def run(self, vehicle):
        yaw_speed = 0 # yaw speed deg/s
        direction = 1 # direction -1 ccw, 1 cw

        # yaw relative to direction of travel or absolute angle
        if self.frame == "Relative":
            is_relative = 1 
        else:
            is_relative = 0
        # create the CONDITION_YAW command using command_long_encode()
        msg = vehicle.message_factory.command_long_encode(
            0, 0, mavutil.mavlink.MAV_CMD_CONDITION_YAW, 0, 
            self.yaw,
            yaw_speed, direction, is_relative, 
            0, 0, 0)
        vehicle.send_mavlink(msg)


class OpenAIOutput(BaseModel):
    model: str
    temperature: float
    usage: dict
    text: str
    parsed: Optional[dict] = None

    def to_ai_message(self):
        return {
            "role": "ai",
            "content": self.text if not self.parsed else self.parsed,
        }
    

def parse_openai_output(response):
    return OpenAIOutput(
        model=response.model,
        temperature=response.temperature,
        usage=response.usage.model_dump(),
        text=response.output[0].content[0].text,
        parsed = None
    )


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
    """ Parse the response to commands """
    cmds = response.output_parsed.commands
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


client = OpenAI()

prompt_template = """
You are a drone control system. Your task is to convert user input into structured commands for the drone.

Initial decision: Decide if the user input is a command or a question. 
If it's a command, parse it into structured commands. If it's a question, provide an answer.

Documentation and formatting for commands are:

{cmds_doc}

The user input is: 

{user_input}

Steps if input includes commands:
    1. Parse the user input to identify:
        - Individual actions requested in the input
        - The command best suited for each action

    2. Use the command class documents to create JSON for each command

Finally, return your response as CommandPromptOutput object:
    - text: The response text
    - commands: commands as JSON that can be unpacked into pydantic objects
    
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
    cmd_SetHeading
    ]

cmds_doc = "\n\n".join([_cmd.__doc__ for _cmd in all_cmds])

while True:

    new_commands = []

    user_input = input("\nEnter command: ")

    if user_input.lower() == "exit":
        break

    # print(prompt_template.format(cmds_doc=cmds_doc, user_input=user_input))

    start_time = time.time()

    response = client.responses.parse(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": prompt_template.format(
                    cmds_doc=cmds_doc, 
                    user_input=user_input
                    )
            },
        ],
        text_format=CommandPromptOutput,
        temperature=0.1
        
    )
    
    openai_response = parse_openai_output(response)

    print(f"\nResponse Params:")
    print(f"  Time: {time.time() - start_time} seconds:")
    print(f"  Model: {openai_response.model}")
    print(f"  Temperature: {openai_response.temperature}")
    print(f"  Usage: {openai_response.usage}")
    # print(f"  Text: {openai_response.text}") Redudant if using .parse for completions
    
    openai_response.parsed = response.output_parsed
    print(f"\nParsed Output:")

    if openai_response.parsed:
        print(f"  Speech Response: {openai_response.parsed.speech_response}")
        print(f"  Commands: {openai_response.parsed.commands}")

    new_commands = parse_response_to_commands(response, all_cmds)
    run_commands(new_commands, vehicle)

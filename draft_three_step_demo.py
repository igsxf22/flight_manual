"""
by igsxf22, 2025
New draft for multi-step version

Steps
  1. Decide if input requires cmd parsing or just simple text response // nano works
  2. If cmds, classify and format cmds // mini works
    a. Immediate
    b. Conditional
    c. Continous
  3. Process commands (outlined)
    a. new immediate have priority, interrupting any existing continuous
    b. start any new continuous
    c. conditional will run in separate thread, converted to immediate when condition met

Doesn't use chat history yet
Connects to vehicle, but does not implement cmd execution yet or pass vehicle state into prompts
Executing commands and using vehicle state will be similar to basic_demo.py
"""

import os
import time
import json
import openai
from pathlib import Path
from typing_extensions import TypedDict, List, Literal, Optional
from pydantic import BaseModel, Field
from dronekit import connect, Vehicle, VehicleMode, LocationGlobalRelative, LocationLocal

# Connect to the vehicle
vehicle = connect('tcp:127.0.0.1:5763', wait_ready=True, baud=57600)

# Load API keys from a JSON file
API_KEY = input("Enter your API key (Or, add your own code to replace this step in line 33:  ")
os.environ["OPENAI_API_KEY"] = API_KEY

# Create an OpenAI client
client = openai.Client()

# Create message hist
MESSAGES = [
    {
        "role": "system", 
        "content": """You are a copilot for drone operations. Respond to the user input. 
        Maintain a professional, operational, but helpful tone."""
     }
]

# Building blocks
class llmEval(TypedDict):
    model: str
    total_tokens: int
    time: float

class VehicleStatus(TypedDict):
    mode: VehicleMode
    armed: bool
    lat: float
    lon: float
    rel_alt: float
    abs_alt: float
    local_xyz: dict[str, float]
    groundspeed: float = 0.0

def get_vehicle_status(vehicle: Vehicle) -> VehicleStatus:
    """
    Get the current status of the vehicle
    """
    return VehicleStatus(
        mode=vehicle.mode,
        armed=vehicle.armed,
        lat=vehicle.location.global_relative_frame.lat,
        lon=vehicle.location.global_relative_frame.lon,
        rel_alt=vehicle.location.global_relative_frame.alt,
        abs_alt=vehicle.location.global_frame.alt,
        local_xyz={
            "x": vehicle.location.local_frame.north,
            "y": vehicle.location.local_frame.east,
            "z": -vehicle.location.local_frame.down
        },
        groundspeed=vehicle.groundspeed
    )

CmdDocumentation = {
    "SetMode": {
        "description": "Set the vehicle mode",
        "args": {
            "mode": "str: 'AUTO', 'GUIDED', 'RTL', or 'POSHOLD'",
        },
        "example": {"cmd": "SetMode", "mode": "LOITER"}
    },
    "ArmDisarm": {
        "description": "Arm or disarm the vehicle",
        "args": {
            "arm": "bool: True to arm, False to disarm"
        },
        "example": {"cmd": "ArmDisarm", "arm": True}
    },
    "GoToGeo": {
        "description": "Go to geographic location, provided as lat and lon decimal degrees",
        "args": {
            "latitude": "float: Latitude of the target location",
            "longitude": "float: Longitude of the target location"
        },
        "example": {"cmd": "GoToGeo", "latitude": 37.7749, "longitude": -122.4194}
    },
    "GoToLocal": {
        "description": "Go to local coordinates relative to current position, provided as x, y, z in meters",
        "args": {
            "x": "float: meters forward, or negative to move backward",
            "y": "float: meters right, or negative to move left",
            "z": "float: meters up, or negative to move down"
        },
        "example": {"cmd": "GoToLocal", "x": 10.0, "y": 5.0, "z": 10.0}
    },
    "SetOrbit": {
        "description": "Set the vehicle to orbit a specific location",
        "args": {
            "radius": "float: Radius of the orbit in meters",
            "direction": "str: clockwise or counterclockwise)"
        },
        "example": {"cmd": "SetOrbit", "radius": 50.0, "direction": "clockwise"}
    },
    "DoSpecialAction": {
        "description": "Perform a special action from a predefined list",
        "args": {
            "action": "List[Literal['takeoff', 'sweep360']]"
        },
    }
}

# ---- Steps ----
class ParseUserInputStep_Input(BaseModel):
    """
    Input template for the user input parser step
    """
    prompt_template: str = """
    You are a copilot for drone operations.
    This is part of a multi-step process to parse user input and determine flight commands
    for an ArduCopter-based vehicle

    This is step 1, where you will classify the user input into one of two categories:
        1. Simple response: the user input can be answered with a simple response
        2. Flight command: the user input likely contains one or more flight commands to be executed

    If 1: provide a simple response to the user input
    If 2: break down user input steps/elements, and return a list of potential flight commands
    to be validated in the next step, in plain language strings.

    User input to be classified:
    {user_input}

    After classifying the user input, return the response in the provided pydantic schema.
    """
    user_input: str = Field(
        ...,
        description="User input to be classified, in plain language"
    )

    def to_prompt(self) -> str:
        """
        Convert the input to a prompt string for the LLM
        """
        return self.prompt_template.format(user_input=self.user_input)
    
class ParseUserInputStep_Output(BaseModel):
    """
    Initial classification of user input
    """
    response_type: Literal["simple_response", "flight_command"]
    simple_response: Optional[str] = Field(
        None, description="Simple response to the user input if applicable"
    )
    flight_commands: Optional[List[str]] = Field(
        None, description="List of flight commands to be executed"
    )

class ParseCommandsStep_Input(BaseModel):
    """
    Input template for the flight command parser step
    """
    prompt_template: str = """
    You are a copilot for drone operations.
    This is part of a multi-step process to parse user input and determine flight commands
    for an ArduCopter-based vehicle

    This is step 2, where the user input has been classified as containing flight commands.
    You will parse the commands and do these steps:
        1. Classify each command by category:
            - Immediate: to be executed immediately
            - Conditional: to be executed based on current or future vehicle state
            - Continuous: to be executed continuously until stopped
        2. Organize any immediate commands into proper order
        3. Create an ImmediateCommand, ConditionalCommand, or ContinuousCommand object
           for each command, based on its category and documentation
           - CAUTION: Do not duplicate immediate and continuous commands, continuous has priority
           - WARNING: Do not invent new commands, only use the provided command documentation
        4. Return the commands in the provided pydantic schema

    Flight commands to be parsed:
    {flight_commands}

    Command documentation:
    {command_documentation}

    """
    command_list: List[str] = Field(
        ...,
        description="List of strings representing flight commands to be parsed into categories"
    )
    command_documentation: dict[str, dict] = Field(
        ...,
        description="Documentation for available commands, including descriptions and arguments"
    )
    def to_prompt(self) -> str:
        """
        Convert the input to a prompt string for the LLM
        """
        return self.prompt_template.format(
            flight_commands=", ".join(self.command_list),
            command_documentation=json.dumps(self.command_documentation, indent=2)
        )
    
class ImmediateCommand(BaseModel):
    """
    Represents an immediate command to be executed 
    """
    cmd: str = Field(
        ...,
        description= """
        The command to be executed, formatted as a JSON-like string
        e.g. {"cmd": "SetMode", "mode": "LOITER"}
        """
    )

class ConditionalCommand(BaseModel):
    """
    Represents a conditional command to be executed based on vehicle state
    """
    condition: str = Field(
        ...,
        description= """
        The condition under which the command should be executed, rephrased to be clear
        e.g. "When the vehicle is in LOITER mode, set the altitude to 10 meters"
        """
    )

class ContinuousCommand(ImmediateCommand):
    """
    Sub-class of immediate command.
    Represents a continuous command to be executed, and also
    provides optional duration and end condition args.
    Issued commands run at 1 Hz.
    """
    duration: Optional[str] = Field(
        None,
        description= """
        Optional duration for the command to be executed continuously.
        e.g. "for 10 seconds" or "until stopped"
        """
    )
    end_condition: Optional[ConditionalCommand] = Field(
        None,
        description= """
        Optional end condition for the command to be executed continuously.
        e.g. "when the vehicle is in LOITER mode"
        """
    )
    
class ParseCommandsStep_Output(BaseModel):
    """
    Output template for the flight command parser step
    Format each command according to its documentation
    and categorize them into immediate, conditional, and continuous commands.
    """
    immediate_commands: List[ImmediateCommand] 
    conditional_commands: List[ConditionalCommand]
    continuous_commands: List[ContinuousCommand]

# ---- Main Loop ----
while True:

    vehicle_status = get_vehicle_status(vehicle)
    # Get user input
    user_input = input("\nUser: ").strip()
    if user_input.lower() == "exit":
        break
    
    new_input = ParseUserInputStep_Input(
        user_input=user_input
    ).to_prompt()


    MESSAGES.append(
        {"role": "user", "content": new_input}
    )

    llm_speed = {
        "start_time": time.time(),
        "step1": 0.0,
        "step2": 0.0,
        "step3": 0.0,
        "total_time": 0.0,
    }

    response = client.responses.parse(
        model="gpt-4.1-nano",
        input=[
            MESSAGES[0],
            MESSAGES[-1]
        ],
        text_format=ParseUserInputStep_Output,
        temperature=0.0,
    )
        
    parsed_response = ParseUserInputStep_Output.model_validate(response.output_parsed)
    MESSAGES.append(
        {"role": "assistant", "content": parsed_response.model_dump_json(indent=2)}
    )


    # -- Step 1: Classify user input
    print("\n--- Step 1 ---")
    print("Received response from LLM:")
    print(parsed_response.model_dump_json(indent=2))
    print("    --> LLM Response Type:", parsed_response.response_type)

    if parsed_response.response_type == "simple_response":
        # If the response is a simple response, print it
        print("\n        --> LLM (simple response):", parsed_response.simple_response)
        print("    Step 1 complete. No flight commands to parse.")
        print("\n--- End Step 1 ---")

        llm_speed["total_time"] = time.time() - llm_speed["start_time"]
        print("\nLoop time (1 step):", llm_speed)
        continue

    elif parsed_response.response_type == "flight_command":
        print("\n        --> LLM (flight commands):", parsed_response.flight_commands)
        print("    Step 1 complete. Proceeding to step 2 to parse flight commands ---")
        print("\n--- End Step 1 ---")


    # -- Step 2: Parse the flight commands
    print("\n--- Step 2 ---")
    command_input = ParseCommandsStep_Input(
        command_list=parsed_response.flight_commands,
        command_documentation=CmdDocumentation
    ).to_prompt()

    MESSAGES.append(
        {"role": "user", "content": command_input}
    )

    response = client.responses.parse(
        model="gpt-4.1-mini",
        input=[
            MESSAGES[0],
            MESSAGES[-1],
        ],
        text_format=ParseCommandsStep_Output,
        temperature=0.0,
    )

    parsed_commands = ParseCommandsStep_Output.model_validate(response.output_parsed)
    print("\n        --> LLM Parsed Commands:", parsed_commands.model_dump_json(indent=2))
    

    print("\n--- Step 2 complete ---")

    total_time = time.time() - llm_speed["start_time"]
    print("\nLoop time (2 steps):", total_time)

    # -- Step 3: Process the parsed commands
    print("\n--- Step 3 (in work) ---")
    print("Processing parsed commands...")

    if parsed_commands.immediate_commands:
        print("\nExecuting immediate commands:")

        while parsed_commands.immediate_commands:
            cmd = parsed_commands.immediate_commands.pop(0)
            print("    Executing command:", cmd.cmd)

    if parsed_commands.conditional_commands:
        print("\nConditional commands to be executed based on vehicle state:")

        for cmd in parsed_commands.conditional_commands:
            print("    Condition:", cmd.condition)

    if parsed_commands.continuous_commands:
        print("\nContinuous commands to be executed until stopped:")

        for cmd in parsed_commands.continuous_commands:
            print("    Command:", cmd.cmd)

            if cmd.duration:
                print("    Duration:", cmd.duration)
            if cmd.end_condition:
                print("    End condition:", cmd.end_condition.condition)


    print("\nEnd of commands.")
    print("\n--- End Step 3 ---\n")

"""
Draft 2 of ArduPilot LLM Assistant
8/22/2025
by IGSXF
"""

import os
import json
import time
import threading
import openai
import queue
import math
from pathlib import Path
from typing_extensions import List, Literal, TypedDict, Union, Optional
from pydantic import BaseModel, Field
from dronekit import VehicleMode, LocationGlobalRelative, connect


# Input Classifier Components
class InputClassifier(BaseModel):
    """
    Model to classify the type of input received.

    'decision' attribute: Indicates how the input should be handled.

    'simple_response' indicates that the input is a simple user query or
    statement that can be answered with a straightforward response:
        e.g.: greetings, simple questions, or requests for information available from general LLM knowledge
        or from the chat history, or basic vehicle status if basic vehicle params are attached to the input.
        No tasks are generated for this type of input.

    'operational_response' indicates that the input requires operational action or data specific 
    to the flight operations context.
    E.g.:
    - A request for flight status or telemetry data NOT included in the input
    - A command to execute a flight operation or task
    - A request for specific flight-related information that requires processing or action
    - A system-generated message that requires a specific operational response
    - A conditional or scheduled task that is ready for execution

    if the input includes elements of both 'simple_response' and 'operational_response',
    the 'decision' should be 'operational_response' to ensure that the input is processed
    in the context of flight operations and any necessary tasks are generated.

    'no response' indicates that the input does not require any response
    or action. E.g:
    - A system-generated message used for logging
    - A low-priority message that does not require immediate attention
    - A conditional or scheduled task that is not currently actionable

    tasks (optional): 
    If the input requires operational action, generate a list of tasks
    - Split the input content into actionable tasks using concise plain language.
      E.g.:
      - "Check <topic>"
      - "Do <action> on <topic>"
    These tasks do not need to reference any specific functions or methods, just describe the task in minimal words

    Response content:
    - If 'decision' is 'simple_response', the response_content will contain
      a simple answer or acknowledgment.
    - If 'decision' is 'operational_response', the response_content will answer any immediately available
      questions or provide a brief acknowledgment of the operational task, plus "Stand by"
    """

    # input_content: str
    # input_source: Literal["user", "script"]
    decision: Literal['no response', 'simple_response', 'operational_response']
    tasks: List[str] = Field(
        default_factory=list,
        description="List of tasks to be executed based on the input content, in plain language"
    )
    response_content: Optional[str] = Field(
        default=None, description="Content of the response if applicable"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Reason for the decision made, in minimal words, to provide context in later steps. Skip is self-explanatory."
    )

def new_input_step(input_content: str,
                   messages: List[dict],
                   input_timestamp: float,
                   input_source: Literal["user", "script"],
                   messages_limit=5,
                   context: Optional[str] = None,
                   vehicle_state: Optional[dict] = None,
                   model: str = "gpt-4.1-nano") -> InputClassifier:
    """
    Classify the input content and source to determine the appropriate response type.

    Since this step emphasizes speed and efficiency, and punts the actual thinking to the
    next step if necessary, it can reduce the number of messages processed
    to a fixed limit (e.g., developer plus latest 5) to ensure quick response times.

    Args:
        input_content (str): The content of the input to classify.
        input_source (Literal["user", "script"]): The source of the input.
        messages (List[dict]): The list of messages to consider for classification.
        input_timestamp (float): The timestamp of the input.
        messages_limit (int): The maximum number of messages to consider for classification.
        model (str): The LLM model to use for classification.

    Returns:
        InputClassifier: An instance of InputClassifier with the classification result.
    """
    # Maintain the developer message at the start of the messages list
    developer_message = messages[0]
    original_messages = messages[1:]  # Exclude the developer message

    if len(original_messages) > messages_limit:
        used_messages = [developer_message] + original_messages[-messages_limit:]
    else:
        used_messages = [developer_message] + original_messages


    input_header = f"Time(UTC): {round(input_timestamp)} | Input source: {input_source.upper()}:\n"

    if vehicle_state:
        vehicle_info = f"Vehicle state: {json.dumps(vehicle_state, indent=2)}\n"

    input_body = "\n".join([
        f"New input:\n{input_content.strip()}",
        f"Situation context: {context or 'N/A'}",
        f"Vehicle info: {vehicle_info if vehicle_state else 'N/A'}"
    ])

    used_messages.append({"role": 'user', "content": input_header + input_body})

    print(used_messages[-1]["content"])

    # print("Messages used in New InputStep:\n", json.dumps(used_messages, indent=2))

    start_time = time.time()

    result = client.responses.parse(
        model=model,
        input=used_messages,
        temperature=0.0,
        top_p=0.1,
        text_format=InputClassifier,
    )

    response_header = f"{round(time.time())} | New Input Step Response:\n"
    response_content = response_header + result.output_parsed.model_dump_json(indent=2)

    messages.append({"role": "user", "content": input_header + input_body})
    messages.append({"role": "assistant", "content": response_content})

    elapsed = time.time() - start_time

    token_count = result.usage.total_tokens

    return result.output_parsed, messages, elapsed, token_count



# Command Components
command_guidance = """
With the given task, select a command from the predefined set that is best suited to accomplish the task.
Do not invent new commands or modify existing ones. 

If the task cannot be clearly be accomplished by any of the command options below, Reject the command.
This prevents the LLM from stretchig the command to fit the request, which may lead to unexpected behavior.

Available commands:
- "arm_disarm" - for arming or disarming the drone / vehicle

    - params: {"arm": bool} - True to arm, False to disarm
    - example: {"cmd": "arm_disarm", "arm": True}

- "set_mode" - for changing the flight mode of the drone
    * Note: RTL = Return to Launch, aka Land

    params: {"mode": Literal["LOITER", "GUIDED", "AUTO", "RTL", "TAKEOFF"]}
    example: {"cmd": "set_mode", "mode": "LOITER"}

- "set_speed" for adjusting the flight speed

    params: {"speed": float} - speed in m/s
    example: {"cmd": "set_speed", "speed": 15.0}

- "set_altitude" for setting the flight altitude

    params: {"altitude": float} - altitude in meters
    example: {"cmd": "set_altitude", "altitude": 100.0

- "adjust_orbit" for adjusting the orbit radius, direction
    params: {"radius": float, "direction": Literal["clockwise", "counterclockwise"]}
    example: {"cmd": "adjust_orbit", "radius": 50.0, "direction": "clockwise"}

- "go_to_location" for navigating to a specific GPS location

    params: {"ddlat": float, "ddlon": float, "alt": Optional[float]} - GPS coordinates in decimal degrees
    * vehicle will maintain current altitude if not specified
    example: {"cmd": "go_to_location", "ddlat": 37.7749, "ddlon": -122.4194, "alt": 100.0}

Command types:
- "immediate" for immediate execution
- "conditional" for execution based on certain conditions (it is passed into a queue for continuous evaluation)
    - conditions include time, vehicle state, or other criteria
- "continous" for cmd that should be executed immediately, but also run continuously
    in the background until a condition is met or the cmd is no longer needed
-   "rejected" if the command is impossible, overly vague, a duplicate, or seems erroneous

Conditions:
- Use with conditional cmds to specify the criteria for execution
- Use with continuous cmds to specify the criteria for stopping the task.

Reasoning: (Optional)
- In a short sentence or two, explain why you selected this command and type, if not self-explanatory.

Return command in the Command object schema
"""

class Condition(TypedDict):
    """
    Represents a condition for executing a command, attached to Command object as an optional attribute.
    Includes vehicle parameters, time, eta, other measurable data if and only if accessible from messages and vehicle state.
    If the condition can't be monitored by the system given the constraints above, ignore this class and REJECT the command.

    Attributes:
    - description (str): A brief description of the condition with the parameter to monitor, the control value, and the target value.
    - control_value (Union[str, int, float, bool]): The current value of the parameter to monitor.
    - target_value (Union[str, int, float, bool]): The value that the control_value must reach for the condition to be met.
    """
    description: str
    control_value: Union[str, int, float, bool]
    target_value: Union[str, int, float, bool]

class Command(TypedDict):
    """
    Represents a Command to be executed.
    Note: if a command is impossible, overly vague, a duplicate, or seems erroneous, it should be rejected.
        If rejected, the remaining fields in this Command object should be None or empty.
    Attributes:
        task: describes task meant to be accomplished in plain language.
        cmd: Selected predefined command to exec
        cmd_type: ["immediate", "conditional", "continous", "rejected"]
        cmd_keys: List of keys for the cmd parameters.
        cmd_values: List of values for the cmd parameters.
        exec_condition: If conditional or continous, condition(s) that must be met for the cmd to run
        stop_condition: If continous, the condition(s) that must be met for the cmd to stop 
    """
    task: str
    cmd: Optional[Literal[
        "arm_disarm",
        "set_mode",
        "set_speed",
        "set_altitude",
        "adjust_orbit",
        "go_to_location"
    ]]
    cmd_type: Literal[
        "immediate",
        "conditional",
        "continous",
        "rejected"
    ]
    cmd_keys: List[str]
    cmd_values: List[Union[str, int, float, bool]]
    exec_condition: Optional[List[Condition]]
    stop_condition: Optional[List[Condition]]
    reasoning: Optional[str]

class CommandHandler(BaseModel):
    """
    Model to handle tasks generated from the OperationsParser step.
    This generates a list of Command objects based on the parsed input content, if applicable,
    and then returns a simple acknowledgment or a response indicating the status of the commands, if needed.
    """
    cmds: List[Command] = Field(
        default_factory=list,
        description="List of commands to be executed based on the parsed input content"
    )
    response: Optional[str] = Field(
        description="""
         - Response should always be concise and plain language.
        E.g.:
        - '<cmd> done'
        - 'No action needed'
        - '<timestamps> --> human understandble format in minimum format to understand, e.g: 
            - 'Four hours ago', 
            - 'fifteen minutes from now',
            - 'at 3:30 PM UTC'
            - 'just now'
            Unlikely the day of the week or month is needed, but if it is, use the minimum format to understand.
        """
    )

class EvaluatedCommand(TypedDict):
    cmd: str
    eval: Literal["ready", "deferred", "not_ready", "removed"]
    condition: Optional[Condition]
    reason: Optional[str]

class ConditionalEvalOutput(BaseModel):
    evaluated_commands: List[EvaluatedCommand] = Field(
        default_factory=list,
        description="List of commands that have been evaluated based on the current vehicle state and context."
    )

def handle_tasks_step(tasks: list = [],
                      command_guidance: str = command_guidance,
                      model: str = 'gpt-4.1-nano',
                      vehicle_state: dict = None,
                      context: str = None) -> CommandHandler:
    """

    """


    input_content = """
    Handle the tasks generated from the InputClassifier step.

    Match the tasks to available set of predefined commands that the vehicle can execute
    using the following command set and guidelines, as well as the current vehicle state and situational context.
    {command_guidance}

    Tasks:
    {tasks}

    Vehicle state:
    {vehicle_state}

    Situational context:
    {context}

    Return a list of Command objects in the CommandHandler schema.
    """.format(
        command_guidance=command_guidance,
        tasks="\n".join([f"- {task}" for task in tasks]) if tasks else "No tasks to handle.",
        vehicle_state=json.dumps(vehicle_state, indent=2) if vehicle_state else "N/A",
        context=context or "N/A"
    )

    result = client.responses.parse(
        model=model,
        input=input_content,
        temperature=0.0,
        top_p=0.0,
        text_format=CommandHandler,
    )

    return result.output_parsed

def repr_command(command: Command) -> str:
    """    Represent a command as a string for easy reading."""
    # Create dict of cmd k-v pairs
    cmd_params = dict(list(zip(command['cmd_keys'], command['cmd_values'])))

    # Create header and body
    header = f"Command: {command['cmd']} | Type: {command['cmd_type']}"
    if command['cmd_type'] == 'immediate':
        cmd_string = f"{header} | Params: {json.dumps(cmd_params)}"
    elif command['cmd_type'] in ['conditional', 'continous']:
        cmd_string = f"{header} | Params: {json.dumps(cmd_params)}\n\tExec condition: {command['exec_condition']} | Stop condition: {command.get('stop_condition', 'N/A')}"

    return cmd_string

def run_command(command: Command, vehicle) -> None:
    command_params = dict(list(zip(command['cmd_keys'], command['cmd_values'])))
    c = {'cmd': command['cmd']} | command_params

    if c['cmd'] == 'arm_disarm':
        vehicle.armed = c['arm']
        print(f"Vehicle {'armed' if c['arm'] else 'disarmed'}.")

    elif c['cmd'] == 'set_mode':
        vehicle.mode = VehicleMode(c['mode'])
        print(f"Vehicle mode set to {c['mode']}.")

    elif c['cmd'] == 'set_speed':
        vehicle.groundspeed = c['speed']
        print(f"Vehicle speed set to {c['speed']} m/s.")

    elif c['cmd'] == 'set_altitude':
        print("PLACEHOLDER: set_altitude not implemented yet.")
        print(f"Vehicle altitude set to {c['altitude']} m.")

    elif c['cmd'] == 'adjust_orbit':
        print("PLACEHOLDER: adjust_orbit not implemented yet.")
        print(f"Vehicle orbit adjusted to radius {c['radius']} m, direction {c['direction']}.")

    elif c['cmd'] == 'go_to_location':
        vehicle.simple_goto(
            LocationGlobalRelative(c['ddlat'], c['ddlon'], 
                                   c.get('alt', vehicle.location.global_relative_frame.alt)))
        print(f"Vehicle navigating to location: lat={c['ddlat']}, lon={c['ddlon']}, alt={c.get('alt', 'current altitude')} m.")

    else:
        print(f"Unknown command: {c['cmd']}. Cannot execute.")

def eval_conditional_commands(cmds: List[Command],
                              messages: List[dict],
                              context: str,
                              vehicle_state: dict) -> ConditionalEvalOutput:
    """
    Evaluates conditional commands based on the current vehicle state and context.
    """
    prompt_template = """
    Evaluate conditional commands based on the current vehicle state.
    For each command, determine if it is "ready" to be executed, "deferred" for later evaluation,
    "not_ready" if conditions are not met, or "removed" if the command is no longer relevant or valid.
    Provide a brief reason for each evaluation.
    Return the results in a list of EvaluatedCommand objects.

    Commands to evaluate:
    {commands}

    Situational context:
    {context}

    Current vehicle state:
    {vehicle_state}

    """
    commands = [json.dumps(cmd) for cmd in cmds]

    input_messages = [messages[0]]  # Developer message

    input_content = prompt_template.format(commands="\n".join(commands),
                                          context=context,
                                          vehicle_state=json.dumps(vehicle_state, indent=2))
    
    input_messages.append({"role": "user", "content": input_content})

    result = client.responses.parse(
        model="gpt-4.1-nano",
        input=input_messages,
        temperature=0.0,
        top_p=0.0,
        text_format=ConditionalEvalOutput,
    )

    return result.output_parsed


# Summarizer Components
class Summarizer:     
    """
    Summarizer class to maintain an evolving summary of the conversation.
    The delay is used to control how often the summarizer checks for new events.

    use example:

        summarizer = Summarizer()
        summarizer.evolving_summary = "No events to summarize yet."

        ...in the main loop or script, after an LLM or system step...

            summarizer_package = messages[-n:]  # Get the last n (2) messages for summarization 
            summarizer.queue.put(summarizer_package)  # Add new events to the queue for processing

    The Summarizer will run in a separate thread and process the queue
        to update the evolving summary with new events.
    """

    developer_message = (
        "You are a concise AI assistant integrated into a flight operations system. "
        "The system includes a human operator and an AI LLM-based assistant, plus"
        " scripts running in the background that can execute tasks and provide"
        " status updates. Your role is to assist the flow by summarizing the "
        "recent chat history and system messages into a concise paragraph, providing useful"
        " context more efficiently than the full chat history. "
        "You should focus on key points, actions taken, and any important updates."
    )

    def __init__(self, delay=2, model="gpt-4.1-nano"):
        self.delay = delay  # Delay in seconds
        self.model = model
        self.queue = queue.Queue()
        self.overall_summary = None  # A longer summary of the entire session
        self.evolving_summary = None  # A summary that evolves with each new input
        self.usage = {
            "count": 0, "total": 0, "average": 0,"last": 0,
        }
        self.current_status = None  # Current status of the vehicle or operation, in a few words
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while True:
            if not self.queue.empty():
                new_events = self.queue.get()
                if new_events:
                    
                    update_prompt = (
                        "This is a summary of the recent events in the flight operations system:\n\n"
                        f"{self.evolving_summary}\n\n"
                        f"Here are new events that occurred:\n\n{json.dumps(new_events)}\n\n"
                        "If these events are important, update the summary to include them, but,"
                        " this summary must be five or less sentences long. Therefore, the summary"
                        " shoudl evolve with each new input, but not grow indefinitely, as older events"
                        " may become less relevant over time and newer events are more important to provide"
                        " context for the human operator and the AI assistant."
                    )

                    summary_input = [
                        {"role": "system", "content": Summarizer.developer_message},
                        {"role": "user", "content": update_prompt}
                    ]

                    result = client.responses.parse(
                        model=self.model,
                        input=summary_input,
                        temperature=0.0,
                        top_p=0.1,
                        text_format=MessagesSummarizer,
                    )

                    self.evolving_summary = result.output_parsed.summary.strip()
                    self.current_status = result.output_parsed.status.strip() if result.output_parsed.status else None

                    self.usage["last"] = result.usage.total_tokens
                    self.usage["total"] += result.usage.total_tokens
                    self.usage["count"] += 1
                    self.usage["average"] = self.usage["total"] / self.usage["count"]


                    print(f"\nUpdated Evolving Summary:\n{self.evolving_summary}\n")

            time.sleep(2)

    def summarize_messages(self, messages: List[dict]) -> str:
        """
        Summarize the messages in the conversation.

        This function processes the messages and generates a concise summary of the conversation history.
        This function doesn't run in a separate thread is called on demand

        Args:
            messages (List[dict]): The list of messages to summarize.

        Returns:
            str: A concise summary of the conversation history.
        """
        input_content = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])

        result = client.responses.parse(
            model=self.model,
            input=input_content,
            temperature=0.0,
            top_p=0.1,
            text_format=MessagesSummarizer,
        )

        self.overall_summary = result.output_parsed.summary.strip()

class MessagesSummarizer(BaseModel):
    """
    Model to summarize the messages in the conversation.

    This generates a concise summary of the conversation history, focusing on key points and actions taken.
    The summary should be brief and highlight the most important aspects of the conversation.

    Summary should be in plain language, avoiding technical jargon or unnecessary details. Limit to seven sentences unless 
    essential to include more for clarity.
    """
    summary: str = Field(
        description="""
        A concise summary of the conversation history, focusing on key points and actions taken.
        Review user inputs versus assistant responses - Did the assistant understand and respond appropriately?
        Did the state of the vehicle and command script change appropriately? Include this in the summary if 
        appropriate to help reduce hallucinations and reorient the assistant.
        """
    )
    status: Optional[str] = Field(
        default=None,
        description="Vehicle's current operation in as few words as possible",
        examples=["holding position", "in flight", "on ground", "landing", "taking off", "moving to location", "unknown"]
    )


# Dronekit Components
def get_vehicle_state(vehicle, status_text: str = None) -> dict:
    """
    Get the current state of the vehicle.
    This function simulates getting the vehicle state, replace with actual vehicle state retrieval logic.
    """
    return {
        "current_time": round(time.time()),
        "speed": vehicle.groundspeed,
        "mode": vehicle.mode.name,
        "heading": round(vehicle.heading),
        "roll": round(math.degrees(vehicle.attitude.roll)),
        "pitch": round(math.degrees(vehicle.attitude.pitch)),
        "yaw": round(math.degrees(vehicle.attitude.yaw)),
        "location": {
            "lat": vehicle.location.global_relative_frame.lat,
            "lon": vehicle.location.global_relative_frame.lon,
            "alt": vehicle.location.global_relative_frame.alt   
        },
        "armed": vehicle.armed,
        "status": status_text or "N/A",
        "destination": None,
        "eta": None
    }


if __name__ == "__main__":

    # Create vehicle by connecting to the Mission Planner SITL instance
    vehicle = connect('tcp:127.0.0.1:5763', wait_ready=True)
    print("Connected to vehicle")
    time.sleep(0.5)
    
    
    os.environ["OPENAI_API_KEY"] = input("Enter your OpenAI API key: ").strip()

    client = openai.Client()

    flight_developer_message = (
        "You are a flight operations assistant for an ArduPilot drone. "
        "You are ultraconcise and provide only the necessary information. "
        "You assist with flight operations, parsing user and script inputs, "
        "generating scheduled and conditional tasks, and issuing flight "
        "commands when necessary. "
        "If requested information is not available, do not invent it."
    )

    messages = [
        {"role": "developer", "content": flight_developer_message},
    ]

    inputs = 0

    summarizer = Summarizer()  # Run the summarizer in a separate thread, via queue
    summarizer.evolving_summary = "No events to summarize yet."
    

    vehicle_state = get_vehicle_state(vehicle, summarizer.current_status)

    while True:

        new_input = input("Enter new input (or 'exit' to quit): ").strip()

        if not new_input:
            print("Empty input, please try again.")
            continue

        elif new_input.lower() == 'exit':
            print("Exiting...")
            break
        
        # Simulate system messages with 'system:' prefix to input
        elif new_input.lower().startswith("system:"):
            new_input = new_input[7:].strip()
            input_source = "script"

        else:
            input_source = "user"

        
        vehicle_state = get_vehicle_state(vehicle, summarizer.current_status)

        inputs += 1

        classifier_output = new_input_step(
            input_content=new_input,
            messages=messages,
            input_timestamp=time.time(),
            input_source=input_source,
            model="gpt-4.1-mini",
            messages_limit=5,
            context=summarizer.evolving_summary,
            vehicle_state=vehicle_state
        )

        parsed_classifier_output, messages, elapsed, token_count = classifier_output

        print(f"\nNew Input Step Output:\n{parsed_classifier_output.model_dump_json(indent=2)}\n")

    
        summarizer_package = messages[-2:]  # Get the last two messages for summarization
        summarizer.queue.put(summarizer_package)


        if parsed_classifier_output.decision == "operational_response":
            tasks = parsed_classifier_output.tasks

            if tasks:
                print(f"\nTasks to handle: {tasks}\n")

                handle_tasks_output = handle_tasks_step(
                    tasks=tasks,
                    model="gpt-4.1-mini",
                    context=summarizer.evolving_summary,
                    vehicle_state=vehicle_state
                )

                print("\nHandle Tasks Step\n", handle_tasks_output.model_dump_json(indent=2))

                messages.append({"role": "assistant", "content": handle_tasks_output.response})


                if handle_tasks_output.response:
                    print("\nResponse:\n", handle_tasks_output.response)

                if handle_tasks_output.cmds:
                    
                    for c in handle_tasks_output.cmds:
                        
                        print(f"\n{repr_command(c)}\n")
                        
                        if c['cmd_type'] == 'immediate' and c['cmd'] != 'rejected':
                            run_command(c, vehicle)

        summarizer.summarize_messages(messages)
        print(f"\nEvolving Summary:\n{summarizer.evolving_summary}\n")




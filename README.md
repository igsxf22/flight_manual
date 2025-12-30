# flight_manual
LLM Interaction with ArduPilot vehicles via Dronekit

***This is for SITL simulated flights, not real vehicles***

Focus:
  - agentic execution
  - multimodal capabilities
     - voice input, voice output
     - video input (gesture detection)
     - realtime api's
  - minimum latency and max token efficiency
     - logging and mapping value of different options

> Example with MissionPlanner and UnrealEngine:
<img width="602" height="700" alt="image" src="https://github.com/user-attachments/assets/f1e16c9d-de2f-4279-9daf-a81e3e582dd4" />




> You can easily integrate this with my UnrealEngine - Ardupilot project:<br>
> (https://github.com/igsxf22/python_unreal_ardupilot)

## Quick Start
```
with python 3.12.9:
  pip install openai dronekit pymavlink future pyyaml

with mission planner:
  Go to simulation tab on the top left menu
  Click multirotor then stable in pop up

run basic_demo.py
input your openai api key
  (better, add your own method to set os.environ["OPENAI_API_KEY"]

when ready, terminal should display:
  Enter command:

Type your command to the vehicle (See demo limitations note)

Watch vehicle execute command in Mission Planner

Repeat
```

Basic demo limitations:
 - The basic demo is a simple template to use as a starting point
 - This doesn't provide the LLM with current vehicle status and doesn't include chat memory
 - The LLM will only format commands based on the available command classes
 - These classes each have a docstring, describing the purpose and format of the command, which is passed along with user input in the prompt template
 - You can add your command classes and run methods, just add them to the `all_cmds` list on line 276 so their docstring is included in the prompt

More advanced demos are in work.

> **Remember**: Increasing the complexity and length of the prompt will increase latency and token cost

The basic_demo.py script includes a workaround for the error caused when trying to import dronekit in python 3.10+, but you can fix it yourself here [import dronekit fix](#fix-dronekit-import-issue)

## Components

The basic demo uses OpenAI and requires an OpenAI API key
- https://auth.openai.com/create-account

> The demo uses OpenAI and GPT-4o-Mini, but you can use
the Pydantic Command class objects with any models, wrappers,
or APIs that support custom schemas. This includes modern LLMs
trained for structured output generation, such as those capable of
producing responses in JSON or Pydantic-compatible formats.

> Gemini Demo: Get API key at https://aistudio.google.com/api-keys

### Basic Demo Reqs:
* Python (built with 3.12.9)
  * Dronekit
  * Pymavlink
  * OpenAI

* Mission Planner

<br><br>
#### Fix dronekit import issue
* Fix `import dronekit` error: <br>
  `AttributeError: module 'collections' has no attribute 'MutableMapping'`

  A workaround is built into the basic_demo.py script, but you can also edit:

  `./Lib/site-packages/dronekit/__init__.py`<br>

  ```
  On Line 2689: 
    class Parameters(collections.MutableMapping, HasObservers):

  Change to:

    class Parameters(collections.abc.MutableMapping, HasObservers):
  ```
  Or run:
  
  ```python
  from pathlib import Path
  p = Path('Lib\site-packages\dronekit\__init__.py')
  
  data = p.read_text()
  data = data.replace('collections.MutableMapping', 'collections.abc.MutableMapping')
  p.write_text(data)
  
  print("Dronekit __init__.py patched successfully.")
  ```


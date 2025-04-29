# flight_manual
LLM Interaction with ArduPilot vehicles via Dronekit

Project to explore enabling Ardupilot vehicles with realtime LLM assistance

Focus:
  - agentic execution
  - multimodal capabilities
  - minimum latency and max token efficiency

> You can easily integrate this with my UnrealEngine - Ardupilot project:<br>
> (https://github.com/igsxf22/python_unreal_ardupilot)

## Quick Start
```
with python 3.12.9:
  pip install openai dronekit pymavlink

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


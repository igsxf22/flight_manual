# Connect to Unreal Engine 5 Standalone App
The Unreal Engine 5 app has a built-in TCP relay that will connect to a Python script. 

The TCP relay Python script requires only native Python libraries, while the TCP + Dronekit version requires a Dronekit venv.

> [!NOTE]
> This assumes you completed the Getting Started with Windows Mission Planner / Dronekit [Instructions](win_install_dronekit_2026.md)

## Scripts

Open a new cmd terminal, navigate to your dronekit environment and activate it

For example:
  ```
  cd dronekit3
  Scripts\activate.bat
  ```

Inside your dronekit environment dir, create a new python file for the `tcp_relay.py` script
  ```
  edit tcp_relay.py
  ```

Copy and paste into editor, CTRL+S to save, CTRL+Q to return to terminal
  ```python
  """
  tcp_relay.py
  -------------
  This is a simple TCP server that passes data between a Python script and an Unreal Engine 5 Runtime.
  It runs in a separate thread so communication is not affected by the main script or UE execution time.
  The Unreal Engine 5 standalone .exe will automatically handle connect/disconnect actions from this script
  """

  import socket
  import time
  import threading
  
  def create_tcp_host(host="127.0.0.1", port=1234, listen=1):
      server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      server_socket.bind((host, port))
      server_socket.listen(listen)
      print(f"Listening on {host}:{port}")
      return server_socket
  
  def create_fields_string(fields_list):
      """
      This function places values into a string we'll decode with the blueprints in the customized Unreal TCP actor.
      Then, the values are relayed to an Unreal Engine actor via a blueprint interface and used to update the actor's properties.
  
      Creates a string of fields separated by spaces.
      :param fields_list: List of fields to be included in the string.
      :return: String of fields separated by spaces.
      """
      field_str = "{} " * len(fields_list)
      return field_str.format(*fields_list).rstrip()
  
  class TCP_Relay:
      """
      TCP_Relay is a class that sets up a TCP server to relay data between Unreal Engine and a Python script.
      
      Attributes:
          server_socket (socket.socket): The server socket that listens for incoming connections.
          num_fields (int): The number of fields in the message string.
          message (str): The message string to be sent to Unreal Engine.
          linked (bool): A flag indicating whether a client is connected.
          message_in (bytes): The latest message received from the client.
          client_socket (socket.socket): The client socket connected to the server.
          thread (threading.Thread): The thread running the sender method.
      """
      def __init__(self, num_fields=23, host="127.0.0.1", port=1234, size=1024):
          self.server_socket = create_tcp_host(host, port)
          self.num_fields = num_fields
          self.size = size
          self.message = create_fields_string([0.] * self.num_fields)
          self.linked = False
          self.message_in = None
          self.client_socket = None
          self.thread = threading.Thread(target=self._server)
          self.thread.daemon = True
          self.thread.start()
  
      def _server(self):
          while True:
              while self.linked:
                  try:
                      self.message_in = self.client_socket.recv(self.size)
                  except socket.error as e:
                      print(f"Receive error: {e}")
                      self.message_in = None
  
                  try:
                      self.client_socket.send(str.encode(self.message))
                  except socket.error as e:
                      print(f"Send error: {e}")
                      print("Disconnected.")
                      self.client_socket.close()
                      self.linked = False
                      self.client_socket = None
  
              if not self.linked:
                  try:
                      self.client_socket, client_address = self.server_socket.accept()
                      print("Connected. Client address:", client_address)
                      self.linked = True
                  except socket.error as e:
                      print(f"Accept error: {e}")
  
              time.sleep(0.002)
  
  # Test connection with UE5 standalone app by running as main
  # ie in cmd terminal, in activated venv, run: `python tcp_relay.py`
  # Will perform arbitrary movements to confirm connection to game actor
  if __name__ == "__main__":
  
      relay = TCP_Relay()
  
      x, y, z = 0., 0., 0.
      roll, pitch, yaw = 0., 0., 0.
  
      fields = [0.] * relay.num_fields
      fields[:6] = [x, y, z, roll, pitch, yaw]  # Example values
  
      while True:
  
          x, y, z = [(i + 10.0) for i in [x, y, z]]
          roll, pitch, yaw = [(i + 1.0) for i in [roll, pitch, yaw]]
          fields[:6] = [x, y, z, roll, pitch, yaw]

          relay.message = create_fields_string(fields)  # Example message
          print("Message Out:", relay.message)
  
          if relay.message_in:
              print("Message in:", relay.message_in)
          else:
              print("No message received.")
  
          time.sleep(1)
  ```

Create new `dronekit_unreal.py` script to link vehicle to Unreal Engine actor (ie first person camera / 'player') in game
  ```
  edit dronekit_unreal.py
  ```

Copy and paste into editor, CTRL+S to save, CTRL+Q to return to terminal
  ```python
  """
  SITL Dronekit to Unreal Engine - Basic Example
  This script connects to a SITL instance using Dronekit and sends vehicle data to Unreal Engine using a TCP relay.
  The basic example is configured to match the bp_pythonPawn example in the Unreal Engine project: 
      https://github.com/igsxf22/python_unreal_relay
  """
  # Fix for the error: AttributeError: module 'collections' has no attribute 'MutableMapping'
  try:
    from dronekit import connect, VehicleMode, Vehicle, LocationGlobalRelative
  except Exception as e:
    print("Applying run-time fix for Dronekit collections deprecation")
    from collections import abc
    import collections
    collections.MutableMapping = abc.MutableMapping
  
  import time
  import math
  
  from dronekit import connect, VehicleMode, Vehicle, LocationGlobalRelative
  
  import tcp_relay

  def vehicle_to_unreal(vehicle, z_invert=True, scale=100):
      """
      Converts vehicle data to a dictionary and formats it for Unreal Engine.
      :param vehicle: The vehicle object from dronekit.
      :param z_invert: Invert the Z axis for local frame (default is True because Ardupilot uses NED).
      :param scale: The scale of the Unreal Engine world (default is 100, UE uses cm).
      """
      d = {}
      d["lat"] = vehicle.location.global_frame.lat
      d["lon"] = vehicle.location.global_frame.lon
      d["alt"] = vehicle.location.global_frame.alt
      d["n"] = vehicle.location.local_frame.north * scale
      d["e"] = vehicle.location.local_frame.east * scale
      d["d"] = vehicle.location.local_frame.down * scale
      if z_invert:
          d["d"] *= -1
      d["roll"] = vehicle.attitude.roll
      d["pitch"] = vehicle.attitude.pitch
      d["yaw"] = vehicle.attitude.yaw
  
      # Round based on required precision
      for k,v in d.items():
          if type(v) == float:
              if k in ["lat", "lon", "alt"]:
                  d[k] = round(v, 8)
              elif k in ["n", "e", "d"]:
                  d[k] = round(v, 3)
              elif k in ["roll", "pitch", "yaw"]:
                  d[k] = round(math.degrees(v), 3)
  
      return d
  
  # def create_servo_listener(self, name, message):
  #     # Create DroneKit listener for SERVO_OUTPUT_RAW messages
  #     for i in range(1, 9):
  #         key = f'servo{i}_raw'
  #         channel = getattr(message, key)
  #         self.channels_out[i] = channel
  
  if __name__ == "__main__":
      # Connect to the vehicle
      connection_string = 'tcp:127.0.0.1:5763'
      vehicle = connect(connection_string, wait_ready=True, baud=57600, rate=60)
      print("Vehicle Connected.")
  
      
      while not vehicle.location.local_frame.north:
          time.sleep(1)
          print("Waiting for location local_frame to be available...")
      print("Location local_frame is now available.")
  
      relay = tcp_relay.TCP_Relay()
  
      while True:
  
          # Send vehicle data to Unreal Engine
          data = vehicle_to_unreal(vehicle)
  
          # Create a blank list of fields
          fields = [0.] * relay.num_fields
  
          # Set location and rotation fields with vehicle local frame and attitude data
          fields[0] = data["n"]
          fields[1] = data["e"]
          fields[2] = data["d"]
          fields[3] = data["roll"]
          fields[4] = data["pitch"]
          fields[5] = data["yaw"]
  
          fields[6] = 0.0 # Mount0 roll
          fields[7] = 0.0 # Mount0 pitch
          fields[8] = 0.0 # Mount0 yaw
  
          fields[9] = 0.0 # Mount1 roll
          fields[10] = 0.0 # Mount1 pitch
          fields[11] = 0.0 # Mount1 yaw
  
          fields[12] = 0 # Camera index (0=Mount0, 1=Mount1)
          fields[13] = 80.0 # Camera FOV
  
          # Update the relay message with from the fields, relay will send this to Unreal Engine in its thread
          relay.message = tcp_relay.create_fields_string(fields)
          
          time.sleep(1/60)
  ```

## Run
1. Open Mission Planner and start a SITL instance
2. In activated dronekit venv with the scripts saved above:
   
   ```
   python dronekit_unreal.py
   ```
4. Launch the standalone unreal .exe (probably called `devtest.exe` right now)
5. Issue commands in Mission Planner Guided (Arm, Takeoff, Move to location), in-game first person camera should match camera location, orientation.

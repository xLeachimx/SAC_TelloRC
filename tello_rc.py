# File: tello_rc.py
# Author: Michael Huelsman
# Copyright: Dr. Michael Andrew Huelsman 2023
# License: GNU GPLv3
# Created On: 07 Feb 2024
# Purpose:
# Notes:

# File: tello_rc.py
# Author: Michael Huelsman
# Copyright: Dr. Michael Andrew Huelsman 2023
# License: GNU GPLv3
# Created On: 29 Jun 2023
# Purpose:
#   A class for handling a tello drone using keyboard/controller controls.
# Notes:

from threading import Thread
from socket import socket, AF_INET, SOCK_DGRAM
from time import perf_counter, sleep
from rc_controls import RemoteControl

class TelloRC:
  # Precond:
  #   None.
  #
  # Postcond:
  #   Sets up the required steps for controlling a Tello drone.
  def __init__(self):
    # Addresses
    self.local_addr = ('', 8889)
    self.tello_addr = ('192.168.10.1', 8889)

    # Setup channels
    self.send_channel = socket(AF_INET, SOCK_DGRAM)
    self.send_channel.bind(self.local_addr)

    # Basic accounting variables
    self.flying = False
    self.active = False
    self.connected = False
    self.rc_freq = 30
    self.cmd_log = []
    self.MAX_TIMEOUT = 5

    # Threads
    self.send_thread = Thread(target=self.__send_rc)
    self.receive_thread = Thread(target=self.__receive)

  # Precond:
  #   None.
  #
  # Postcond:
  #   Attempts (up to 5 times) to connect to the Tello drone and start all needed threads.
  #   Returns True if connection was made.
  def connect(self):
    if not self.__connect():
      print("Problem connecting to drone.")
      return False
    self.active = True
    # Starting needed threads
    self.receive_thread.start()
    return True

  # Precond:
  #   None
  #
  # Postcond:
  #   Main flying loop.
  def fly(self):
    if not self.connected:
      if not self.connect():
        print("Failure to connect")
        return
    running = True
    control = RemoteControl()
    run_timer = perf_counter()
    frame_delta = 1/30
    while running:
      delta = perf_counter() - run_timer
      if delta >= frame_delta:
        control.update(frame_delta) #make sure we don't spike anything
        self.__send_rc(control.get_rc())
        action = control.next_action()
        if action is not None:
          match action:
            case "TAKEOFF":
              if not self.flying:
                self.__send_cmd("takeoff")
              else:
                self.__send_cmd("land")
              self.flying = not self.flying
            case "STOP":
              running = False
            case _:
              print("Unknown action:", action)
    self.shutdown()


  # Precond:
  #   None.
  #
  # Postcond:
  #   Stops the connection and lands (if needed) the drone.
  def shutdown(self):
    if self.connected:
      if self.flying:
        self.__send_cmd("land")
      self.active = False
      sleep(1)
      self.receive_thread.join()


  # Precond:
  #   attempts is the number of times to try and connect.
  #
  # Postcond:
  #   Checks connection to the drone by sending a message to
  #     switch the drone into SDK mode.
  #   Returns true if the connection was made.
  #   Returns false if there was a problem connecting and attempts were
  #       exceeded.
  def __connect(self, attempts=5):
    for _ in range(attempts):
      res = self.__send_cmd("command")
      if res is not None and res == 'ok':
        self.connected = True
        return True
    return False



  # Precond:
  #   rc_val is a valid 4 element integer list with each value between -100 and 100
  #
  # Postcond:
  #   Sends the provided rc_values to the drone.
  def __send_rc(self, rc_val: [int, int, int, int]):
    rc_str = "rc " + " ".join(list(map(str, rc_val)))
    self.__send_nowait(rc_str)

  # Precond:
  #   msg is a string containing the message to send.
  #
  # Postcond:
  #   Sends the given message to the Tello.
  #   Returns the response string if the message was received.
  #   Returns None if the message failed.
  def __send_cmd(self, msg: str):
    self.cmd_log.append([msg, None])
    self.send_channel.sendto(msg.encode('utf-8'), self.tello_addr)
    # Response wait loop
    start = perf_counter()
    while self.cmd_log[-1][1] is None:
      if (perf_counter() - start) > self.MAX_TIMEOUT:
        self.cmd_log[-1][1] = "TIMED OUT"
        return None
    return self.cmd_log[-1][1]

  # Precond:
  #   msg is a string containing the message to send.
  #
  # Postcond:
  #   Sends the given message to the Tello.
  #   Does not wait for a response.
  #   Used (internally) only for sending the emergency signal or rc values.
  def __send_nowait(self, msg):
    self.send_channel.sendto(msg.encode('utf-8'), self.tello_addr)
    return None

  # Precond:
  #   None.
  #
  # Postcond:
  #   Receives messages from the Tello and logs them.
  def __receive(self):
    while self.active:
      try:
        response, ip = self.send_channel.recvfrom(1024)
        response = response.decode('utf-8')
        self.cmd_log[-1][1] = response.strip()
      except OSError as exc:
        if self.active:
          print("Caught exception socket.error : %s" % exc)
      except UnicodeDecodeError as dec:
        if self.active:
          self.cmd_log[-1][1] = "Decode Error"
          print("Caught exception Unicode 0xcc error.")

if __name__ == "__main__":
  drone = TelloRC()
  drone.fly()
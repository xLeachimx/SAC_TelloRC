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
import pygame as pg
import cv2 as cv
from datetime import datetime
import random

class TelloRC:
  # Precond:
  #   None.
  #
  # Postcond:
  #   Sets up the required steps for controlling a Tello drone.
  def __init__(self):
    # Addresses
    self.tello_addr = '192.168.10.1'
    self.cmd_port = 8889
    self.state_port = 8890
    self.video_port = 11111

    # Setup channels
    self.send_channel = socket(AF_INET, SOCK_DGRAM)
    self.send_channel.bind(('', self.cmd_port))

    self.state_channel = socket(AF_INET, SOCK_DGRAM)
    self.state_channel.bind(('', self.state_port))

    # Video setup
    self.video_connect_str = 'udp://' + self.tello_addr + ":" + str(self.video_port)
    self.video_stream = None
    self.video_thread = Thread(target=self.__receive_video)
    self.video_thread.daemon = True
    self.last_frame = None
    self.stream_active = False
    self.frame_width = 0
    self.frame_height = 0

    # Basic accounting variables
    self.flying = False
    self.active = False
    self.connected = False
    self.rc_freq = 30
    self.cmd_log = []
    self.last_state = None
    self.MAX_TIMEOUT = 5

    # Threads
    self.send_thread = Thread(target=self.__send_rc)
    self.send_thread.daemon = True
    self.receive_thread = Thread(target=self.__receive)
    self.receive_thread.daemon = True
    self.state_thread = Thread(target=self.__receive_state)
    self.state_thread.daemon = True

  # Precond:
  #   None.
  #
  # Postcond:
  #   Attempts (up to 5 times) to connect to the Tello drone and start all needed threads.
  #   Returns True if connection was made.
  def connect(self):
    self.active = True
    # Starting needed threads
    self.receive_thread.start()
    if not self.__connect():
      print("Problem connecting to drone.")
      return False
    self.video_start()
    self.state_thread.start()
    return True

  # Precond:
  #   None.
  #
  # Postcond:
  #   Starts the state receiving thread.
  def video_start(self):
    # Set up the video stream
    self.stream_active = True
    self.video_stream = cv.VideoCapture(self.video_connect_str, cv.CAP_ANY)
    self.frame_width = self.video_stream.get(cv.CAP_PROP_FRAME_WIDTH)
    self.frame_height = self.video_stream.get(cv.CAP_PROP_FRAME_HEIGHT)
    self.video_thread.start()

  # Precond:
  #   None.
  #
  # Postcond:
  #   Returns the last grabbed video frame.
  def get_frame(self):
    return self.last_frame

  # Precond:
  #   None.
  #
  # Postcond:
  #   Returns the last received state as a dictionary.
  def get_state(self):
    return self.last_state

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
    print("Connected")
    control = RemoteControl()
    run_timer = perf_counter()
    frame_delta = 1/30
    # Helpful text
    font = pg.font.SysFont(pg.font.get_default_font(), 48)
    takeoff_txt = font.render("TAKING OFF", True, (255, 255, 255), (0, 0, 0))
    landing_txt = font.render("LANDING", True, (255, 255, 255), (0, 0, 0))
    pic_txt = font.render("TAKING PICTURE", True, (255, 255, 255), (0, 0, 0))
    stop_txt = font.render("SHUTTING DOWN", True, (255, 255, 255), (0, 0, 0))
    # Setup screen
    if not pg.get_init():
      pg.init()
    screen = pg.display.set_mode((1280, 720))
    while running:
      delta = perf_counter() - run_timer
      if delta >= frame_delta:
        control.update(frame_delta) #make sure we don't spike anything
        self.__send_rc(control.get_rc())
        action = control.next_action()
        # Draw last frame grabbed
        screen.fill((200, 200, 200))
        if self.last_frame is not None:
          screen.blit(pg.image.frombuffer(self.last_frame.tobytes(), self.last_frame.shape[1::-1], "BGR"), (0, 0))
        # Check state and render battery life
        if self.last_state is not None:
          percentage = int(self.last_state['bat'])
          # Draw bounding boxes
          pg.draw.rect(screen, (255, 255, 255), (0, 0, 108, 58))
          pg.draw.rect(screen, (0, 0, 0), (2, 2, 104, 54))
          pg.draw.rect(screen, (0, 200, 0), (4, 4, percentage, 50))
        if action is not None:
          match action:
            case "TAKEOFF":
              if not self.flying:
                center_x = (screen.get_width() - takeoff_txt.get_width())//2
                center_y = (screen.get_height() - takeoff_txt.get_height())//2
                screen.blit(takeoff_txt, (center_x, center_y))
              else:
                center_x = (screen.get_width() - landing_txt.get_width())//2
                center_y = (screen.get_height() - landing_txt.get_height())//2
                screen.blit(landing_txt, (center_x, center_y))
            case "PICTURE":
              center_x = (screen.get_width() - pic_txt.get_width())//2
              center_y = (screen.get_height() - pic_txt.get_height())//2
              screen.blit(pic_txt, (center_x, center_y))
            case "STOP":
              center_x = (screen.get_width() - stop_txt.get_width())//2
              center_y = (screen.get_height() - stop_txt.get_height())//2
              screen.blit(stop_txt, (center_x, center_y))
            case _:
              pass
        pg.display.flip()
        if action is not None:
          match action:
            case "TAKEOFF":
              if not self.flying:
                self.__send_cmd("takeoff")
              else:
                self.__send_cmd("land")
              self.flying = not self.flying
            case "PICTURE":
              date = datetime.today().strftime("%b-%d-%y")
              filename = "pic_" + date + f"-{random.randint(1,10**6)}.jpg"
              cv.imwrite(filename, self.last_frame)
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
      self.stream_active = False
      self.send_channel.close()
      self.last_frame = None
      sleep(1)
      self.receive_thread.join()
      self.video_thread.join()
      pg.quit()


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
        self.__send_cmd("streamon")
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
    self.send_channel.sendto(msg.encode('utf-8'), (self.tello_addr, self.cmd_port))
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
    self.send_channel.sendto(msg.encode('utf-8'), (self.tello_addr, self.cmd_port))
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
      except UnicodeDecodeError as _:
        if self.active:
          self.cmd_log[-1][1] = "Decode Error"
          print("Caught exception Unicode 0xcc error.")

  # Precond:
  #   None.
  #
  # Postcond:
  #   Receives video messages from the Tello.
  def __receive_video(self):
    while self.stream_active:
      ret, img = self.video_stream.read()
      if ret:
        self.last_frame = img
    self.video_stream.release()

  # Precond:
  #   None.
  #
  # Postcond:
  #   Receives state information from the Tello and logs it.
  def __receive_state(self):
    while self.active:
      try:
        response, ip = self.state_channel.recvfrom(1024)
        response = response.decode('utf-8')
        response = response.strip()
        vals = response.split(';')
        state = {}
        for item in vals:
            if item == '':
                continue
            label, val = item.split(':')
            state[label] = val
        self.last_state = state
      except OSError as exc:
        if self.active:
          print("Caught exception socket.error : %s" % exc)
      except UnicodeDecodeError as _:
        if self.active:
          self.cmd_log[-1][1] = "Decode Error"
          print("Caught exception Unicode 0xcc error.")

if __name__ == "__main__":
  drone = TelloRC()
  drone.fly()
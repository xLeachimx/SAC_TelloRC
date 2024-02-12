# File: rc_controls.py
# Author: Michael Huelsman
# Copyright: Dr. Michael Andrew Huelsman 2023
# License: GNU GPLv3
# Created On: 07 Feb 2024
# Purpose:
#   A class for managing input from both the keyboard and a controller.
# Supported Controllers:
#     Xbox series X
#     Playstation 4 (untested)
# Notes:
#
# Xbox series X button and stick map
#   Btn Num | Controller Btn
#      0    |      A
#      1    |      B
#      2    |      X
#      3    |      Y
#      4    |    View
#      5    |    Xbox
#      6    |    Menu
#      7    | LStick Click
#      8    | RStick Click
#      9    | Left   Bumper
#     10    | Right  Bumper
#     11    | DPad   Up
#     12    | DPad   Down
#     13    | DPad   Left
#     14    | DPad   Right
#     15    |     Share
# ===============================
#  Axis Num | Controls
#      0    | LStick Horizontal
#      1    | LStick Vertical
#      2    | RStick Horizontal
#      3    | RStick Vertical
#      4    | Left   Trigger
#      5    | Right  Trigger

import pygame as pg
from math import log
from time import perf_counter
from datetime import datetime

# Important constants
_BUTTON = 0
_AXIS = 1
_X_IDX = 0
_Z_IDX = 1
_Y_IDX = 2
_R_IDX = 3


_Xbox_Map = {
  "Type": _AXIS,
  "X": 2,
  "Y": 1,
  "Z": 3,
  "RL": 4,
  "RR": 5,
  "R": 0
}

_Xbox_FPS_Map = {
  "Type": _AXIS,
  "X": 0,
  "Y": 3,
  "Z": 1,
  "RL": 4,
  "RR": 5,
  "R": 2
}

_Xbox_Action = {
  6: "TAKEOFF",
  15: "PICTURE",
  1: "STOP"
}

_Keyboard_Map = {
  "Type": _BUTTON,
  "XM": pg.K_a,
  "XP": pg.K_d,
  "YM": pg.K_DOWN,
  "YP": pg.K_UP,
  "ZP": pg.K_w,
  "ZM": pg.K_s,
  "RL": pg.K_q,
  "RR": pg.K_e
}

_KEYMAP_EXPAND = {
  "Type": "Button",
  "XM": "Move Left",
  "XP": "Move Right",
  "YM": "Move Down",
  "YP": "Move Up",
  "ZP": "Move Forward",
  "ZM": "Move Backward",
  "RL": "Rotate Left (counter clockwise)",
  "RR": "Rotate Right (clockwise)",
  "X" : "Left/Right Axis",
  "Y" : "Up/Down Axis",
  "Z" : "Forward/Backward Axis",
}

_Keyboard_Actions = {
  pg.K_SPACE: "TAKEOFF",
  pg.K_p: "PICTURE",
  pg.K_ESCAPE: "STOP"
}

def _dz_axis_clamp(d_zone: float, val: float, positive: bool=False):
  if positive:
    val = val + 1
  if d_zone < abs(val) < d_zone:
    return 0.0
  return val

class RemoteControl:
  # Precond:
  #   aggression is a value which indicates how aggressively the rc value accelerate.
  #   acc_time is a value indicating the amount of time before a held value reaches it's maximum.
  #
  # Postcond:
  #   Creates a new class for handling remote control of a TelloDrone
  def __init__(self, aggression=2, acc_time=10):
    if not pg.get_init():
      pg.init()
    self.aggression = max(2, aggression)
    self.acc_time = max(1, acc_time)
    self.mode = "keyboard"
    self.map = _Keyboard_Map
    self.action_map = _Keyboard_Actions
    self.stick = None
    self.held_map = {
      "XM": 0.0,
      "XP": 0.0,
      "YM": 0.0,
      "YP": 0.0,
      "ZP": 0.0,
      "ZM": 0.0,
      "RL": 0.0,
      "RR": 0.0
    }
    self.__current_rc = [0, 0, 0, 0]
    self.__action_q = []

  # Precond:
  #   delta is the amount of time (in seconds) since the last call to get_rc.
  #
  # Postcond:
  #   Ppdates both the action queue and the rc values.
  def update(self, delta: float):
    # Check controller change events
    # Also real poor management of controllers (> 1 might break system)
    for event in pg.event.get([pg.JOYDEVICEADDED, pg.JOYDEVICEREMOVED]):
      if event.type == pg.JOYDEVICEADDED and self.mode == "keyboard":
        self.mode = "joystick"
        self.stick = pg.joystick.Joystick(0)
        if not self.stick.get_init():
          self.stick.init()
        self.map = _Xbox_FPS_Map
        self.action_map = _Xbox_Action
      elif event.type == pg.JOYDEVICEREMOVED and self.mode == "joystick":
        self.mode = "keyboard"
        self.map = _Keyboard_Map
        self.action_map = _Keyboard_Actions
        self.held_map = {
          "XM": 0.0,
          "XP": 0.0,
          "YM": 0.0,
          "YP": 0.0,
          "ZP": 0.0,
          "ZM": 0.0,
          "RL": 0.0,
          "RR": 0.0
        }
    self.__compute_rc(delta)
    self.__detect_actions()

  # Precond:
  #   delta is the amount of time (in seconds) since the last call to get_rc.
  #
  # Postcond:
  #   Returns an array of values between -100 and 100 representing the RC values
  #   to send to the Tello
  def get_rc(self):
    return self.__current_rc

  # Precond:
  #   None.
  #
  # Postcond:
  #   Returns the next action in the queue.
  #   Returns None if there is no action in the queue.
  def next_action(self):
    if len(self.__action_q) == 0:
      return None
    return self.__action_q.pop(0)

  # Precond:
  #   None.
  #
  # Postcond:
  #   Uses the Pygame event system to determine if buttons have been pressed to perform actions.
  def __detect_actions(self):
    for event in pg.event.get([pg.JOYBUTTONDOWN, pg.KEYDOWN]):
      if self.mode == "joystick" and event.type == pg.JOYBUTTONDOWN:
        if event.button in self.action_map:
          self.__action_q.append(self.action_map[event.button])
      elif self.mode == "keyboard" and event.type == pg.KEYDOWN:
        if event.key in self.action_map:
          self.__action_q.append(self.action_map[event.key])

  # Precond:
  #   delta is the amount of time (in seconds) since the last call to __compute_rc.
  #
  # Postcond:
  #   Computes the current rc values based on key/controller inputs.
  def __compute_rc(self, delta):
    # Init the rc state
    rc_state = [0, 0, 0, 0]
    if self.map["Type"] == _BUTTON:
      # Decrease held button counts
      for key in self.held_map:
        if pg.key.get_pressed()[self.map[key]]:
          self.held_map[key] += delta
        else:
          self.held_map[key] = 0 #max(0.0, (self.held_map[key] - 2*delta))
        rc_state[_X_IDX] = self.__btn_acc_curve(self.held_map["XP"]) - self.__btn_acc_curve(self.held_map["XM"])
        rc_state[_Y_IDX] = self.__btn_acc_curve(self.held_map["YP"]) - self.__btn_acc_curve(self.held_map["YM"])
        rc_state[_Z_IDX] = self.__btn_acc_curve(self.held_map["ZP"]) - self.__btn_acc_curve(self.held_map["ZM"])
        rc_state[_R_IDX] = self.__btn_acc_curve(self.held_map["RR"]) - self.__btn_acc_curve(self.held_map["RL"])
    elif self.map["Type"] == _AXIS:
      rc_state[_X_IDX] = _dz_axis_clamp(0.3, self.stick.get_axis(self.map["X"]))
      rc_state[_Y_IDX] = -_dz_axis_clamp(0.3, self.stick.get_axis(self.map["Y"]))
      rc_state[_Z_IDX] = -_dz_axis_clamp(0.3, self.stick.get_axis(self.map["Z"]))
      if "R" in self.map:
        rc_state[_R_IDX] = _dz_axis_clamp(0.3, self.stick.get_axis(self.map["R"]))
      else:
        rr_val = (1 + self.stick.get_axis(self.map["RR"]))/2
        rl_val = (1 + self.stick.get_axis(self.map["RL"]))/2
        rc_state[_R_IDX] = (rr_val - rl_val)
    # Align the rc_state with api expectations
    for i in range(len(rc_state)):
      rc_state[i] = max(-100, min(100, int(100 * rc_state[i])))
    self.__current_rc = rc_state

  # Precond:
  #   t is the number of seconds a button has been held.
  #
  # Postcond:
  #   Returns a number between 0 and 1 indicating the current speed associated with the acc curve.
  def __btn_acc_curve(self, t):
    # Clamp the time
    t = max(0, min(t, self.acc_time)) / self.acc_time
    return self.__acc_curve(t)


  # Precond:
  #   t is a value between 0 and 1
  #
  # Postcond:
  #   Returns a number between 0 and 1 indicating the current speed associated with the acc curve.
  def __acc_curve(self, t):
    neg = -1 if t < 0 else 1
    t = abs(t)
    t = max(0.0, min(1.0, t))
    t = ((self.aggression - 1) * t) + 1
    return neg * log(t, self.aggression)


def _main():
  # Output the button map
  print("Keyboard Control Scheme")
  for item in _Keyboard_Map:
    key_name = pg.key.name(_Keyboard_Map[item])
    if key_name:
      print(pg.key.name(_Keyboard_Map[item]), "->", _KEYMAP_EXPAND[item])
    else:
      print(item, "->", _KEYMAP_EXPAND[item])
  for item in _Keyboard_Actions:
    key_name = pg.key.name(item)
    if key_name:
      print(key_name, "->", _Keyboard_Actions[item])
  print(datetime.today().strftime("%b-%d-%y"))
  # Test the controls
  pg.init()
  screen = pg.display.set_mode((500, 250))
  font = pg.font.SysFont(pg.font.get_default_font(), 48)
  padding = 20
  fps = 30
  frame_delta = 1/fps
  x_text = font.render("X:", True, (255,255,255))
  y_text = font.render("Y:", True, (255,255,255))
  z_text = font.render("Z:", True, (255,255,255))
  r_text = font.render("R:", True, (255,255,255))
  pos_color = (0, 200, 0)
  neg_color = (200, 0, 0)
  # Setup controller
  controller = RemoteControl(10, 2)
  running = True
  start = perf_counter()
  while running:
    delta = perf_counter() - start
    if delta >= frame_delta:
      start = perf_counter()
      controller.update(frame_delta)
      screen.fill((0, 0, 0))
      for event in pg.event.get(pg.QUIT):
        running = False
      rc_data = controller.get_rc()
      # Display active x value
      vert_pos = padding
      horz_pos = 2 * padding + x_text.get_width()
      screen.blit(x_text, (padding, vert_pos))
      color = pos_color
      if rc_data[_X_IDX] < 0:
        color = neg_color
      pg.draw.rect(screen, color, (horz_pos, vert_pos, abs(rc_data[_X_IDX]), x_text.get_height()))

      # Display active y value
      vert_pos += x_text.get_height() + padding
      horz_pos = 2 * padding + y_text.get_width()
      screen.blit(y_text, (padding, vert_pos))
      color = pos_color
      if rc_data[_Y_IDX] < 0:
        color = neg_color
      pg.draw.rect(screen, color, (horz_pos, vert_pos, abs(rc_data[_Y_IDX]), y_text.get_height()))

      # Display active z value
      vert_pos += y_text.get_height() + padding
      horz_pos = 2 * padding + z_text.get_width()
      screen.blit(z_text, (padding, vert_pos))
      color = pos_color
      if rc_data[_Z_IDX] < 0:
        color = neg_color
      pg.draw.rect(screen, color, (horz_pos, vert_pos, abs(rc_data[_Z_IDX]), z_text.get_height()))

      # Display active r value
      vert_pos += z_text.get_height() + padding
      horz_pos = 2 * padding + x_text.get_width()
      screen.blit(r_text, (padding, vert_pos))
      color = pos_color
      if rc_data[_R_IDX] < 0:
        color = neg_color
      pg.draw.rect(screen, color, (horz_pos, vert_pos, abs(rc_data[_R_IDX]), r_text.get_height()))

      pg.display.flip()

      action = controller.next_action()
      if action is not None:
        print(action)

  pg.quit()


if __name__ == "__main__":
  _main()

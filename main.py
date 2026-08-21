# Part of the code was taken from https://pysdl2.readthedocs.io/en/0.9.13/modules/sdl2.html and from claude
import ctypes
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
from collections import deque
from functools import reduce

import sdl2.ext
from input_handling.InputReader import InputReader
from sdl2 import *
from sdl2.sdlttf import *

sdl_epoch_monotonic = None
log_fp = None

reader = InputReader("sf6", character="Ryu")

OVERLAY_MAX_LINES = 12
# overlay_lines: deque[str] = deque(maxlen=OVERLAY_MAX_LINES)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(
    SCRIPT_DIR, "font", "CascadiaCode-VariableFont_wght.ttf"
).encode("utf-8")
FONT_SIZE = 16
font = None
GAMECONTROLLERDB_PATH = os.path.join(SCRIPT_DIR, "data", "gamecontrollerdb.txt").encode(
    "utf-8"
)

DEVICE_PROFILES = {
    "gp2040": "digital_stick",
    "hit box": "digital_stick",
    "hitbox": "digital_stick",
    "haute": "digital_stick",
    "brook": "digital_stick",  # many Brook fight-stick boards behave similarly
    "xinput": "digital_stick",  # GP2040-CE in XInput mode often reports as this
}
DEFAULT_PROFILE = "digital_stick"

RAW_ANALOG_DEADZONE = 3000  # ignore drift within this range of center for real sticks
DIGITAL_STICK_THRESHOLD = 8000  # deflection needed to register as a discrete direction

controller_profiles: dict[int, str] = {}
last_quantized_axis = {}
controller_inputs: dict = {}


def profile_for_device_name(name: str) -> str:
    name_lower = name.lower()
    for substring, profile in DEVICE_PROFILES.items():
        if substring in name_lower:
            return profile
    return DEFAULT_PROFILE


LOG_FILE = os.path.join(SCRIPT_DIR, "log", "log.jsonl").encode("utf-8")
controllers = {}


def handleEvent(event: sdl2.SDL_Event):
    ts = sdlTsToMonotonic(event.common.timestamp)
    i = event.cdevice.which
    match event.type:
        case sdl2.SDL_CONTROLLERBUTTONDOWN:
            controller_inputs[i]["buttons"].append(event.cbutton.button)
            controller_inputs[i]["notation"] = reader.parseInput(controller_inputs[i])
            logEvent(
                ts,
                "button-down",
                controller=event.cbutton.which,
                button=event.cbutton.button,
            )
        case sdl2.SDL_CONTROLLERBUTTONUP:
            try:
                controller_inputs[i]["buttons"].remove(event.cbutton.button)
            except ValueError:
                print(
                    f"Button not found in controller input. Controller: {event.cbutton.which}, Button: {event.cbutton.button}"
                )
            controller_inputs[i]["notation"] = reader.parseInput(controller_inputs[i])
            logEvent(
                ts,
                "button-up",
                controller=event.cbutton.which,
                button=event.cbutton.button,
            )
        case sdl2.SDL_CONTROLLERAXISMOTION:
            which = event.caxis.which
            axis = event.caxis.axis
            value = event.caxis.value
            profile = controller_profiles.get(which, DEFAULT_PROFILE)

            match profile:
                case "ignore_axes":
                    pass
                case "digital_stick":
                    if value > DIGITAL_STICK_THRESHOLD:
                        quantized = 1
                    elif value < -DIGITAL_STICK_THRESHOLD:
                        quantized = -1
                    else:
                        quantized = 0
                    key = (which, axis)
                    if last_quantized_axis.get(key) != quantized:
                        last_quantized_axis[key] = quantized
                        controller_inputs[i]["axis"].update({axis: quantized})
                        controller_inputs[i]["notation"] = reader.parseInput(
                            controller_inputs[i]
                        )
                        logEvent(
                            ts,
                            "axis_direction",
                            controller=which,
                            axis=axis,
                            direction=quantized,
                        )
                case _:
                    if abs(value) >= RAW_ANALOG_DEADZONE:
                        controller_inputs[i]["axis"].update({axis: value})
                        controller_inputs[i]["notation"] = reader.parseInput(
                            controller_inputs[i]
                        )
                        logEvent(
                            ts, "axis_motion", controller=which, axis=axis, value=value
                        )

        case sdl2.SDL_CONTROLLERDEVICEADDED:
            i = event.cdevice.which
            controller = sdl2.SDL_GameControllerOpen(i)
            joystick = sdl2.SDL_GameControllerGetJoystick(controller)
            instance_id = sdl2.SDL_JoystickInstanceID(joystick)
            controllers[instance_id] = controller
            name = sdl2.SDL_GameControllerName(controller).decode("utf-8")
            profile = profile_for_device_name(name)
            controller_profiles[instance_id] = profile
            controller_inputs[instance_id] = {
                "buttons": [],
                "axis": {i: 0 for i in range(sdl2.SDL_JoystickNumAxes(joystick))},
            }
            controller_inputs[instance_id]["notation"] = reader.parseInput(
                controller_inputs[instance_id]
            )
            print(f"added device, controllers \n {controller_inputs}")
            logEvent(
                ts,
                "controller-connected",
                controller=instance_id,
                name=name,
            )
        case sdl2.SDL_CONTROLLERDEVICEREMOVED:
            instance_id = event.cdevice.which
            if instance_id in controllers:
                sdl2.SDL_GameControllerClose(controllers[instance_id])
                del controllers[instance_id]
            controller_profiles.pop(instance_id, None)
            controller_inputs.pop(instance_id, None)
            logEvent(ts, "controller_disconnected", controller=instance_id)
        case sdl2.SDL_KEYDOWN:
            if not event.key.repeat:
                key_name = sdl2.SDL_GetKeyName(event.key.keysym.sym).decode("utf-8")
                logEvent(ts, "key_down", key=key_name)
        case sdl2.SDL_KEYUP:
            key_name = sdl2.SDL_GetKeyName(event.key.keysym.sym).decode("utf-8")
            logEvent(ts, "key_up", key=key_name)


def sdlTsToMonotonic(sdl_ticks_ms):
    return sdl_epoch_monotonic + (sdl_ticks_ms / 1_000)


def logEvent(ts, event_type, **kwargs):
    assert log_fp is not None, "log_fp not initialized -- call main() first"
    entry = {"t": ts, "type": event_type, **kwargs}
    print(entry)
    log_fp.write(json.dumps(entry) + "\n")
    log_fp.flush()
    # detail = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    # overlay_lines.append(f"{event_type} ({detail})")


# Pulled from claude
def _text_width(text):
    assert font is not None, "font not loaded -- call main() first"
    w, h = ctypes.c_int(), ctypes.c_int()
    TTF_SizeUTF8(font, text.encode("utf-8"), ctypes.byref(w), ctypes.byref(h))
    return w.value


def wrap_to_width(text, max_width):
    """Break text into a list of lines that each fit within max_width pixels."""
    lines = []
    current = ""

    for word in text.split(" "):
        candidate = word if not current else f"{current} {word}"
        if _text_width(candidate) <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ""

        if _text_width(word) <= max_width:
            current = word
            continue

        # a single word is wider than the line -- break it up by character
        chunk = ""
        for ch in word:
            if _text_width(chunk + ch) <= max_width:
                chunk += ch
            else:
                lines.append(chunk)
                chunk = ch
        current = chunk

    if current:
        lines.append(current)
    return lines or [""]


# Pulled from claude
def draw_overlay(windowsurface):
    assert font is not None, "font not loaded -- call main() first"

    color = SDL_Color(0, 255, 0)
    line_height = FONT_SIZE + 4
    y = 8
    margin = 8
    max_width = windowsurface.contents.w - (margin * 2)
    max_height = windowsurface.contents.h

    for controller, inputs in controller_inputs.items():
        if y + line_height > max_height:
            break

        axis_string = ", ".join(f"Axis {k}: {v}" for k, v in inputs["axis"].items())
        button_string = ", ".join(str(b) for b in inputs["buttons"])
        line = f"Controller {controller}: ({axis_string}), (Button: {button_string}), (Notation: {inputs.get('notation', '')})"

        for wrapped_line in wrap_to_width(line, max_width):
            if y + line_height > max_height:
                break  # ran out of vertical room mid-controller

            text_surface = TTF_RenderText_Blended(
                font, wrapped_line.encode("utf-8"), color
            )
            if not text_surface:
                continue
            dest_rect = SDL_Rect(margin, y, 0, 0)
            SDL_BlitSurface(text_surface, None, windowsurface, dest_rect)
            SDL_FreeSurface(text_surface)
            y += line_height


def main():
    global sdl_epoch_monotonic, log_fp, font
    SDL_Init(SDL_INIT_VIDEO | SDL_INIT_JOYSTICK | SDL_INIT_GAMECONTROLLER)
    sdl_epoch_monotonic = time.monotonic() - (SDL_GetTicks() / 1000.0)

    if os.path.exists(GAMECONTROLLERDB_PATH.decode("utf-8")):
        SDL_GameControllerAddMappingsFromFile(GAMECONTROLLERDB_PATH)

    if TTF_Init() != 0:
        print(f"TTF_Init failed: {TTF_GetError()}")
        return 1

    font = TTF_OpenFont(FONT_PATH, FONT_SIZE)
    if not font:
        print(f"Failed to load font at {FONT_PATH!r}: {TTF_GetError()}")
        print("Place a .ttf file at that path (e.g. a system font) and retry.")
        return 1

    log_fp = open(LOG_FILE, "a")
    window = SDL_CreateWindow(
        b"Hello World",
        SDL_WINDOWPOS_CENTERED,
        SDL_WINDOWPOS_CENTERED,
        750,
        750,
        SDL_WINDOW_SHOWN,
    )
    windowsurface = SDL_GetWindowSurface(window)
    for i in range(SDL_NumJoysticks()):
        if not sdl2.SDL_IsGameController(i):
            continue
        controller = sdl2.SDL_GameControllerOpen(i)
        joystick = sdl2.SDL_GameControllerGetJoystick(controller)
        instance_id = sdl2.SDL_JoystickInstanceID(joystick)
        controllers[instance_id] = controller
        name = sdl2.SDL_GameControllerName(controller).decode("utf-8")
        profile = profile_for_device_name(name)
        controller_inputs[i] = {
            "buttons": [],
            "axis": {i: 0 for i in range(sdl2.SDL_JoystickNumAxes(joystick))},
        }
        controller_inputs[i]["notation"] = reader.parseInput(controller_inputs[i])
        controller_profiles[instance_id] = profile
        print(f"found controller: {controller_inputs}")

    background = SDL_LoadBMP(b"exampleimage.bmp")
    SDL_BlitSurface(background, None, windowsurface, None)

    SDL_UpdateWindowSurface(window)
    SDL_FreeSurface(background)

    running = True
    event = SDL_Event()
    running = True
    event = SDL_Event()
    while running:
        while SDL_PollEvent(ctypes.byref(event)) != 0:
            if event.type == SDL_QUIT:
                running = False
                break
            handleEvent(event)

        if running:
            SDL_FillRect(
                windowsurface, None, SDL_MapRGB(windowsurface.contents.format, 0, 0, 0)
            )
            SDL_BlitSurface(background, None, windowsurface, None)
            draw_overlay(windowsurface)
            SDL_UpdateWindowSurface(window)

        SDL_Delay(16)

    SDL_FreeSurface(background)
    TTF_CloseFont(font)
    TTF_Quit()
    log_fp.close()
    for controller in controllers.values():
        sdl2.SDL_GameControllerClose(controller)
    SDL_DestroyWindow(window)
    SDL_Quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())

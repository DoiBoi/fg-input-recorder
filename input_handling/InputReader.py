import json
import os
import sys
from functools import reduce

from data_mining.Backend import Backend

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

_MAPPING_FILE = os.path.join(
    os.path.dirname(SCRIPT_DIR), "data", "defaultMapping.json"
).encode("utf-8")

with open(_MAPPING_FILE, "r", encoding="utf-8") as file:
    _DEFAULTMAPPING = json.load(file)

LEFTSTICK_X_AXIS = 0
LEFTSTICK_Y_AXIS = 1

# Mapping uses (up, down, left, right)
_NUMPAD_DIR_MAPPING = {
    (False, True, True, False): "1",
    (False, True, False, False): "2",
    (False, True, False, True): "3",
    (False, False, True, False): "4",
    (False, False, False, False): "5",
    (False, False, False, True): "6",
    (True, False, True, False): "7",
    (True, False, False, False): "8",
    (True, False, False, True): "9",
}

_NUMPAD_BTN_MAPPING = {
    11: (True, False, False, False),
    12: (False, True, False, False),
    13: (False, False, True, False),
    14: (False, False, False, True),
}


class InputReader:
    # mapping = {}

    def __init__(self, name: str = "", mapping=None, character=None) -> None:
        self.frame = Backend(f"{name}_frame_data")
        if not mapping:
            self.mapping = _DEFAULTMAPPING.get(name, {})
        else:
            self.mapping = mapping
        if not character:
            self.moves = []
        else:
            self.moves = self.frame.fetchData("input, name", f"chara = \"{character}\"")[0]
        print(self.moves)

    def _handleSOCD(
        self, direction: tuple[bool, bool, bool, bool]
    ) -> tuple[bool, bool, bool, bool]:
        return (
            direction[0] & (not direction[1]),
            direction[1] & (not direction[0]),
            direction[2] & (not direction[3]),
            direction[3] & (not direction[2]),
        )

    def _toNumpad(self, axis: dict[int, int], buttons: list):
        btns_direction = reduce(
            lambda acc, curr: tuple(a | b for a, b in zip(acc, curr)),
            [_NUMPAD_BTN_MAPPING[x] for x in buttons if x in _NUMPAD_BTN_MAPPING],
            (False, False, False, False),
        )

        axis_direction = (
            axis[LEFTSTICK_Y_AXIS] == -1,
            axis[LEFTSTICK_Y_AXIS] == 1,
            axis[LEFTSTICK_X_AXIS] == -1,
            axis[LEFTSTICK_X_AXIS] == 1,
        )

        direction = tuple(a | b for a, b in zip(btns_direction, axis_direction))

        assert len(direction) == 4
        direction = self._handleSOCD(direction)
        return _NUMPAD_DIR_MAPPING[direction]

    def _toAtk(self, buttons: list, axis: dict) -> str:
        btn_moves = reduce(
            lambda acc, curr: acc + curr,
            [self.mapping[str(btn)] for btn in buttons if str(btn) in self.mapping],
            [],
        )
        axis_moves = reduce(
            lambda acc, curr: acc + curr,
            [
                self.mapping[f"a{axis}"]
                for axis, value in axis.items()
                if (f"a{axis}" in self.mapping and value == 1)
            ],
            [],
        )

        moves = reduce(lambda curr, acc: acc + curr, set(btn_moves + axis_moves), "")
        return moves

    def setMapping(self, mapping: dict | None = None) -> None:
        if mapping is None:
            mapping = {}
        self.mapping.update(mapping)

    def parseInput(self, input: dict) -> str:
        return self._toNumpad(input["axis"], input["buttons"]) + self._toAtk(
            input["buttons"], input["axis"]
        )
        # return self.mapping.get(input, "")

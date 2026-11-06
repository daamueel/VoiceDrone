"""Deterministic parser for keyboard text and speech transcripts."""

import math
import re

from .commands import (
    CircleBehavior,
    CircleCommand,
    Command,
    Direction,
    ExitCommand,
    HelpCommand,
    LandCommand,
    StatusCommand,
    TakeoffCommand,
)


class CommandParseError(ValueError):
    """Raised when text cannot be mapped to exactly one supported command."""


_TOKEN_PATTERN = re.compile(
    r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[+-]?\d+)?|[a-z]+|[.,!?;:()]|\S",
    re.IGNORECASE,
)
_IGNORED_PUNCTUATION = frozenset(".,!?;:()")
_UNITS = frozenset(("meter", "meters", "metre", "metres"))

_SMALL_NUMBERS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_DIGIT_WORDS = {
    word: value for word, value in _SMALL_NUMBERS.items() if value < 10
}


def _tokens(text: str) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        raise CommandParseError("command is empty")
    normalized = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", text.casefold())
    return [
        token
        for token in _TOKEN_PATTERN.findall(normalized)
        if token not in _IGNORED_PUNCTUATION
    ]


def _parse_under_thousand(words: list[str]) -> int:
    if not words:
        return 0
    if words == ["zero"]:
        return 0
    if "zero" in words:
        raise CommandParseError("invalid spoken number")

    result = 0
    if "hundred" in words:
        if words.count("hundred") != 1:
            raise CommandParseError("invalid spoken number")
        index = words.index("hundred")
        if index != 1 or words[0] not in _DIGIT_WORDS or words[0] == "zero":
            raise CommandParseError("invalid spoken number")
        result = _DIGIT_WORDS[words[0]] * 100
        words = words[2:]

    if not words:
        return result
    if len(words) == 1 and words[0] in _SMALL_NUMBERS:
        return result + _SMALL_NUMBERS[words[0]]
    if words[0] in _TENS and len(words) <= 2:
        tail = 0
        if len(words) == 2:
            if words[1] not in _DIGIT_WORDS or words[1] == "zero":
                raise CommandParseError("invalid spoken number")
            tail = _DIGIT_WORDS[words[1]]
        return result + _TENS[words[0]] + tail
    raise CommandParseError("invalid spoken number")


def _parse_spoken_integer(words: list[str]) -> int:
    words = [word for word in words if word != "and"]
    if not words:
        raise CommandParseError("number is missing")
    if "thousand" not in words:
        return _parse_under_thousand(words)
    if words.count("thousand") != 1:
        raise CommandParseError("invalid spoken number")
    index = words.index("thousand")
    leading = _parse_under_thousand(words[:index])
    if leading == 0:
        raise CommandParseError("invalid spoken number")
    trailing = _parse_under_thousand(words[index + 1 :])
    return leading * 1000 + trailing


def _parse_number(tokens: list[str]) -> float:
    if not tokens:
        raise CommandParseError("number is missing")
    if len(tokens) == 1:
        try:
            value = float(tokens[0])
        except ValueError:
            pass
        else:
            if not math.isfinite(value):
                raise CommandParseError("number must be finite")
            return value

    if tokens.count("point") > 1:
        raise CommandParseError("invalid spoken number")
    if "point" in tokens:
        point = tokens.index("point")
        integer = _parse_spoken_integer(tokens[:point])
        fraction_words = tokens[point + 1 :]
        if not fraction_words or any(
            word not in _DIGIT_WORDS for word in fraction_words
        ):
            raise CommandParseError("invalid spoken decimal")
        fraction = "".join(str(_DIGIT_WORDS[word]) for word in fraction_words)
        return float(f"{integer}.{fraction}")
    return float(_parse_spoken_integer(tokens))


def _parse_measurement(tokens: list[str], *, name: str) -> float:
    units = [token for token in tokens if token in _UNITS]
    if len(units) > 1:
        raise CommandParseError(f"{name} has multiple units")
    if units:
        if tokens[-1] not in _UNITS:
            raise CommandParseError(f"{name} unit must follow the number")
        tokens = tokens[:-1]
    return _parse_number(tokens)


def _takeoff(tokens: list[str]) -> TakeoffCommand:
    if tokens[0] == "takeoff":
        remainder = tokens[1:]
    elif tokens[:2] == ["take", "off"]:
        remainder = tokens[2:]
    else:
        raise CommandParseError("unsupported command")

    if not remainder:
        return TakeoffCommand()
    if remainder[0] == "to":
        remainder = remainder[1:]
    if not remainder:
        raise CommandParseError("takeoff altitude is missing")
    altitude = _parse_measurement(remainder, name="takeoff altitude")
    try:
        return TakeoffCommand(altitude_m=altitude)
    except ValueError as error:
        raise CommandParseError(str(error)) from error


def _collapse_circle_phrases(tokens: list[str]) -> list[str]:
    collapsed: list[str] = []
    index = 0
    while index < len(tokens):
        pair = tokens[index : index + 2]
        if pair == ["fixed", "yaw"]:
            collapsed.append("fixed_yaw")
            index += 2
        elif pair == ["counter", "clockwise"]:
            collapsed.append("counterclockwise")
            index += 2
        else:
            collapsed.append(tokens[index])
            index += 1
    return collapsed


def _circle(tokens: list[str]) -> CircleCommand:
    tokens = _collapse_circle_phrases(tokens)
    circle_count = tokens.count("circle")
    if circle_count > 1:
        raise CommandParseError("circle is specified more than once")

    behavior_tokens = [
        token for token in tokens if token in {"centripetal", "fixed_yaw", "side"}
    ]
    if len(behavior_tokens) > 1:
        raise CommandParseError("circle behavior is ambiguous or repeated")
    behavior_token = behavior_tokens[0] if behavior_tokens else None
    if circle_count == 0 and behavior_token != "centripetal":
        raise CommandParseError("unsupported command")

    behavior = {
        None: CircleBehavior.CENTRIPETAL,
        "centripetal": CircleBehavior.CENTRIPETAL,
        "fixed_yaw": CircleBehavior.FIXED_YAW,
        "side": CircleBehavior.SIDE,
    }[behavior_token]

    direction_tokens = [
        token
        for token in tokens
        if token in {"clockwise", "counterclockwise"}
    ]
    if len(direction_tokens) > 1:
        raise CommandParseError("circle direction is ambiguous or repeated")
    direction = (
        Direction.COUNTERCLOCKWISE
        if direction_tokens == ["counterclockwise"]
        else Direction.CLOCKWISE
    )

    structural = {
        "circle",
        "centripetal",
        "fixed_yaw",
        "side",
        "clockwise",
        "counterclockwise",
    }
    remainder = [token for token in tokens if token not in structural]
    if not remainder:
        radius = CircleCommand().radius_m
    else:
        if remainder.count("radius") != 1 or remainder[0] != "radius":
            raise CommandParseError("circle parameters must use 'radius <number>'")
        radius = _parse_measurement(remainder[1:], name="circle radius")

    try:
        return CircleCommand(
            behavior=behavior,
            radius_m=radius,
            direction=direction,
        )
    except ValueError as error:
        raise CommandParseError(str(error)) from error


def parse_command(text: str) -> Command:
    """Parse text into one validated command without guessing intent."""

    tokens = _tokens(text)
    if tokens[0] in {"takeoff", "take"}:
        return _takeoff(tokens)
    if "circle" in tokens or "centripetal" in tokens:
        return _circle(tokens)
    exact_commands: dict[str, Command] = {
        "land": LandCommand(),
        "status": StatusCommand(),
        "help": HelpCommand(),
        "exit": ExitCommand(),
    }
    if len(tokens) == 1 and tokens[0] in exact_commands:
        return exact_commands[tokens[0]]
    raise CommandParseError("unsupported command")

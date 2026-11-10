"""Voice previews use the shared parser and cannot execute flight actions."""

from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from control.commands import CircleBehavior, CircleCommand, LandCommand, TakeoffCommand
from voice.run_voice import preview_transcript, run_voice_preview


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        ("Take off to 5 meters", TakeoffCommand(5.0)),
        ("circle, radius 5", CircleCommand(radius_m=5.0)),
        ("land", LandCommand()),
    ],
)
def test_live_style_transcript_uses_keyboard_parser(transcript, expected) -> None:
    preview = preview_transcript(transcript)
    assert preview.command == expected
    assert preview.rejection is None
    if isinstance(preview.command, CircleCommand):
        assert preview.command.behavior is CircleBehavior.CENTRIPETAL


@pytest.mark.parametrize(
    "transcript",
    [
        "",
        "Hey cough",
        "so called radius 5",
        "takeoff, take off",
        "takeoff and land",
        "clockwise counterclockwise circle radius 5",
        "fixed yaw side circle radius 5",
    ],
)
def test_unknown_repeated_or_ambiguous_transcript_is_rejected(transcript) -> None:
    preview = preview_transcript(transcript)
    assert preview.command is None
    assert preview.rejection


def test_microphone_preview_only_shows_commands_and_rejections() -> None:
    class FakeRecognizer:
        def __init__(self) -> None:
            self.transcripts: Iterator[str] = iter(("takeoff", "takeoff and land"))

        def input_device(self):
            return 1, "Test microphone"

        def recognize(self, duration_s):
            assert duration_s == 2.0
            return SimpleNamespace(text=next(self.transcripts), rms=0.02, peak=0.2)

    answers = iter(("", "", "q"))
    output: list[str] = []
    status = run_voice_preview(
        FakeRecognizer(), duration_s=2.0,
        input_fn=lambda _: next(answers), output_fn=output.append,
    )

    assert status == 0
    assert "Parsed command: takeoff" in output
    assert any(line.startswith("Rejected:") for line in output)
    assert output.count("Flight action: none (preview only)") == 2

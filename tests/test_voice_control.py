"""Voice previews use the shared parser and cannot execute flight actions."""

import asyncio
from collections.abc import Iterator
import sys
from types import SimpleNamespace

import pytest

from control.commands import CircleBehavior, CircleCommand, LandCommand, TakeoffCommand
from control.session import FlightResult
from voice.run_voice import main, preview_transcript, run_voice_preview, run_voice_sitl


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
    assert "Flight action: none (preview only)" in output
    assert "Flight action: none (rejected)" in output


def test_sitl_voice_requires_confirmation_for_each_spoken_command() -> None:
    class FakeRecognizer:
        def __init__(self) -> None:
            self.transcripts = iter(("takeoff", "takeoff and land", "circle radius 5"))

        def input_device(self):
            return 1, "Test microphone"

        def recognize(self, duration_s):
            return SimpleNamespace(text=next(self.transcripts), rms=0.02, peak=0.2)

    class FakeSession:
        instance = None

        def __init__(self, *, input_type):
            assert input_type == "voice"
            self.log = SimpleNamespace(path="test.csv")
            self.record_path = "test.jsonl"
            self.executed = []
            self.confirmations = []
            self.rejections = []
            FakeSession.instance = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def record_voice_transcript(self, text):
            pass

        def record_voice_confirmation(self, accepted):
            self.confirmations.append(accepted)

        def record_rejection(self, text, reason):
            self.rejections.append(text)

        async def execute(self, command):
            self.executed.append(command)
            return FlightResult("complete")

    answers = iter(("", "", "", "", "yes", "q"))
    output: list[str] = []
    status = asyncio.run(run_voice_sitl(
        FakeRecognizer(), duration_s=1.0,
        input_fn=lambda _: next(answers), output_fn=output.append,
        session_factory=FakeSession,
    ))

    assert status == 0
    assert FakeSession.instance.executed == [CircleCommand(radius_m=5.0)]
    assert FakeSession.instance.confirmations == [False, True]
    assert FakeSession.instance.rejections == ["takeoff and land"]
    assert "Cancelled; no flight action was taken." in output
    assert any(line.startswith("Action after confirmation:") for line in output)


def test_supplied_transcript_cannot_enable_sitl_execution(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["voicedrone-voice", "--sitl", "--transcript", "takeoff"])
    with pytest.raises(SystemExit) as exit_result:
        main()
    assert exit_result.value.code == 2

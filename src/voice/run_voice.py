"""Preview speech, or confirm each spoken command for PX4 Gazebo SITL."""

import argparse
import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import sys

from control.commands import (
    CircleBehavior, CircleCommand, Command, ExitCommand, HelpCommand, LandCommand,
    StatusCommand, TakeoffCommand,
)
from control.parser import CommandParseError, parse_command
from control.run_keyboard import (
    _read_sitl_input, command_name, effective_parameters,
    execute_with_land_hotkey,
)

from .recognizer import DEFAULT_MODEL_NAME, MicrophoneRecognizer, SUPPORTED_MODELS


@dataclass(frozen=True, slots=True)
class VoicePreview:
    transcript: str
    command: Command | None = None
    rejection: str | None = None


def preview_transcript(transcript: str) -> VoicePreview:
    """Use the keyboard parser unchanged; never execute the parsed command."""

    try:
        command = parse_command(transcript)
    except CommandParseError as error:
        return VoicePreview(transcript, rejection=str(error))
    return VoicePreview(transcript, command=command)


def show_preview(
    preview: VoicePreview, *, execution_enabled: bool = False,
    output_fn: Callable[[str], None] = print,
) -> None:
    output_fn(f"Transcript: {preview.transcript or '<none>'}")
    if preview.rejection is not None:
        output_fn(f"Rejected: {preview.rejection}")
        output_fn("Flight action: none (rejected)")
    else:
        assert preview.command is not None
        output_fn(f"Parsed command: {command_name(preview.command)}")
        output_fn(f"Effective parameters: {effective_parameters(preview.command)}")
        if execution_enabled:
            output_fn(
                f'Confirmation: Transcript "{preview.transcript}" parsed as '
                f"{describe_action(preview.command)} in PX4 SITL. "
                "Type Y to execute, or N to skip it."
            )
            output_fn("Flight action: none yet; keyboard confirmation required")
        else:
            output_fn("Flight action: none (preview only)")


def describe_action(command: Command) -> str:
    if isinstance(command, TakeoffCommand):
        return f"take off to {command.altitude_m:.3f} m and remain airborne"
    if isinstance(command, CircleCommand):
        facing = (
            "fixed-heading" if command.behavior is CircleBehavior.FIXED_YAW
            else "inward-facing"
        )
        return (
            f"one {command.direction.value}, {facing} circle at "
            f"{command.radius_m:.3f} m radius and {command.speed_m_s:.3f} m/s, "
            "then return to its airborne start and remain airborne"
        )
    if isinstance(command, LandCommand):
        return "land and wait for disarm"
    if isinstance(command, StatusCommand):
        return "show the current vehicle state"
    if isinstance(command, HelpCommand):
        return "show supported commands"
    if isinstance(command, ExitCommand):
        return "close the session, landing and disarming if airborne"
    raise TypeError(f"unsupported command: {type(command).__name__}")


def run_voice_preview(
    recognizer: MicrophoneRecognizer,
    *,
    duration_s: float = 6.0,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    index, name = recognizer.input_device()
    output_fn(f"Input device {index}: {name}")
    output_fn("Voice command preview. No PX4 connection or flight action is used.")
    try:
        while True:
            response = input_fn("Press Enter to record, or type q to quit: ")
            if response.strip().casefold() == "q":
                return 0
            if response.strip():
                output_fn("Type q or press Enter; no recording started.")
                continue
            output_fn(f"Recording for {duration_s:g} seconds...")
            result = recognizer.recognize(duration_s)
            output_fn(f"Input level: RMS={result.rms:.6f}, peak={result.peak:.6f}")
            show_preview(preview_transcript(result.text), output_fn=output_fn)
    except EOFError:
        return 0
    except KeyboardInterrupt:
        output_fn("Stopped")
        return 130


async def run_voice_sitl(
    recognizer: MicrophoneRecognizer,
    *,
    duration_s: float = 6.0,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    session_factory: Callable[..., object] | None = None,
) -> int:
    """Use the shared flight session only after typed Y for each voice command."""

    from control.session import CommandRejected, FlightSession

    factory = FlightSession if session_factory is None else session_factory
    index, name = recognizer.input_device()
    output_fn(f"Input device {index}: {name}")
    output_fn("VoiceDrone voice control - PX4 Gazebo SITL only")
    async with factory(input_type="voice") as session:
        output_fn(f"Telemetry CSV: {session.log.path}")
        output_fn(f"Command record: {session.record_path}")
        output_fn("Each spoken command requires typed Y before execution.")
        output_fn("During a maneuver, press L without Enter to land immediately.")
        while True:
            response = await _read_sitl_input(
                input_fn, "Press Enter to record, or type q to quit: "
            )
            if response.strip().casefold() == "q":
                return 0
            if response.strip():
                output_fn("Type q or press Enter; no recording started.")
                continue

            output_fn(f"Recording for {duration_s:g} seconds...")
            result = await asyncio.to_thread(recognizer.recognize, duration_s)
            output_fn(f"Input level: RMS={result.rms:.6f}, peak={result.peak:.6f}")
            session.record_voice_transcript(result.text)
            preview = preview_transcript(result.text)
            show_preview(preview, execution_enabled=True, output_fn=output_fn)
            if preview.command is None:
                session.record_rejection(result.text, preview.rejection or "unknown")
                continue

            answer = await _read_sitl_input(
                input_fn, "Type Y to execute, or N to cancel: ",
                clear_pending=True,
            )
            confirmed = answer.strip().casefold() == "y"
            session.record_voice_confirmation(confirmed)
            if not confirmed:
                output_fn("Cancelled; no flight action was taken.")
                continue

            try:
                if isinstance(preview.command, (TakeoffCommand, CircleCommand)):
                    flight_result = await execute_with_land_hotkey(
                        session, preview.command, output_fn=output_fn
                    )
                else:
                    flight_result = await session.execute(preview.command)
            except CommandRejected as error:
                output_fn(f"Rejected: {error}; no flight action was taken.")
                continue
            output_fn(f"Complete: {flight_result.message}")
            if flight_result.exit_requested:
                return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=int, help="sounddevice input index")
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--model", choices=SUPPORTED_MODELS, default=DEFAULT_MODEL_NAME)
    parser.add_argument(
        "--sitl", action="store_true", help="enable confirmed PX4 Gazebo SITL commands"
    )
    parser.add_argument(
        "--transcript", action="append", metavar="TEXT",
        help="preview supplied text without using the microphone",
    )
    args = parser.parse_args()

    if args.sitl and args.transcript is not None:
        parser.error("--transcript is preview-only and cannot be combined with --sitl")

    if args.transcript is not None:
        for transcript in args.transcript:
            show_preview(preview_transcript(transcript))
        return

    recognizer = MicrophoneRecognizer(device=args.device, model_name=args.model)
    try:
        status = (
            asyncio.run(run_voice_sitl(recognizer, duration_s=args.duration))
            if args.sitl else run_voice_preview(recognizer, duration_s=args.duration)
        )
    except asyncio.CancelledError as error:
        print(f"SITL session interrupted: {error}")
        print("Landing and disarm could not be confirmed. Check PX4 SITL status.")
        status = 1
    except KeyboardInterrupt:
        print("Cancelled; closing the SITL session if open.")
        status = 130
    except Exception as error:
        print(f"Voice control failed: {error}")
        if args.sitl:
            print("Check PX4 SITL status before another flight.")
        status = 1
    raise SystemExit(status)


if __name__ == "__main__":
    main()

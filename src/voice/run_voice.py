"""Preview spoken commands without opening a flight session."""

import argparse
from collections.abc import Callable
from dataclasses import dataclass

from control.commands import Command
from control.parser import CommandParseError, parse_command
from control.run_keyboard import command_name, effective_parameters

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
    preview: VoicePreview, *, output_fn: Callable[[str], None] = print
) -> None:
    output_fn(f"Transcript: {preview.transcript or '<none>'}")
    if preview.rejection is not None:
        output_fn(f"Rejected: {preview.rejection}")
    else:
        assert preview.command is not None
        output_fn(f"Parsed command: {command_name(preview.command)}")
        output_fn(f"Effective parameters: {effective_parameters(preview.command)}")
    output_fn("Flight action: none (preview only)")


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=int, help="sounddevice input index")
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--model", choices=SUPPORTED_MODELS, default=DEFAULT_MODEL_NAME)
    parser.add_argument(
        "--transcript", action="append", metavar="TEXT",
        help="preview supplied text without using the microphone",
    )
    args = parser.parse_args()

    if args.transcript is not None:
        for transcript in args.transcript:
            show_preview(preview_transcript(transcript))
        return

    recognizer = MicrophoneRecognizer(device=args.device, model_name=args.model)
    raise SystemExit(run_voice_preview(recognizer, duration_s=args.duration))


if __name__ == "__main__":
    main()

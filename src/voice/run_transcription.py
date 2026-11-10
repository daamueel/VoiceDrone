"""Transcribe microphone speech locally without parsing or flying."""

import argparse

from .recognizer import DEFAULT_MODEL_NAME, MicrophoneRecognizer, SUPPORTED_MODELS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=int, help="sounddevice input index")
    parser.add_argument("--duration", type=float, default=4.0, help="seconds per capture")
    parser.add_argument("--model", choices=SUPPORTED_MODELS, default=DEFAULT_MODEL_NAME)
    args = parser.parse_args()

    recognizer = MicrophoneRecognizer(device=args.device, model_name=args.model)
    index, name = recognizer.input_device()
    print(f"Input device {index}: {name}")
    print(f"Speech model: {args.model}")
    print("Transcription only. No command parser or flight connection is used.")
    try:
        while True:
            response = input("Press Enter to record, or type q to quit: ")
            if response.strip().casefold() == "q":
                return
            if response.strip():
                print("Type q or press Enter; no recording started.")
                continue
            print(f"Recording for {args.duration:g} seconds...", flush=True)
            result = recognizer.recognize(args.duration)
            print(f"Transcript: {result.text or '<none>'}")
            print(f"Input level: RMS={result.rms:.6f}, peak={result.peak:.6f}")
    except (EOFError, KeyboardInterrupt):
        print("Stopped")


if __name__ == "__main__":
    main()

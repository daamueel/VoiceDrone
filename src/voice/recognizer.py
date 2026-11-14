"""Local microphone transcription. This module has no flight connection."""

from dataclasses import dataclass
import math

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from .continuous import ContinuousMicrophone, DEFAULT_MAX_UTTERANCE_SECONDS


SAMPLE_RATE = 16_000
DEFAULT_MODEL_NAME = "small.en"
SUPPORTED_MODELS = ("base.en", "small.en")
COMMAND_HOTWORDS = (
    "takeoff, take off, circle, radius, clockwise, counterclockwise, "
    "centripetal, fixed yaw, side, land"
)


@dataclass(frozen=True, slots=True)
class RecognitionResult:
    text: str
    rms: float
    peak: float


class MicrophoneRecognizer:
    """Transcribe recorded phrases with the cached local Whisper model."""

    def __init__(
        self, *, device: int | None = None, model_name: str = DEFAULT_MODEL_NAME
    ) -> None:
        if model_name not in SUPPORTED_MODELS:
            raise ValueError(f"unsupported local speech model: {model_name}")
        self.device = device
        self.model = WhisperModel(
            model_name, device="cpu", compute_type="int8", local_files_only=True
        )

    def input_device(self) -> tuple[int, str]:
        index = sd.default.device[0] if self.device is None else self.device
        info = sd.query_devices(index, "input")
        sd.check_input_settings(
            device=index, samplerate=SAMPLE_RATE, channels=1, dtype="float32"
        )
        return index, info["name"]

    def recognize(self, duration_s: float = 4.0) -> RecognitionResult:
        if not math.isfinite(duration_s) or not 1.0 <= duration_s <= 30.0:
            raise ValueError("recording duration must be between 1 and 30 seconds")

        index, _ = self.input_device()
        frames = round(SAMPLE_RATE * duration_s)
        recording = sd.rec(
            frames, samplerate=SAMPLE_RATE, channels=1,
            dtype="float32", device=index, blocking=True,
        )
        audio = np.asarray(recording[:, 0], dtype=np.float32)
        return self.transcribe_audio(audio)

    def open_stream(
        self, *, max_utterance_s: float = DEFAULT_MAX_UTTERANCE_SECONDS,
    ) -> ContinuousMicrophone:
        index, _ = self.input_device()
        return ContinuousMicrophone(device=index, max_utterance_s=max_utterance_s)

    def transcribe_audio(self, audio: np.ndarray) -> RecognitionResult:
        """Transcribe one completed utterance; keep its samples in memory only."""

        rms = float(np.sqrt(np.mean(np.square(audio))))
        peak = float(np.max(np.abs(audio)))

        segments, _ = self.model.transcribe(
            audio,
            language="en",
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
            hotwords=COMMAND_HOTWORDS,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return RecognitionResult(text=text, rms=rms, peak=peak)

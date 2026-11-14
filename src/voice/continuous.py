"""Continuous microphone capture with speech-end detection before transcription."""

import asyncio
from collections import deque
from collections.abc import Callable
import math
from queue import Empty, Full, Queue

from faster_whisper.vad import get_vad_model
import numpy as np
import sounddevice as sd


SAMPLE_RATE = 16_000
CHUNK_SAMPLES = 512
CHUNK_SECONDS = CHUNK_SAMPLES / SAMPLE_RATE
PRE_ROLL_SECONDS = 0.32
END_SILENCE_SECONDS = 0.72
MIN_SPEECH_SECONDS = 0.16
DEFAULT_MAX_UTTERANCE_SECONDS = 10.0


class SileroStreamScorer:
    """Retain Silero's recurrent state across 32 ms microphone chunks."""

    def __init__(self) -> None:
        self._session = get_vad_model().session
        self.reset()

    def reset(self) -> None:
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros(64, dtype=np.float32)

    def score(self, chunk: np.ndarray) -> float:
        window = np.concatenate((self._context, chunk)).reshape(1, 576)
        probabilities, self._h, self._c = self._session.run(
            None, {"input": window, "h": self._h, "c": self._c}
        )
        self._context = chunk[-64:].copy()
        return float(probabilities[0])


class UtteranceDetector:
    """Return complete phrases; ignore short noises and overlong speech."""

    def __init__(
        self, *, max_utterance_s: float = DEFAULT_MAX_UTTERANCE_SECONDS,
        scorer: object | None = None,
    ) -> None:
        if not math.isfinite(max_utterance_s) or not 1.0 <= max_utterance_s <= 30.0:
            raise ValueError("maximum utterance must be between 1 and 30 seconds")
        self.scorer = SileroStreamScorer() if scorer is None else scorer
        self.max_frames = math.ceil(max_utterance_s / CHUNK_SECONDS)
        self.reset()

    def reset(self) -> None:
        self.scorer.reset()
        self._pre_roll: deque[np.ndarray] = deque(
            maxlen=math.ceil(PRE_ROLL_SECONDS / CHUNK_SECONDS)
        )
        self._frames: list[np.ndarray] = []
        self._speech_frames = 0
        self._silence_frames = 0
        self._dropping = False

    def push(self, chunk: np.ndarray) -> np.ndarray | None:
        if chunk.shape != (CHUNK_SAMPLES,):
            raise ValueError("VAD chunk must contain 512 mono samples")
        probability = self.scorer.score(chunk)
        if not self._frames and not self._dropping:
            self._pre_roll.append(chunk)
            if probability >= 0.5:
                self._frames = list(self._pre_roll)
                self._pre_roll.clear()
                self._speech_frames = 1
            return None

        if probability < 0.35:
            self._silence_frames += 1
        else:
            self._silence_frames = 0
            if probability >= 0.5:
                self._speech_frames += 1

        if self._dropping:
            if self._silence_frames >= math.ceil(END_SILENCE_SECONDS / CHUNK_SECONDS):
                self.reset()
            return None

        self._frames.append(chunk)
        if len(self._frames) > self.max_frames:
            self._frames.clear()
            self._dropping = True
            return None
        if self._silence_frames < math.ceil(END_SILENCE_SECONDS / CHUNK_SECONDS):
            return None

        audio = np.concatenate(self._frames)
        enough_speech = self._speech_frames >= math.ceil(
            MIN_SPEECH_SECONDS / CHUNK_SECONDS
        )
        self.reset()
        return audio if enough_speech else None


class ContinuousMicrophone:
    """Keep the device open while dropping audio outside the listening state."""

    def __init__(
        self, *, device: int,
        max_utterance_s: float = DEFAULT_MAX_UTTERANCE_SECONDS,
        detector: UtteranceDetector | None = None,
    ) -> None:
        self.device = device
        self.detector = detector or UtteranceDetector(max_utterance_s=max_utterance_s)
        self._chunks: Queue[np.ndarray] = Queue(maxsize=512)
        self._accepting = False
        self._overrun = False
        self._stream: sd.InputStream | None = None

    def __enter__(self) -> "ContinuousMicrophone":
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            device=self.device, blocksize=CHUNK_SAMPLES, callback=self._on_audio,
        )
        try:
            self._stream.start()
        except BaseException:
            self._stream.close()
            self._stream = None
            raise
        self.resume()
        return self

    def __exit__(self, *_: object) -> None:
        self.pause()
        assert self._stream is not None
        try:
            self._stream.stop()
        finally:
            self._stream.close()
            self._stream = None

    def _on_audio(self, indata: np.ndarray, frames: int, _time: object, status: object) -> None:
        if not self._accepting:
            return
        if status or frames != CHUNK_SAMPLES:
            self._overrun = True
            return
        try:
            self._chunks.put_nowait(indata[:, 0].copy())
        except Full:
            self._overrun = True

    def _clear(self) -> None:
        while True:
            try:
                self._chunks.get_nowait()
            except Empty:
                break
        self._overrun = False
        self.detector.reset()

    def pause(self) -> None:
        self._accepting = False
        self._clear()

    def resume(self) -> None:
        self._accepting = False
        self._clear()
        self._accepting = True

    async def next_utterance(
        self, *, key_fn: Callable[[], str | None],
    ) -> np.ndarray | None:
        """Return the next completed phrase, or None when Q stops listening."""

        while True:
            key = key_fn()
            if key is not None and key.casefold() == "q":
                self.pause()
                return None
            if self._overrun:
                self._clear()
            try:
                chunk = self._chunks.get_nowait()
            except Empty:
                await asyncio.sleep(0.02)
                continue
            audio = self.detector.push(chunk)
            if audio is not None:
                self.pause()
                return audio

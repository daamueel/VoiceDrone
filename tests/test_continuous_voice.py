"""Speech boundaries and microphone gating without a physical input device."""

import asyncio
from collections.abc import Iterator
import numpy as np
import pytest

from voice import continuous


def test_packaged_silero_vad_scores_a_silent_chunk() -> None:
    scorer = continuous.SileroStreamScorer()
    score = scorer.score(np.zeros(continuous.CHUNK_SAMPLES, dtype=np.float32))
    assert 0.0 <= score < 0.5


class FakeScorer:
    def __init__(self, probabilities: list[float]) -> None:
        self.probabilities: Iterator[float] = iter(probabilities)
        self.resets = 0

    def reset(self) -> None:
        self.resets += 1

    def score(self, chunk: np.ndarray) -> float:
        return next(self.probabilities)


def test_vad_waits_for_phrase_end_and_keeps_full_audio() -> None:
    scorer = FakeScorer([0.0] * 4 + [0.8] * 8 + [0.1] * 23)
    detector = continuous.UtteranceDetector(scorer=scorer)
    completed = []
    for index in range(35):
        chunk = np.full(continuous.CHUNK_SAMPLES, index, dtype=np.float32)
        completed.append(detector.push(chunk))

    assert all(result is None for result in completed[:-1])
    audio = completed[-1]
    assert audio is not None
    assert audio[0] == 0  # pre-roll preserves the start of the phrase
    assert audio[-1] == 34
    assert scorer.resets == 2


def test_vad_keeps_words_separated_by_a_short_pause_together() -> None:
    scorer = FakeScorer([0.8] * 6 + [0.1] * 10 + [0.8] * 6 + [0.1] * 23)
    detector = continuous.UtteranceDetector(scorer=scorer)
    chunk = np.zeros(continuous.CHUNK_SAMPLES, dtype=np.float32)
    results = [detector.push(chunk) for _ in range(45)]
    assert all(result is None for result in results[:-1])
    assert results[-1] is not None


def test_vad_discards_short_noise_and_overlong_phrase() -> None:
    short = FakeScorer([0.8] + [0.1] * 23)
    detector = continuous.UtteranceDetector(scorer=short)
    chunk = np.zeros(continuous.CHUNK_SAMPLES, dtype=np.float32)
    assert all(detector.push(chunk) is None for _ in range(24))

    long = FakeScorer([0.8] * 33 + [0.1] * 23)
    detector = continuous.UtteranceDetector(max_utterance_s=1.0, scorer=long)
    assert all(detector.push(chunk) is None for _ in range(56))


@pytest.mark.parametrize("limit", [0.0, 30.1, float("nan")])
def test_vad_rejects_invalid_maximum_duration(limit: float) -> None:
    with pytest.raises(ValueError, match="maximum utterance"):
        continuous.UtteranceDetector(max_utterance_s=limit, scorer=FakeScorer([]))


def test_microphone_drops_audio_while_paused_and_clears_backlog(monkeypatch) -> None:
    class FakeDetector:
        def __init__(self) -> None:
            self.resets = 0

        def reset(self):
            self.resets += 1

        def push(self, chunk):
            return chunk

    class FakeInputStream:
        def __init__(self, **options):
            self.callback = options["callback"]
            self.started = False
            self.closed = False

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

        def close(self):
            self.closed = True

    created = []

    def make_stream(**options):
        stream = FakeInputStream(**options)
        created.append(stream)
        return stream

    monkeypatch.setattr(continuous.sd, "InputStream", make_stream)
    microphone = continuous.ContinuousMicrophone(device=1, detector=FakeDetector())
    with microphone:
        stream = created[0]
        first = np.ones((continuous.CHUNK_SAMPLES, 1), dtype=np.float32)
        stale = np.full_like(first, 2)
        fresh = np.full_like(first, 3)
        stream.callback(first, continuous.CHUNK_SAMPLES, None, None)
        stream.callback(stale, continuous.CHUNK_SAMPLES, None, None)
        received = asyncio.run(microphone.next_utterance(key_fn=lambda: None))
        assert received is not None and received[0] == 1
        stream.callback(stale, continuous.CHUNK_SAMPLES, None, None)
        microphone.resume()
        stream.callback(fresh, continuous.CHUNK_SAMPLES, None, None)
        received = asyncio.run(microphone.next_utterance(key_fn=lambda: None))
        assert received is not None and received[0] == 3
        microphone.resume()
        assert asyncio.run(microphone.next_utterance(key_fn=lambda: "q")) is None
    assert created[0].closed

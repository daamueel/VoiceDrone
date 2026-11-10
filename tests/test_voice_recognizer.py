"""Transcription checks with the microphone and model replaced by small fakes."""

from types import SimpleNamespace

import numpy as np
import pytest

from voice import recognizer


def test_microphone_audio_is_transcribed_without_flight_action(monkeypatch) -> None:
    model_options = {}
    transcription_options = {}

    class FakeModel:
        def __init__(self, name, **options):
            model_options.update(name=name, **options)

        def transcribe(self, audio, **options):
            transcription_options.update(options)
            assert audio.shape == (16_000,)
            return iter((SimpleNamespace(text=" Takeoff "),)), None

    def fake_record(frames, **options):
        assert frames == 16_000
        assert options == dict(
            samplerate=16_000, channels=1, dtype="float32",
            device=1, blocking=True,
        )
        return np.full((frames, 1), 0.25, dtype=np.float32)

    monkeypatch.setattr(recognizer, "WhisperModel", FakeModel)
    monkeypatch.setattr(recognizer.sd, "query_devices", lambda *_: {"name": "Realtek mic"})
    monkeypatch.setattr(recognizer.sd, "check_input_settings", lambda **_: None)
    monkeypatch.setattr(recognizer.sd, "rec", fake_record)

    result = recognizer.MicrophoneRecognizer(device=1).recognize(1.0)

    assert result.text == "Takeoff"
    assert result.rms == result.peak == 0.25
    assert model_options == dict(
        name="small.en", device="cpu", compute_type="int8", local_files_only=True
    )
    assert transcription_options["vad_filter"] is True
    assert transcription_options["language"] == "en"
    assert "circle" in transcription_options["hotwords"]


def test_invalid_duration_never_starts_recording(monkeypatch) -> None:
    monkeypatch.setattr(recognizer, "WhisperModel", lambda *_, **__: object())
    monkeypatch.setattr(
        recognizer.sd, "rec", lambda *_, **__: pytest.fail("recording started")
    )
    microphone = recognizer.MicrophoneRecognizer()
    for duration in (0, 31, float("nan")):
        with pytest.raises(ValueError, match="duration"):
            microphone.recognize(duration)


def test_recognizer_selects_cached_small_model(monkeypatch) -> None:
    selected = []
    monkeypatch.setattr(
        recognizer, "WhisperModel",
        lambda name, **options: selected.append((name, options)),
    )
    recognizer.MicrophoneRecognizer(model_name="small.en")
    assert selected[0][0] == "small.en"
    assert selected[0][1]["local_files_only"] is True

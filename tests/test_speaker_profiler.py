"""Unit tests for speaker age/gender profiling sidecar."""
from __future__ import annotations

import struct

import pytest

from speaker_profiler import (
    SpeakerProfile,
    _top_label,
    inject_speaker_annotation,
    pitch_to_gender_hint,
    speaker_profiling_enabled,
)
from stt_audio import pcm_rms, pcm_to_wav_bytes


def test_pcm_to_wav_header():
    pcm = b"\x00\x01" * 160  # 160 samples
    wav = pcm_to_wav_bytes(pcm, sample_rate=16000)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert wav[12:16] == b"fmt "
    assert wav[36:40] == b"data"
    data_size = struct.unpack_from("<I", wav, 40)[0]
    assert data_size == len(pcm)
    assert len(wav) == 44 + len(pcm)


def test_pcm_rms_silence_and_tone():
    silence = b"\x00\x00" * 100
    assert pcm_rms(silence) == 0.0
    loud = struct.pack("<" + "h" * 100, *([10000] * 100))
    assert pcm_rms(loud) > 1000


def test_top_label_list_and_object():
    label, conf = _top_label([{"label": "adult", "confidence": 0.9}, {"label": "young", "confidence": 0.1}])
    assert label == "adult"
    assert conf == 0.9
    label2, conf2 = _top_label({"label": "Young", "confidence": 0.7})
    assert label2 == "young"
    assert conf2 == 0.7
    assert _top_label(None) == (None, 0.0)


def test_pitch_gender_hint_capped():
    g, c = pitch_to_gender_hint("low")
    assert g == "male"
    assert c <= 0.55
    g2, c2 = pitch_to_gender_hint("high")
    assert g2 == "female"
    assert pitch_to_gender_hint("medium") == (None, 0.0)
    assert pitch_to_gender_hint(None) == (None, 0.0)


def test_speaker_profiling_enabled_flag():
    assert speaker_profiling_enabled({}) is False
    assert speaker_profiling_enabled({"speaker_profiling": {"enabled": False}}) is False
    assert speaker_profiling_enabled({"speaker_profiling": {"enabled": True}}) is True
    assert speaker_profiling_enabled({"speaker_profiling_enabled": True}) is True


def test_reconcile_gender_smallest_beats_pitch():
    from speaker_profiler import SpeakerProfiler

    sp = SpeakerProfiler(None, {"speaker_profiling": {"enabled": True}}, None)
    # fake inworld pitch + smallest gender
    class FakeIn:
        best_age = ("adult", 0.85)
        best_pitch = ("low", 0.9)
        best_emotion = ("neutral", 0.5)
        best_accent = (None, 0.0)
        best_style = (None, 0.0)
        raw_last = {}
        age_locked = True

    class FakeSm:
        result_gender = "female"
        result_confidence = 0.8
        result_age = None
        result_emotion = None
        raw = {"gender": "female"}
        _fired = True

        async def force_fire(self):
            return None

        async def aclose(self):
            return None

    sp.inworld = FakeIn()
    sp.smallest = FakeSm()
    sp._reconcile(provisional=False)
    assert sp.profile.age_group == "adult"
    assert sp.profile.gender == "female"
    assert sp.profile.gender_source == "smallest"
    assert sp.profile.pitch == "low"


def test_reconcile_pitch_hint_only():
    from speaker_profiler import SpeakerProfiler

    sp = SpeakerProfiler(None, {"speaker_profiling": {"enabled": True}}, None)

    class FakeIn:
        best_age = ("young", 0.7)
        best_pitch = ("high", 0.8)
        best_emotion = (None, 0.0)
        best_accent = (None, 0.0)
        best_style = (None, 0.0)
        raw_last = {}

    sp.inworld = FakeIn()
    sp.smallest = None
    sp._reconcile(provisional=True)
    assert sp.profile.gender == "female"
    assert sp.profile.gender_source == "pitch_hint"
    assert sp.profile.gender_confidence <= 0.55


def test_inject_annotation_appends():
    class FakeCtx:
        def __init__(self):
            self.items = []

        def append(self, role=None, text=None, content=None):
            self.items.append({"role": role, "text": text or content})

    ctx = FakeCtx()
    profile = SpeakerProfile(age_group="adult", gender="male", age_confidence=0.8, gender_confidence=0.8)
    inject_speaker_annotation(ctx, profile)
    assert ctx.items
    assert "SPEAKER PROFILE" in ctx.items[0]["text"]
    assert "Do NOT mention" in ctx.items[0]["text"]


def test_profile_public_dict_strips_raw():
    p = SpeakerProfile(age_group="adult", gender="male", raw={"x": 1})
    d = p.to_public_dict()
    assert "raw" not in d
    assert d["age_group"] == "adult"

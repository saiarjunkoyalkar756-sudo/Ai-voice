"""
Live speaker age + gender profiling (sidecar — does not replace Soniox STT).

Division of labor (vendor constraints):
  • Age (real-time):   Inworld STT Voice Profiles (streaming WS)
  • Gender (buffered): Smallest AI Pulse pre-recorded STT (gender_detection)
  • Pitch / emotion:   Inworld (bonus; pitch only used as low-confidence gender hint)

Audio is tee'd from Agent.stt_node; Soniox transcription path is untouched.
Feature flag: config speaker_profiling.enabled (default false).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

logger = logging.getLogger("inbound-voice-agent")

INWORLD_WS_URL = "wss://api.inworld.ai/stt/v1/transcribe:streamBidirectional"
SMALLEST_STT_URL = "https://api.smallest.ai/waves/v1/stt/"

_PITCH_GENDER_HINT = {
    "low": "male",
    "high": "female",
    "medium": None,
}


# ── Config helpers ───────────────────────────────────────────────────────────


def _cfg_block(live_config: dict | None) -> dict[str, Any]:
    raw = (live_config or {}).get("speaker_profiling")
    if isinstance(raw, dict):
        return raw
    # flat keys fallback
    return {
        "enabled": bool((live_config or {}).get("speaker_profiling_enabled")),
        "window_s": (live_config or {}).get("speaker_profiling_window_s", 6.0),
        "deadline_s": (live_config or {}).get("speaker_profiling_deadline_s", 7.0),
        "age_conf_min": (live_config or {}).get("speaker_profiling_age_conf_min", 0.6),
        "gender_provider_prior": (live_config or {}).get(
            "speaker_profiling_gender_provider_prior", 0.8
        ),
        "silence_rms_floor": (live_config or {}).get(
            "speaker_profiling_silence_rms_floor", 350
        ),
        "inworld_model_id": (live_config or {}).get(
            "speaker_profiling_inworld_model_id", "inworld/inworld-stt-1"
        ),
        "inworld_top_n": (live_config or {}).get("speaker_profiling_inworld_top_n", 3),
        "smallest_model": (live_config or {}).get(
            "speaker_profiling_smallest_model", "pulse"
        ),
        "language": (live_config or {}).get("speaker_profiling_language", "en"),
        "inject_into_llm": (live_config or {}).get(
            "speaker_profiling_inject_into_llm", True
        ),
        "store_in_analytics": (live_config or {}).get(
            "speaker_profiling_store_in_analytics", True
        ),
        "emotion_detection": (live_config or {}).get(
            "speaker_profiling_emotion_detection", True
        ),
    }


def speaker_profiling_enabled(live_config: dict | None) -> bool:
    return bool(_cfg_block(live_config).get("enabled"))


def _resolve_key(
    env_name: str,
    call_cfg: Any = None,
    attr: str | None = None,
    get_secret: Callable | None = None,
) -> str:
    if call_cfg is not None and attr:
        val = getattr(call_cfg, attr, None)
        if val and str(val).strip():
            return str(val).strip()
    env_val = (os.environ.get(env_name) or "").strip()
    if env_val:
        return env_val
    if get_secret:
        try:
            secret = get_secret(env_name)
            if secret and str(secret).strip():
                return str(secret).strip()
        except Exception:
            pass
    try:
        from secrets_manager import get_secret as _gs

        secret = _gs(env_name)
        if secret and str(secret).strip():
            return str(secret).strip()
    except Exception:
        pass
    return ""


# ── Result model ─────────────────────────────────────────────────────────────


@dataclass
class SpeakerProfile:
    age_group: str | None = None  # kid|young|adult|old
    age_confidence: float = 0.0
    age_source: str = ""  # inworld|smallest|merged
    gender: str | None = None  # male|female
    gender_confidence: float = 0.0
    gender_source: str = ""  # smallest|pitch_hint
    pitch: str | None = None
    emotion: str | None = None
    accent: str | None = None
    vocal_style: str | None = None
    finalized: bool = False
    finalized_at_s: float = 0.0
    raw: dict = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # keep raw out of dashboard by default (audit only in logs)
        d.pop("raw", None)
        return d


def inject_speaker_annotation(chat_ctx, profile: SpeakerProfile) -> None:
    """Transient system note — never verbalize demographics to the caller."""
    if not profile or (not profile.age_group and not profile.gender):
        return
    parts = []
    if profile.age_group:
        parts.append(f"age_group≈{profile.age_group} (conf {profile.age_confidence:.2f})")
    if profile.gender:
        parts.append(f"gender≈{profile.gender} (conf {profile.gender_confidence:.2f}, src={profile.gender_source})")
    if profile.emotion:
        parts.append(f"emotion≈{profile.emotion}")
    body = (
        "[SPEAKER PROFILE — internal only] Caller likely: "
        + ", ".join(parts)
        + ". Adapt tone and pacing gently. "
        "Do NOT mention, imply, or ask about age, gender, or demographics."
    )
    try:
        chat_ctx.append(role="system", text=body)
    except TypeError:
        try:
            chat_ctx.append(role="system", content=body)
        except Exception:
            logger.debug("[SPEAKER] inject failed", exc_info=True)


# ── Parsing helpers ──────────────────────────────────────────────────────────


def _top_label(entries: Any) -> tuple[str | None, float]:
    """Parse Inworld voiceProfile category — list of {label,confidence} or single object."""
    if not entries:
        return None, 0.0
    if isinstance(entries, dict):
        label = entries.get("label") or entries.get("value")
        conf = float(entries.get("confidence") or 0.0)
        return (str(label).lower() if label else None), conf
    if isinstance(entries, list) and entries:
        best = entries[0]
        if isinstance(best, dict):
            label = best.get("label") or best.get("value")
            conf = float(best.get("confidence") or 0.0)
            return (str(label).lower() if label else None), conf
        return str(best).lower(), 0.5
    return None, 0.0


def pitch_to_gender_hint(pitch: str | None) -> tuple[str | None, float]:
    if not pitch:
        return None, 0.0
    g = _PITCH_GENDER_HINT.get(pitch.lower())
    if not g:
        return None, 0.0
    return g, 0.45  # capped — never authoritative


# ── Vendor clients ───────────────────────────────────────────────────────────


class InworldVoiceProfileClient:
    """Streaming WS → age + pitch + emotion (not gender)."""

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str = "inworld/inworld-stt-1",
        top_n: int = 3,
        language: str = "en-US",
        age_conf_min: float = 0.6,
        on_update: Callable[[dict], None] | None = None,
    ):
        self.api_key = api_key
        self.model_id = model_id
        self.top_n = top_n
        self.language = language
        self.age_conf_min = age_conf_min
        self.on_update = on_update
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=64)
        self._task: asyncio.Task | None = None
        self._closed = False
        self.best_age: tuple[str | None, float] = (None, 0.0)
        self.best_pitch: tuple[str | None, float] = (None, 0.0)
        self.best_emotion: tuple[str | None, float] = (None, 0.0)
        self.best_accent: tuple[str | None, float] = (None, 0.0)
        self.best_style: tuple[str | None, float] = (None, 0.0)
        self.raw_last: dict = {}
        self.age_locked = False

    def start(self) -> None:
        if not self.api_key or self._task:
            return
        self._task = asyncio.create_task(self._run(), name="inworld_voice_profile")

    def offer_pcm(self, pcm: bytes) -> None:
        if self._closed or not pcm:
            return
        try:
            self._queue.put_nowait(pcm)
        except asyncio.QueueFull:
            try:
                _ = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(pcm)
            except asyncio.QueueFull:
                pass

    async def aclose(self) -> None:
        self._closed = True
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def _apply_voice_profile(self, vp: dict) -> None:
        if not isinstance(vp, dict):
            return
        self.raw_last = vp
        age, ac = _top_label(vp.get("age"))
        if age and age != "unclear" and ac >= self.best_age[1]:
            self.best_age = (age, ac)
            if ac >= self.age_conf_min:
                self.age_locked = True
        pitch, pc = _top_label(vp.get("pitch"))
        if pitch and pc >= self.best_pitch[1]:
            self.best_pitch = (pitch, pc)
        emo, ec = _top_label(vp.get("emotion"))
        if emo and ec >= self.best_emotion[1]:
            self.best_emotion = (emo, ec)
        acc, aacc = _top_label(vp.get("accent"))
        if acc and aacc >= self.best_accent[1]:
            self.best_accent = (acc, aacc)
        style, sc = _top_label(vp.get("vocalStyle") or vp.get("vocal_style"))
        if style and sc >= self.best_style[1]:
            self.best_style = (style, sc)
        if self.on_update:
            try:
                self.on_update(
                    {
                        "age": self.best_age,
                        "pitch": self.best_pitch,
                        "emotion": self.best_emotion,
                    }
                )
            except Exception:
                pass

    def _parse_message(self, raw: str | bytes) -> None:
        try:
            data = json.loads(raw)
        except Exception:
            return
        # Various response shapes
        vp = data.get("voiceProfile") or data.get("voice_profile")
        if not vp and isinstance(data.get("result"), dict):
            vp = data["result"].get("voiceProfile") or data["result"].get("voice_profile")
        if not vp and isinstance(data.get("transcription"), dict):
            vp = data["transcription"].get("voiceProfile")
        if vp:
            self._apply_voice_profile(vp)

    async def _run(self) -> None:
        import websockets

        headers = {"Authorization": f"Basic {self.api_key}"}
        try:
            async with websockets.connect(
                INWORLD_WS_URL,
                additional_headers=headers,
                max_size=8 * 1024 * 1024,
                open_timeout=8,
                close_timeout=2,
            ) as ws:
                config_msg = {
                    "transcribeConfig": {
                        "modelId": self.model_id,
                        "language": self.language,
                        "audioEncoding": "LINEAR16",
                        "sampleRateHertz": 16000,
                        "numberOfChannels": 1,
                        "voiceProfileConfig": {
                            "enableVoiceProfile": True,
                            "topN": int(self.top_n),
                        },
                        "inworldConfig": {"voiceProfileThreshold": 0.5},
                    }
                }
                await ws.send(json.dumps(config_msg))
                logger.info("[SPEAKER] Inworld WS connected (voice profile on)")

                async def _sender():
                    while not self._closed:
                        chunk = await self._queue.get()
                        if chunk is None:
                            try:
                                await ws.send(json.dumps({"closeStream": True}))
                            except Exception:
                                pass
                            break
                        b64 = base64.b64encode(chunk).decode("ascii")
                        try:
                            await ws.send(json.dumps({"audioChunk": {"content": b64}}))
                        except Exception:
                            # alternate field names
                            try:
                                await ws.send(json.dumps({"audioContent": b64}))
                            except Exception as exc:
                                logger.debug("[SPEAKER] Inworld send failed: %s", exc)
                                break

                send_task = asyncio.create_task(_sender())
                try:
                    async for msg in ws:
                        if self._closed:
                            break
                        self._parse_message(msg)
                        if self.age_locked:
                            # keep socket briefly for pitch; then stop sending
                            break
                finally:
                    send_task.cancel()
                    try:
                        await send_task
                    except (asyncio.CancelledError, Exception):
                        pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[SPEAKER] Inworld WS error: %s", exc)


class SmallestGenderClient:
    """Buffer non-silent PCM → one pre-recorded Pulse POST for gender (+ optional emotion)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "pulse",
        language: str = "en",
        window_s: float = 6.0,
        deadline_s: float = 7.0,
        silence_rms_floor: float = 350.0,
        gender_provider_prior: float = 0.8,
        emotion_detection: bool = True,
        sample_rate: int = 16000,
    ):
        self.api_key = api_key
        self.model = model
        self.language = language
        self.window_s = window_s
        self.deadline_s = deadline_s
        self.silence_rms_floor = silence_rms_floor
        self.gender_provider_prior = gender_provider_prior
        self.emotion_detection = emotion_detection
        self.sample_rate = sample_rate
        self._buf = bytearray()
        self._speech_samples = 0
        self._started = time.monotonic()
        self._fired = False
        self.result_gender: str | None = None
        self.result_confidence = 0.0
        self.result_age: str | None = None  # may be absent on Pulse today
        self.result_emotion: str | None = None
        self.raw: dict = {}
        self._task: asyncio.Task | None = None

    @property
    def speech_seconds(self) -> float:
        return self._speech_samples / float(self.sample_rate)

    def offer_pcm(self, pcm: bytes, rms: float) -> None:
        if self._fired or not pcm:
            return
        if rms < self.silence_rms_floor:
            return
        self._buf.extend(pcm)
        self._speech_samples += len(pcm) // 2  # int16
        # Cap buffer to deadline_s * rate * 2
        max_bytes = int(self.deadline_s * self.sample_rate * 2)
        if len(self._buf) > max_bytes:
            excess = len(self._buf) - max_bytes
            del self._buf[:excess]
            self._speech_samples = len(self._buf) // 2

    def should_fire(self) -> bool:
        if self._fired or not self.api_key:
            return False
        if self.speech_seconds >= self.window_s:
            return True
        if (time.monotonic() - self._started) >= self.deadline_s and self.speech_seconds >= 1.5:
            return True
        return False

    def fire_if_ready(self) -> None:
        if not self.should_fire() or self._task:
            return
        self._fired = True
        pcm = bytes(self._buf)
        self._buf.clear()
        self._task = asyncio.create_task(self._post(pcm), name="smallest_gender")

    async def force_fire(self) -> None:
        if self._fired:
            if self._task:
                try:
                    await self._task
                except Exception:
                    pass
            return
        self._fired = True
        pcm = bytes(self._buf)
        self._buf.clear()
        if pcm and self.api_key:
            await self._post(pcm)

    async def aclose(self) -> None:
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3.0)
            except Exception:
                self._task.cancel()
                try:
                    await self._task
                except Exception:
                    pass

    async def _post(self, pcm: bytes) -> None:
        from stt_audio import pcm_to_wav_bytes

        if not pcm:
            return
        wav = pcm_to_wav_bytes(pcm, sample_rate=self.sample_rate)
        params = {
            "model": self.model,
            "language": self.language,
            "gender_detection": "true",
        }
        # Age not supported on current Pulse API — omit age_detection
        if self.emotion_detection:
            params["emotion_detection"] = "true"

        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            import httpx

            async with httpx.AsyncClient(timeout=2.5) as client:
                # multipart file form (docs) — also try raw WAV body as fallback
                files = {"file": ("audio.wav", wav, "audio/wav")}
                data = {k: v for k, v in params.items() if k != "model"}
                url = f"{SMALLEST_STT_URL}?model={self.model}"
                resp = await client.post(url, headers=headers, files=files, data=data)
                if resp.status_code >= 400:
                    # fallback: raw body
                    resp = await client.post(
                        url,
                        headers={**headers, "Content-Type": "audio/wav"},
                        content=wav,
                        params=params,
                    )
                resp.raise_for_status()
                payload = resp.json()
        except Exception as exc:
            logger.warning("[SPEAKER] Smallest gender POST failed: %s", exc)
            return

        self.raw = payload if isinstance(payload, dict) else {"raw": payload}
        gender = (
            self.raw.get("gender")
            or (self.raw.get("result") or {}).get("gender")
            or (self.raw.get("data") or {}).get("gender")
        )
        if gender:
            g = str(gender).lower().strip()
            if g in ("male", "female", "m", "f"):
                self.result_gender = "male" if g.startswith("m") else "female"
                self.result_confidence = float(self.gender_provider_prior)
        # optional fields if API adds them later
        age = self.raw.get("age") or self.raw.get("age_group")
        if age:
            self.result_age = str(age).lower()
        emo = self.raw.get("emotion")
        if emo:
            self.result_emotion = str(emo).lower()
        logger.info(
            "[SPEAKER] Smallest gender=%s conf=%.2f speech_s=%.2f",
            self.result_gender,
            self.result_confidence,
            self.speech_seconds,
        )


# ── Controller ───────────────────────────────────────────────────────────────


class SpeakerProfiler:
    """Per-call controller: audio tee → Inworld + Smallest → SpeakerProfile."""

    def __init__(
        self,
        call_cfg: Any,
        live_config: dict,
        get_secret: Callable | None = None,
        *,
        window_s: float | None = None,
        deadline_s: float | None = None,
    ):
        self.live_config = live_config
        self.cfg = _cfg_block(live_config)
        self.window_s = float(window_s if window_s is not None else self.cfg.get("window_s", 6.0))
        self.deadline_s = float(
            deadline_s if deadline_s is not None else self.cfg.get("deadline_s", 7.0)
        )
        self.age_conf_min = float(self.cfg.get("age_conf_min", 0.6))
        self.silence_floor = float(self.cfg.get("silence_rms_floor", 350))
        self.inject_into_llm = bool(self.cfg.get("inject_into_llm", True))
        self.store_in_analytics = bool(self.cfg.get("store_in_analytics", True))

        inworld_key = _resolve_key(
            "INWORLD_API_KEY", call_cfg, "inworld_api_key", get_secret
        )
        smallest_key = _resolve_key(
            "SMALLEST_API_KEY", call_cfg, "smallest_api_key", get_secret
        )

        self.inworld = InworldVoiceProfileClient(
            api_key=inworld_key,
            model_id=str(self.cfg.get("inworld_model_id") or "inworld/inworld-stt-1"),
            top_n=int(self.cfg.get("inworld_top_n") or 3),
            language="en-US",
            age_conf_min=self.age_conf_min,
            on_update=self._on_inworld_update,
        ) if inworld_key else None

        self.smallest = SmallestGenderClient(
            api_key=smallest_key,
            model=str(self.cfg.get("smallest_model") or "pulse"),
            language=str(self.cfg.get("language") or "en"),
            window_s=self.window_s,
            deadline_s=self.deadline_s,
            silence_rms_floor=self.silence_floor,
            gender_provider_prior=float(self.cfg.get("gender_provider_prior", 0.8)),
            emotion_detection=bool(self.cfg.get("emotion_detection", True)),
        ) if smallest_key else None

        self._frame_q: asyncio.Queue = asyncio.Queue(maxsize=48)
        self._worker: asyncio.Task | None = None
        self._watchdog: asyncio.Task | None = None
        self._t0 = time.monotonic()
        self.done = False
        self.profile = SpeakerProfile()
        self._injected = False

        if not inworld_key and not smallest_key:
            logger.warning(
                "[SPEAKER] No INWORLD_API_KEY / SMALLEST_API_KEY — profiler idle"
            )

    def start(self) -> None:
        if self._worker:
            return
        if self.inworld:
            self.inworld.start()
        self._worker = asyncio.create_task(self._process_frames(), name="speaker_profiler")
        self._watchdog = asyncio.create_task(self._deadline_watch(), name="speaker_deadline")
        logger.info(
            "[SPEAKER] Profiler started (window=%.1fs deadline=%.1fs inworld=%s smallest=%s)",
            self.window_s,
            self.deadline_s,
            bool(self.inworld),
            bool(self.smallest),
        )

    def offer_frame(self, frame: Any) -> None:
        """Non-blocking; drops if queue full. Never blocks Soniox STT path."""
        if self.done:
            return
        try:
            self._frame_q.put_nowait(frame)
        except asyncio.QueueFull:
            try:
                _ = self._frame_q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._frame_q.put_nowait(frame)
            except asyncio.QueueFull:
                pass

    async def _process_frames(self) -> None:
        from stt_audio import frame_to_pcm16_mono, pcm_rms

        while not self.done:
            try:
                frame = await asyncio.wait_for(self._frame_q.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if self.smallest:
                    self.smallest.fire_if_ready()
                continue
            except asyncio.CancelledError:
                break
            try:
                pcm = frame_to_pcm16_mono(frame, target_rate=16000)
            except Exception:
                continue
            if not pcm:
                continue
            rms = pcm_rms(pcm)
            if self.inworld and not self.inworld.age_locked:
                self.inworld.offer_pcm(pcm)
            if self.smallest and not self.smallest._fired:
                self.smallest.offer_pcm(pcm, rms)
                self.smallest.fire_if_ready()
            self._reconcile(provisional=True)
            if self._ready_to_finalize():
                await self._finalize()
                break

    def _on_inworld_update(self, _payload: dict) -> None:
        self._reconcile(provisional=True)

    def _ready_to_finalize(self) -> bool:
        age_ok = bool(self.profile.age_group and self.profile.age_confidence >= self.age_conf_min)
        gender_ok = bool(
            self.profile.gender
            and self.profile.gender_source == "smallest"
            and self.profile.gender_confidence > 0
        )
        return age_ok and gender_ok

    def _reconcile(self, *, provisional: bool) -> None:
        # Age from Inworld
        if self.inworld:
            age, ac = self.inworld.best_age
            if age and age != "unclear":
                self.profile.age_group = age
                self.profile.age_confidence = ac
                self.profile.age_source = "inworld"
            pitch, _ = self.inworld.best_pitch
            self.profile.pitch = pitch
            emo, _ = self.inworld.best_emotion
            if emo:
                self.profile.emotion = emo
            acc, _ = self.inworld.best_accent
            if acc:
                self.profile.accent = acc
            style, _ = self.inworld.best_style
            if style:
                self.profile.vocal_style = style

        # Gender: Smallest authoritative; pitch hint provisional
        if self.smallest and self.smallest.result_gender:
            self.profile.gender = self.smallest.result_gender
            self.profile.gender_confidence = self.smallest.result_confidence
            self.profile.gender_source = "smallest"
            if self.smallest.result_emotion and not self.profile.emotion:
                self.profile.emotion = self.smallest.result_emotion
            # Optional Smallest age if ever returned
            if self.smallest.result_age and (
                not self.profile.age_group
                or self.profile.age_confidence < 0.5
            ):
                self.profile.age_group = self.smallest.result_age
                self.profile.age_confidence = max(self.profile.age_confidence, 0.55)
                self.profile.age_source = (
                    "merged" if self.profile.age_source == "inworld" else "smallest"
                )
        elif self.profile.gender_source != "smallest":
            hint, hconf = pitch_to_gender_hint(self.profile.pitch)
            if hint:
                self.profile.gender = hint
                self.profile.gender_confidence = min(hconf, 0.55)
                self.profile.gender_source = "pitch_hint"

        self.profile.finalized = not provisional and self.profile.finalized
        self.profile.raw = {
            "inworld": getattr(self.inworld, "raw_last", {}) if self.inworld else {},
            "smallest": getattr(self.smallest, "raw", {}) if self.smallest else {},
        }
        # publish provisional for consumers
        self.live_config["_speaker_profile_result"] = self.profile.to_public_dict()

    async def _deadline_watch(self) -> None:
        try:
            await asyncio.sleep(self.deadline_s)
            if not self.done:
                logger.info("[SPEAKER] Deadline %.1fs — finalizing with available data", self.deadline_s)
                if self.smallest:
                    await self.smallest.force_fire()
                await self._finalize()
        except asyncio.CancelledError:
            pass

    async def _finalize(self) -> None:
        if self.done:
            return
        self.done = True
        if self.smallest:
            await self.smallest.force_fire()
        self._reconcile(provisional=False)
        self.profile.finalized = True
        self.profile.finalized_at_s = time.monotonic() - self._t0
        self.live_config["_speaker_profile_result"] = self.profile.to_public_dict()
        logger.info(
            "[SPEAKER] FINAL age=%s(%.2f/%s) gender=%s(%.2f/%s) pitch=%s emotion=%s t=%.2fs",
            self.profile.age_group,
            self.profile.age_confidence,
            self.profile.age_source,
            self.profile.gender,
            self.profile.gender_confidence,
            self.profile.gender_source,
            self.profile.pitch,
            self.profile.emotion,
            self.profile.finalized_at_s,
        )
        # release vendor sockets
        await self._close_vendors()

    async def _close_vendors(self) -> None:
        if self.inworld:
            try:
                await self.inworld.aclose()
            except Exception:
                pass
        if self.smallest:
            try:
                await self.smallest.aclose()
            except Exception:
                pass

    async def aclose(self) -> None:
        self.done = True
        if self._watchdog:
            self._watchdog.cancel()
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except (asyncio.CancelledError, Exception):
                pass
        await self._close_vendors()


def maybe_start_speaker_profiler(
    live_config: dict,
    call_cfg: Any,
    get_secret: Callable | None = None,
) -> SpeakerProfiler | None:
    if not speaker_profiling_enabled(live_config):
        return None
    sp = SpeakerProfiler(call_cfg, live_config, get_secret)
    live_config["_speaker_profile"] = sp
    sp.start()
    return sp

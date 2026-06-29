"""Buenavista private voice channel: wake-phrase STT (AssemblyAI), BV LLM, Cartesia TTS playback."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import math
import os
import re
import tempfile
import threading
import time
import wave
from array import array
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional
from urllib.parse import urlencode

import aiohttp
import discord

if TYPE_CHECKING:
    from bubbot.runtime.buenavista_extension import BuenavistaExtension


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


ASSEMBLYAI_API_KEY = (os.getenv("ASSEMBLYAI_API_KEY") or "").strip()
ASSEMBLYAI_BASE_URL = (
    os.getenv("ASSEMBLYAI_BASE_URL") or "https://api.eu.assemblyai.com"
).strip().rstrip("/")
ASSEMBLYAI_STREAMING_URL = (
    os.getenv("ASSEMBLYAI_STREAMING_URL") or "wss://streaming.eu.assemblyai.com/v3/ws"
).strip()
ASSEMBLYAI_STREAMING_MODEL = (os.getenv("ASSEMBLYAI_STREAMING_MODEL") or "u3-rt-pro").strip()
ASSEMBLYAI_STREAMING_PROMPT = (
    os.getenv("ASSEMBLYAI_STREAMING_PROMPT")
    or "Casual Discord voice chat with a bot named Bub. Users may say hey bub before a short command."
).strip()
CARTESIA_API_KEY = (os.getenv("CARTESIA_API_KEY") or "").strip()
CARTESIA_BASE_URL = (os.getenv("CARTESIA_BASE_URL") or "https://api.cartesia.ai").strip().rstrip("/")
CARTESIA_API_VERSION = (os.getenv("CARTESIA_API_VERSION") or "2026-03-01").strip()
CARTESIA_TTS_MODEL = (os.getenv("CARTESIA_TTS_MODEL") or "sonic-3.5").strip()
CARTESIA_VOICE_ID = (
    os.getenv("CARTESIA_VOICE_ID") or "79f8b5fb-2cc8-479a-80df-29f7a7cf1a3e"
).strip()
CARTESIA_TTS_SAMPLE_RATE = max(8000, _env_int("CARTESIA_TTS_SAMPLE_RATE", 44100))
CARTESIA_TTS_BIT_RATE = max(32000, _env_int("CARTESIA_TTS_BIT_RATE", 128000))
BUB_VOICE_WAKE_PHRASE = (os.getenv("BUB_VOICE_WAKE_PHRASE") or "alexa").strip()
BUB_VOICE_WAKE_ALIASES = [
    alias.strip()
    for alias in (os.getenv("BUB_VOICE_WAKE_ALIASES") or "hey bub,hey bob,hey bug,hey bud,aibo,he was here").split(",")
    if alias.strip()
]
BUB_VOICE_DEBUG = _env_bool("BUB_VOICE_DEBUG", False)
BUB_VOICE_LISTEN_ALL_USERS = _env_bool("BUB_VOICE_LISTEN_ALL_USERS", True)
BUB_VOICE_WAKE_ENGINE = (os.getenv("BUB_VOICE_WAKE_ENGINE") or "openwakeword").strip().lower()
OPENWAKEWORD_MODEL = (os.getenv("OPENWAKEWORD_MODEL") or "alexa").strip()
OPENWAKEWORD_THRESHOLD = max(0.05, min(0.99, float(os.getenv("OPENWAKEWORD_THRESHOLD", "0.45"))))
OPENWAKEWORD_INFERENCE_FRAMEWORK = (os.getenv("OPENWAKEWORD_INFERENCE_FRAMEWORK") or "onnx").strip().lower()
OPENWAKEWORD_VAD_THRESHOLD = max(0.0, min(1.0, float(os.getenv("OPENWAKEWORD_VAD_THRESHOLD", "0"))))

DISCORD_PCM_SAMPLE_RATE = 48_000
DISCORD_PCM_CHANNELS = 2
DISCORD_PCM_SAMPLE_WIDTH = 2
ASSEMBLYAI_PCM_SAMPLE_RATE = 16_000
ASSEMBLYAI_PCM_CHANNELS = 1
ASSEMBLYAI_STREAM_CHUNK_MS = max(50, min(1000, _env_int("ASSEMBLYAI_STREAM_CHUNK_MS", 100)))
ASSEMBLYAI_STREAM_GAP_SEC = max(0.0, float(os.getenv("ASSEMBLYAI_STREAM_GAP_SEC", "3")))
ASSEMBLYAI_CONCURRENT_BACKOFF_SEC = max(1.0, float(os.getenv("ASSEMBLYAI_CONCURRENT_BACKOFF_SEC", "10")))
ASSEMBLYAI_MAX_CONCURRENT_STREAMS = max(1, _env_int("ASSEMBLYAI_MAX_CONCURRENT_STREAMS", 1))
_ASSEMBLYAI_STREAM_SEMAPHORE = asyncio.Semaphore(ASSEMBLYAI_MAX_CONCURRENT_STREAMS)

SILENCE_TIMEOUT_SEC = max(0.35, float(os.getenv("BUB_VOICE_SILENCE_TIMEOUT_SEC", "0.85")))
MIN_UTTERANCE_SEC = max(0.2, float(os.getenv("BUB_VOICE_MIN_UTTERANCE_SEC", "0.2")))
MAX_UTTERANCE_SEC = max(3.0, float(os.getenv("BUB_VOICE_MAX_UTTERANCE_SEC", "12")))
MAX_TTS_CHARS = max(80, _env_int("BUB_VOICE_MAX_TTS_CHARS", 600))
USER_COOLDOWN_SEC = max(2, _env_int("BUB_VOICE_USER_COOLDOWN_SEC", 8))
BUB_VOICE_QUERY_GRACE_SEC = max(0.0, float(os.getenv("BUB_VOICE_QUERY_GRACE_SEC", "10")))
BUB_VOICE_QUERY_TIMEOUT_SEC = max(3.0, float(os.getenv("BUB_VOICE_QUERY_TIMEOUT_SEC", "12")))
BUB_VOICE_ACK_SOUND_PATH = (os.getenv("BUB_VOICE_ACK_SOUND_PATH") or "").strip()
VOICE_RMS_THRESHOLD = max(0, _env_int("BUB_VOICE_RMS_THRESHOLD", 220))
OPENWAKEWORD_FRAME_SAMPLES = 1280
OPENWAKEWORD_WAKE_FLUSH_SEC = max(0.05, float(os.getenv("OPENWAKEWORD_WAKE_FLUSH_SEC", "0.2")))

_VOICE_PHASE_SCANNING = "scanning_wake"
_VOICE_PHASE_ACK = "playing_ack"
_VOICE_PHASE_GRACE = "awaiting_query"
_VOICE_PHASE_CAPTURE = "capturing_query"
MIN_PCM_BYTES = int(
    DISCORD_PCM_SAMPLE_RATE * DISCORD_PCM_CHANNELS * DISCORD_PCM_SAMPLE_WIDTH * MIN_UTTERANCE_SEC
)
MAX_PCM_BYTES = int(
    DISCORD_PCM_SAMPLE_RATE * DISCORD_PCM_CHANNELS * DISCORD_PCM_SAMPLE_WIDTH * MAX_UTTERANCE_SEC
)


def _assemblyai_keyterms() -> list[str]:
    terms = [
        BUB_VOICE_WAKE_PHRASE,
        "bub",
        "bob",
        *BUB_VOICE_WAKE_ALIASES,
    ]
    extra = [
        term.strip()
        for term in (os.getenv("ASSEMBLYAI_KEYTERMS") or "").split(",")
        if term.strip()
    ]
    seen: set[str] = set()
    result: list[str] = []
    for term in terms + extra:
        key = term.lower()
        if not term or key in seen:
            continue
        seen.add(key)
        result.append(term)
    return result


ASSEMBLYAI_KEYTERMS = _assemblyai_keyterms()


def parse_voice_nl_action(content_lower: str) -> Optional[str]:
    """Return join|leave|status when content matches a Buenavista voice NL phrase."""
    text = str(content_lower or "").strip()
    if not text:
        return None
    if re.search(r"\b(?:join\s+voice|voice\s+join)\b", text) or re.search(r"\bbv\s+voice\s+join\b", text):
        return "join"
    if re.search(r"\b(?:leave\s+voice|voice\s+leave)\b", text) or re.search(r"\bbv\s+voice\s+leave\b", text):
        return "leave"
    if re.search(r"\bvoice\s+status\b", text) or re.search(r"\bbv\s+voice\s+status\b", text):
        return "status"
    return None


def voice_feature_flags(*, buenavista_enabled: bool, bv_llm_enabled: bool, bv_voice_enabled: bool) -> tuple[bool, str]:
    if not buenavista_enabled:
        return False, "Buenavista is disabled (BUB_ENABLE_BUENAVISTA=0)."
    if not bv_llm_enabled:
        return False, "Buenavista LLM is disabled (BUB_BV_LLM_ENABLED=0)."
    if not bv_voice_enabled:
        return False, "Buenavista voice is disabled (BUB_BV_VOICE_ENABLED=0)."
    if not ASSEMBLYAI_API_KEY:
        return False, "ASSEMBLYAI_API_KEY is not configured."
    if not CARTESIA_API_KEY:
        return False, "CARTESIA_API_KEY is not configured."
    if not CARTESIA_VOICE_ID:
        return False, "CARTESIA_VOICE_ID is not configured."
    return True, ""


def normalize_transcript(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def extract_wake_prompt(transcript: str, wake_phrase: str = BUB_VOICE_WAKE_PHRASE) -> Optional[str]:
    raw = normalize_transcript(transcript)
    wake_phrases = [wake_phrase, *BUB_VOICE_WAKE_ALIASES]
    normalized_wakes = [normalize_transcript(phrase).lower() for phrase in wake_phrases if normalize_transcript(phrase)]
    if not raw or not normalized_wakes:
        return None
    lowered = raw.lower()
    for wake in normalized_wakes:
        if wake not in lowered:
            continue
        start = lowered.index(wake)
        prompt = raw[start + len(wake) :].strip(" ,.-:;")
        return prompt or None
    return None


def pcm_to_wav_bytes(pcm: bytes, *, sample_rate: int = DISCORD_PCM_SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(DISCORD_PCM_CHANNELS)
        wav_file.setsampwidth(DISCORD_PCM_SAMPLE_WIDTH)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


_ACK_CHIME_CACHE: Optional[str] = None


def voice_ack_sound_path() -> str:
    """Return path to acknowledgement chime (env override or generated two-tone ding)."""
    global _ACK_CHIME_CACHE
    if BUB_VOICE_ACK_SOUND_PATH and os.path.isfile(BUB_VOICE_ACK_SOUND_PATH):
        return BUB_VOICE_ACK_SOUND_PATH
    if _ACK_CHIME_CACHE and os.path.isfile(_ACK_CHIME_CACHE):
        return _ACK_CHIME_CACHE

    sample_rate = DISCORD_PCM_SAMPLE_RATE
    tones = ((880.0, 0.11), (1174.0, 0.14))
    gap_sec = 0.04
    samples = array("h")
    for tone_index, (frequency, duration_sec) in enumerate(tones):
        if tone_index:
            samples.extend([0] * int(sample_rate * gap_sec))
        total = int(sample_rate * duration_sec)
        for index in range(total):
            t = index / sample_rate
            fade = min(1.0, index / max(1, int(sample_rate * 0.008)), (total - index) / max(1, int(sample_rate * 0.02)))
            value = int(9000 * fade * math.sin(2 * math.pi * frequency * t))
            sample = max(-32767, min(32767, value))
            samples.append(sample)
            samples.append(sample)
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    temp_file.write(pcm_to_wav_bytes(samples.tobytes(), sample_rate=sample_rate))
    temp_file.close()
    _ACK_CHIME_CACHE = temp_file.name
    return temp_file.name


def discord_pcm_to_assemblyai_pcm(pcm: bytes) -> bytes:
    """Convert Discord 48 kHz stereo PCM16 into AssemblyAI-friendly 16 kHz mono PCM16."""
    frame_bytes = DISCORD_PCM_CHANNELS * DISCORD_PCM_SAMPLE_WIDTH
    usable = len(pcm) - (len(pcm) % frame_bytes)
    if usable <= 0:
        return b""
    samples = array("h")
    samples.frombytes(pcm[:usable])
    mono = array("h")
    for index in range(0, len(samples) - 1, 2):
        mono.append(int((samples[index] + samples[index + 1]) / 2))
    if DISCORD_PCM_SAMPLE_RATE == ASSEMBLYAI_PCM_SAMPLE_RATE:
        return mono.tobytes()
    step = max(1, round(DISCORD_PCM_SAMPLE_RATE / ASSEMBLYAI_PCM_SAMPLE_RATE))
    downsampled = array("h", mono[::step])
    return downsampled.tobytes()


def pcm_rms(pcm: bytes) -> float:
    if len(pcm) < DISCORD_PCM_SAMPLE_WIDTH:
        return 0.0
    usable = len(pcm) - (len(pcm) % DISCORD_PCM_SAMPLE_WIDTH)
    samples = array("h")
    samples.frombytes(pcm[:usable])
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


def is_voice_pcm(pcm: bytes) -> bool:
    return bool(pcm and (VOICE_RMS_THRESHOLD <= 0 or pcm_rms(pcm) >= VOICE_RMS_THRESHOLD))


class AssemblyAIError(RuntimeError):
    pass


class WakeWordError(RuntimeError):
    pass


class CartesiaError(RuntimeError):
    pass


def _openwakeword_version() -> str:
    try:
        import importlib.metadata as metadata

        return metadata.version("openwakeword")
    except Exception:
        return "unknown"


class OpenWakeWordDetector:
    def __init__(self):
        self._model = None
        self._np = None
        self._user_pending: dict[int, bytes] = {}
        self._user_best: dict[int, float] = {}
        self._active_user_id: Optional[int] = None
        self._lock = threading.RLock()

    @staticmethod
    def _download_models(model_name: str) -> None:
        try:
            from openwakeword.utils import download_models
        except ImportError as exc:
            raise WakeWordError(
                f"openWakeWord {_openwakeword_version()} is too old or broken (need >= 0.6.0). "
                "On the bot host: .venv/bin/pip install -U 'openwakeword>=0.6.0,<0.7' && "
                ".venv/bin/pip install onnxruntime tqdm scipy scikit-learn requests numpy"
            ) from exc
        model_key = model_name.replace(" ", "_")
        try:
            download_models([model_key])
        except TypeError:
            download_models()

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            import numpy as np
            from openwakeword.model import Model
        except Exception as exc:
            raise WakeWordError(f"openWakeWord is not installed or could not import: {exc}") from exc
        self._download_models(OPENWAKEWORD_MODEL)
        self._model = Model(
            wakeword_models=[OPENWAKEWORD_MODEL],
            inference_framework=OPENWAKEWORD_INFERENCE_FRAMEWORK,
            vad_threshold=OPENWAKEWORD_VAD_THRESHOLD,
        )
        self._np = np
        self._prime_model_context()
        return self._model

    def _prime_model_context(self) -> None:
        if self._model is None or self._np is None:
            return
        silence = self._np.zeros(OPENWAKEWORD_FRAME_SAMPLES, dtype=self._np.int16)
        # openWakeWord suppresses the first few frames after reset; consume them with silence.
        for _ in range(6):
            try:
                self._model.predict(silence)
            except Exception:
                break

    def _ensure_model(self):
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                return self._load_model()
            except WakeWordError:
                raise
            except Exception as exc:
                raise WakeWordError(f"openWakeWord model initialization failed: {exc}") from exc

    def reset(self) -> None:
        with self._lock:
            self._user_pending.clear()
            self._user_best.clear()
            self._active_user_id = None
            if self._model is not None:
                try:
                    self._model.reset()
                    self._prime_model_context()
                except Exception:
                    pass

    def _switch_user(self, user_id: int) -> None:
        if self._active_user_id == user_id:
            return
        self._active_user_id = user_id

    def _score_prediction(self, prediction, best: float) -> tuple[bool, float]:
        model_key = OPENWAKEWORD_MODEL.replace("_", " ").lower()
        detected = False
        if isinstance(prediction, dict):
            for label, score in prediction.items():
                label_norm = str(label).replace("_", " ").lower()
                if model_key not in label_norm and OPENWAKEWORD_MODEL.lower() not in label_norm:
                    continue
                score_f = float(score or 0.0)
                best = max(best, score_f)
                if score_f >= OPENWAKEWORD_THRESHOLD:
                    detected = True
        return detected, best

    def _feed_audio(self, user_id: int, audio: bytes, *, flush: bool) -> tuple[bool, float]:
        model = self._ensure_model()
        self._switch_user(user_id)
        pending = self._user_pending.get(user_id, b"")
        if audio:
            pending += audio
        frame_bytes = OPENWAKEWORD_FRAME_SAMPLES * DISCORD_PCM_SAMPLE_WIDTH
        best = self._user_best.get(user_id, 0.0)
        detected = False

        while len(pending) >= frame_bytes:
            frame = pending[:frame_bytes]
            pending = pending[frame_bytes:]
            samples = self._np.frombuffer(frame, dtype=self._np.int16)
            try:
                prediction = model.predict(samples)
            except Exception as exc:
                raise WakeWordError(f"openWakeWord prediction failed: {exc}") from exc
            frame_detected, best = self._score_prediction(prediction, best)
            detected = detected or frame_detected

        if flush and pending:
            min_partial = max(DISCORD_PCM_SAMPLE_WIDTH, frame_bytes // 3)
            if len(pending) >= min_partial:
                padded = pending + (b"\x00" * (frame_bytes - len(pending)))
                pending = b""
                samples = self._np.frombuffer(padded, dtype=self._np.int16)
                try:
                    prediction = model.predict(samples)
                except Exception as exc:
                    raise WakeWordError(f"openWakeWord prediction failed: {exc}") from exc
                frame_detected, best = self._score_prediction(prediction, best)
                detected = detected or frame_detected
            else:
                pending = b""

        if pending:
            self._user_pending[user_id] = pending
        else:
            self._user_pending.pop(user_id, None)
        self._user_best[user_id] = best

        if detected:
            self._user_pending.pop(user_id, None)
            self._user_best.pop(user_id, None)
            self.reset()
            self._active_user_id = None
        return detected, best

    def feed(self, user_id: int, pcm: bytes) -> tuple[bool, float]:
        """Stream PCM for one user; keeps per-user frame buffers across chunks."""
        with self._lock:
            audio = discord_pcm_to_assemblyai_pcm(pcm)
            if not audio:
                return False, self._user_best.get(user_id, 0.0)
            return self._feed_audio(user_id, audio, flush=False)

    def flush(self, user_id: int) -> tuple[bool, float]:
        """Score trailing partial frames after the user stops speaking."""
        with self._lock:
            if user_id not in self._user_pending:
                return False, self._user_best.get(user_id, 0.0)
            return self._feed_audio(user_id, b"", flush=True)

    def detect(self, pcm: bytes) -> tuple[bool, float]:
        """One-shot wake check on a buffered clip (used by regressions)."""
        self.reset()
        return self.feed(0, pcm)

    def warmup(self) -> None:
        """Load/download models at session start so the first utterance is not delayed."""
        self._ensure_model()


class AssemblyAIClient:
    def __init__(self, session: aiohttp.ClientSession):
        self._session = session

    async def speech_to_text(self, pcm: bytes) -> str:
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        await queue.put(pcm)
        await queue.put(None)
        return await self.stream_chunks_to_text(queue)

    async def stream_chunks_to_text(self, queue: asyncio.Queue[bytes | None]) -> str:
        if not ASSEMBLYAI_API_KEY:
            raise AssemblyAIError("ASSEMBLYAI_API_KEY is missing")
        params = {
            "sample_rate": ASSEMBLYAI_PCM_SAMPLE_RATE,
            "speech_model": ASSEMBLYAI_STREAMING_MODEL,
        }
        if ASSEMBLYAI_STREAMING_PROMPT:
            params["prompt"] = ASSEMBLYAI_STREAMING_PROMPT
        if ASSEMBLYAI_KEYTERMS:
            params["keyterms_prompt"] = json.dumps(ASSEMBLYAI_KEYTERMS[:100])
        url = f"{ASSEMBLYAI_STREAMING_URL}?{urlencode(params)}"
        chunk_bytes = int(ASSEMBLYAI_PCM_SAMPLE_RATE * ASSEMBLYAI_PCM_CHANNELS * DISCORD_PCM_SAMPLE_WIDTH * ASSEMBLYAI_STREAM_CHUNK_MS / 1000)
        chunk_bytes -= chunk_bytes % DISCORD_PCM_SAMPLE_WIDTH
        min_chunk_bytes = int(ASSEMBLYAI_PCM_SAMPLE_RATE * ASSEMBLYAI_PCM_CHANNELS * DISCORD_PCM_SAMPLE_WIDTH * 0.05)
        final_text = ""
        last_text = ""
        sent_audio = False

        async with _ASSEMBLYAI_STREAM_SEMAPHORE:
            async with self._session.ws_connect(
                url,
                headers={"Authorization": ASSEMBLYAI_API_KEY},
                timeout=30,
                heartbeat=20,
            ) as ws:
                async def send_audio() -> None:
                    nonlocal sent_audio
                    pending = b""
                    try:
                        while True:
                            pcm = await queue.get()
                            if pcm is None:
                                break
                            pending += discord_pcm_to_assemblyai_pcm(pcm)
                            while len(pending) >= chunk_bytes:
                                chunk = pending[:chunk_bytes]
                                pending = pending[chunk_bytes:]
                                await ws.send_bytes(chunk)
                                sent_audio = True
                                await asyncio.sleep(len(chunk) / (ASSEMBLYAI_PCM_SAMPLE_RATE * DISCORD_PCM_SAMPLE_WIDTH))
                        if pending:
                            if len(pending) < min_chunk_bytes:
                                pending = pending + (b"\x00" * (min_chunk_bytes - len(pending)))
                            await ws.send_bytes(pending)
                            sent_audio = True
                            await asyncio.sleep(len(pending) / (ASSEMBLYAI_PCM_SAMPLE_RATE * DISCORD_PCM_SAMPLE_WIDTH))
                        await ws.send_json({"type": "ForceEndpoint"})
                        await ws.send_json({"type": "Terminate"})
                    except Exception:
                        if not ws.closed:
                            await ws.close()
                        raise

                sender = asyncio.create_task(send_audio())
                try:
                    async for message in ws:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            payload = json.loads(message.data)
                            msg_type = payload.get("type")
                            if msg_type == "Turn":
                                text = normalize_transcript(payload.get("transcript") or "")
                                if text:
                                    last_text = text
                                if payload.get("end_of_turn") and text:
                                    final_text = text
                            elif msg_type == "Error":
                                raise AssemblyAIError(
                                    f"Streaming failed ({payload.get('error_code')}): {payload.get('error')}"
                                )
                            elif msg_type == "Termination":
                                break
                        elif message.type == aiohttp.WSMsgType.ERROR:
                            raise AssemblyAIError(f"Streaming websocket error: {ws.exception()}")
                finally:
                    if not sender.done():
                        sender.cancel()
                    try:
                        await sender
                    except asyncio.CancelledError:
                        pass
        if not sent_audio:
            raise AssemblyAIError("STT input audio is empty")
        text = final_text or last_text
        if not text:
            raise AssemblyAIError("STT returned empty transcript")
        return text


class CartesiaClient:
    def __init__(self, session: aiohttp.ClientSession):
        self._session = session

    async def text_to_speech_file(self, text: str) -> str:
        if not CARTESIA_API_KEY:
            raise CartesiaError("CARTESIA_API_KEY is missing")
        if not CARTESIA_VOICE_ID:
            raise CartesiaError("CARTESIA_VOICE_ID is missing")
        clipped = normalize_transcript(text)[:MAX_TTS_CHARS]
        if not clipped:
            raise CartesiaError("TTS text is empty")
        url = f"{CARTESIA_BASE_URL}/tts/bytes"
        headers = {
            "Authorization": f"Bearer {CARTESIA_API_KEY}",
            "Cartesia-Version": CARTESIA_API_VERSION,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "model_id": CARTESIA_TTS_MODEL,
            "transcript": clipped,
            "voice": {"mode": "id", "id": CARTESIA_VOICE_ID},
            "output_format": {
                "container": "mp3",
                "sample_rate": CARTESIA_TTS_SAMPLE_RATE,
                "bit_rate": CARTESIA_TTS_BIT_RATE,
            },
        }
        async with self._session.post(
            url,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as response:
            audio = await response.read()
            if response.status >= 400:
                raise CartesiaError(f"TTS failed ({response.status}): {audio[:240]!r}")
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_file.write(audio)
        temp_file.close()
        return temp_file.name


@dataclass
class _UserBuffer:
    user_id: int
    display_name: str
    chunks: list[bytes] = field(default_factory=list)
    timer_task: Optional[asyncio.Task] = None

    @property
    def byte_count(self) -> int:
        return sum(len(chunk) for chunk in self.chunks)

    def append(self, pcm: bytes) -> None:
        if pcm:
            self.chunks.append(pcm)

    def take_pcm(self) -> bytes:
        data = b"".join(self.chunks)
        self.chunks.clear()
        return data


class BuenavistaVoiceSession:
    def __init__(
        self,
        *,
        guild_id: int,
        text_channel_id: int,
        voice_channel_id: int,
        voice_channel_name: str,
        bot_user_id: int,
        owner_user_id: int,
        owner_display_name: str,
        loop: asyncio.AbstractEventLoop,
        llm_callback: Callable,
        wake_phrase: str = BUB_VOICE_WAKE_PHRASE,
    ):
        self.guild_id = guild_id
        self.text_channel_id = text_channel_id
        self.voice_channel_id = voice_channel_id
        self.voice_channel_name = voice_channel_name
        self.bot_user_id = bot_user_id
        self.owner_user_id = owner_user_id
        self.owner_display_name = owner_display_name
        self.loop = loop
        self.llm_callback = llm_callback
        self.wake_phrase = wake_phrase
        self.voice_client = None
        self.listening = False
        self.speaking = False
        self.processing = False
        self._sink = None
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._assemblyai: Optional[AssemblyAIClient] = None
        self._cartesia: Optional[CartesiaClient] = None
        self._wake_detector: Optional[OpenWakeWordDetector] = None
        self._user_buffers: dict[int, _UserBuffer] = {}
        self._active_stream_user_id: Optional[int] = None
        self._next_stream_allowed_at = 0.0
        self._last_user_ts: dict[int, float] = {}
        self._temp_files: set[str] = set()
        self._joined_at = time.time()
        self.received_voice_chunks = 0
        self.finalized_utterances = 0
        self.stt_attempts = 0
        self.empty_transcripts = 0
        self.wake_misses = 0
        self.stream_backoffs = 0
        self.ignored_other_speakers = 0
        self.local_wake_detections = 0
        self.local_wake_misses = 0
        self.local_wake_errors = 0
        self.last_wake_score = 0.0
        self._local_wake_bypass = False
        self._wake_ready = False
        self._phase = _VOICE_PHASE_SCANNING
        self._active_user_id: Optional[int] = None
        self._active_display_name = ""
        self._query_buffer: Optional[_UserBuffer] = None
        self._grace_task: Optional[asyncio.Task] = None
        self._query_timeout_task: Optional[asyncio.Task] = None
        self._awaiting_query_start = False
        self.ack_chime_plays = 0
        self._wake_scan_lock = asyncio.Lock()
        self._wake_scan_task: Optional[asyncio.Task] = None
        self._wake_pending: list[tuple[int, str, bytes]] = []
        self._wake_capture_pcm: dict[int, bytes] = {}
        self._wake_flush_tasks: dict[int, asyncio.Task] = {}

    async def _ensure_clients(self) -> tuple[AssemblyAIClient, CartesiaClient]:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        if self._assemblyai is None:
            self._assemblyai = AssemblyAIClient(self._http_session)
        if self._cartesia is None:
            self._cartesia = CartesiaClient(self._http_session)
        return self._assemblyai, self._cartesia

    async def _ensure_tts_client(self) -> CartesiaClient:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        if self._cartesia is None:
            self._cartesia = CartesiaClient(self._http_session)
        return self._cartesia

    def _ensure_wake_detector(self) -> OpenWakeWordDetector:
        if self._wake_detector is None:
            self._wake_detector = OpenWakeWordDetector()
        return self._wake_detector

    def _reset_to_scanning(self) -> None:
        if self._grace_task and not self._grace_task.done():
            self._grace_task.cancel()
        self._grace_task = None
        if self._query_timeout_task and not self._query_timeout_task.done():
            self._query_timeout_task.cancel()
        self._query_timeout_task = None
        if self._query_buffer and self._query_buffer.timer_task and not self._query_buffer.timer_task.done():
            self._query_buffer.timer_task.cancel()
        self._query_buffer = None
        self._user_buffers.clear()
        self._active_stream_user_id = None
        self._active_user_id = None
        self._active_display_name = ""
        self._awaiting_query_start = False
        self._phase = _VOICE_PHASE_SCANNING
        self._wake_pending.clear()
        self._wake_capture_pcm.clear()
        for task in self._wake_flush_tasks.values():
            if not task.done():
                task.cancel()
        self._wake_flush_tasks.clear()
        if self._wake_detector is not None:
            self._wake_detector.reset()

    def _schedule_wake_scan(self, user_id: int, display_name: str, pcm: bytes) -> None:
        self._wake_pending.append((user_id, display_name, pcm))
        captured = self._wake_capture_pcm.get(user_id, b"") + pcm
        if len(captured) > MAX_PCM_BYTES:
            captured = captured[-MAX_PCM_BYTES:]
        self._wake_capture_pcm[user_id] = captured
        if self._wake_scan_task is None or self._wake_scan_task.done():
            self._wake_scan_task = self.loop.create_task(self._run_wake_scan_batches())
        self._schedule_wake_flush(user_id, display_name)

    def _schedule_wake_flush(self, user_id: int, display_name: str) -> None:
        old_task = self._wake_flush_tasks.get(user_id)
        if old_task and not old_task.done():
            old_task.cancel()
        self._wake_flush_tasks[user_id] = self.loop.create_task(
            self._wake_flush_after_silence(user_id, display_name)
        )

    async def _wake_flush_after_silence(self, user_id: int, display_name: str) -> None:
        try:
            await asyncio.sleep(OPENWAKEWORD_WAKE_FLUSH_SEC)
        except asyncio.CancelledError:
            return
        if self._phase != _VOICE_PHASE_SCANNING or self._ignore_input():
            return
        await self._scan_wake_flush(user_id, display_name)

    async def _run_wake_scan_batches(self) -> None:
        try:
            while self._wake_pending and self._phase == _VOICE_PHASE_SCANNING and not self._ignore_input():
                batch: list[tuple[int, str, bytes]] = []
                while self._wake_pending:
                    batch.append(self._wake_pending.pop(0))
                by_user: dict[int, tuple[str, bytes]] = {}
                for user_id, display_name, pcm in batch:
                    if user_id in by_user:
                        prev_name, prev_pcm = by_user[user_id]
                        by_user[user_id] = (prev_name, prev_pcm + pcm)
                    else:
                        by_user[user_id] = (display_name, pcm)
                for user_id, (display_name, pcm) in by_user.items():
                    await self._scan_wake_pcm(user_id, display_name, pcm)
                    if self._phase != _VOICE_PHASE_SCANNING:
                        self._wake_pending.clear()
                        return
        except Exception as exc:
            print(
                f"[bv-voice] guild={self.guild_id} wake batch error: {exc}",
                flush=True,
            )
        finally:
            if self._wake_pending and self._phase == _VOICE_PHASE_SCANNING and not self._ignore_input():
                self._wake_scan_task = self.loop.create_task(self._run_wake_scan_batches())

    async def _scan_wake_pcm(
        self,
        user_id: int,
        display_name: str,
        pcm: bytes,
        *,
        flush: bool = False,
    ) -> None:
        if self._phase != _VOICE_PHASE_SCANNING or self._ignore_input():
            return
        if BUB_VOICE_WAKE_ENGINE in {"", "none", "off", "disabled"}:
            self._wake_pending.clear()
            await self._on_wake_detected(user_id, display_name, 1.0)
            return
        if BUB_VOICE_WAKE_ENGINE != "openwakeword":
            return
        if self._local_wake_bypass or not self._wake_ready:
            return
        try:
            detector = self._ensure_wake_detector()
            async with self._wake_scan_lock:
                if flush:
                    detected, score = await asyncio.to_thread(detector.flush, user_id)
                else:
                    detected, score = await asyncio.to_thread(detector.feed, user_id, pcm)
            self.last_wake_score = score
            if BUB_VOICE_DEBUG:
                print(
                    f"[bv-voice] guild={self.guild_id} user={display_name} ({user_id}) "
                    f"local wake model={OPENWAKEWORD_MODEL} "
                    f"detected={'yes' if detected else 'no'} score={score:.3f} "
                    f"flush={'yes' if flush else 'no'}",
                    flush=True,
                )
            if not detected:
                return
            self._wake_pending.clear()
            self._wake_capture_pcm.clear()
            flush_task = self._wake_flush_tasks.pop(user_id, None)
            if flush_task and not flush_task.done():
                flush_task.cancel()
            await self._on_wake_detected(user_id, display_name, score)
        except WakeWordError as exc:
            self.local_wake_errors += 1
            self._wake_pending.clear()
            print(
                f"[bv-voice] guild={self.guild_id} wake scan error: {exc}",
                flush=True,
            )

    async def _scan_wake_flush(self, user_id: int, display_name: str) -> None:
        await self._scan_wake_pcm(user_id, display_name, b"", flush=True)

    async def _warmup_wake_detector(self) -> None:
        if BUB_VOICE_WAKE_ENGINE != "openwakeword":
            self._wake_ready = True
            return
        try:
            detector = self._ensure_wake_detector()
            await asyncio.to_thread(detector.warmup)
            self._wake_ready = True
            print(
                f"[bv-voice] guild={self.guild_id} wake model ready "
                f"model={OPENWAKEWORD_MODEL} threshold={OPENWAKEWORD_THRESHOLD}",
                flush=True,
            )
        except WakeWordError as exc:
            self.local_wake_errors += 1
            self._wake_detector = None
            self._wake_ready = False
            self._local_wake_bypass = True
            print(
                f"[bv-voice] guild={self.guild_id} wake detector error: {exc}",
                flush=True,
            )

    async def _on_wake_detected(self, user_id: int, display_name: str, score: float) -> None:
        if self._phase != _VOICE_PHASE_SCANNING:
            return
        now = time.time()
        if now - self._last_user_ts.get(user_id, 0) < USER_COOLDOWN_SEC:
            return
        self.local_wake_detections += 1
        self.last_wake_score = score
        wake_pcm = self._wake_capture_pcm.pop(user_id, b"")
        self._wake_capture_pcm.clear()
        self._active_user_id = user_id
        self._active_display_name = display_name
        self._active_stream_user_id = user_id
        self._phase = _VOICE_PHASE_ACK
        print(
            f"[bv-voice] wake detected guild={self.guild_id} user={display_name} ({user_id}) "
            f"model={OPENWAKEWORD_MODEL} score={score:.3f}",
            flush=True,
        )
        self.processing = True
        try:
            await self._play_acknowledgement()
        finally:
            self.processing = False
        if self._phase != _VOICE_PHASE_ACK:
            return
        self.listening = True
        self._phase = _VOICE_PHASE_CAPTURE
        self._awaiting_query_start = True
        self._query_buffer = _UserBuffer(user_id=user_id, display_name=display_name)
        if wake_pcm:
            self._query_buffer.append(wake_pcm)
            self._begin_query_capture(user_id, display_name)
            if self._query_buffer.timer_task and not self._query_buffer.timer_task.done():
                self._query_buffer.timer_task.cancel()
            self._query_buffer.timer_task = self.loop.create_task(self._query_silence_timer(user_id))
        if self._awaiting_query_start:
            print(
                f"[bv-voice] guild={self.guild_id} listening for query start "
                f"(up to {BUB_VOICE_QUERY_GRACE_SEC:.1f}s) from {display_name} ({user_id})",
                flush=True,
            )
            if self._grace_task and not self._grace_task.done():
                self._grace_task.cancel()
            self._grace_task = self.loop.create_task(self._query_start_deadline(user_id))
        else:
            print(
                f"[bv-voice] guild={self.guild_id} query capture seeded from wake utterance "
                f"for {display_name} ({user_id})",
                flush=True,
            )

    async def _query_start_deadline(self, user_id: int) -> None:
        try:
            await asyncio.sleep(BUB_VOICE_QUERY_GRACE_SEC)
        except asyncio.CancelledError:
            return
        if (
            self._phase != _VOICE_PHASE_CAPTURE
            or self._active_user_id != user_id
            or not self._awaiting_query_start
        ):
            return
        print(
            f"[bv-voice] guild={self.guild_id} no query started within {BUB_VOICE_QUERY_GRACE_SEC:.1f}s",
            flush=True,
        )
        self._reset_to_scanning()
        self.listening = True

    def _begin_query_capture(self, user_id: int, display_name: str) -> None:
        if not self._awaiting_query_start or self._active_user_id != user_id:
            return
        self._awaiting_query_start = False
        if self._grace_task and not self._grace_task.done():
            self._grace_task.cancel()
        self._grace_task = None
        if self._query_timeout_task and not self._query_timeout_task.done():
            self._query_timeout_task.cancel()
        self._query_timeout_task = self.loop.create_task(self._query_capture_timeout(user_id))
        print(
            f"[bv-voice] guild={self.guild_id} query started from {display_name} ({user_id})",
            flush=True,
        )

    async def _query_capture_timeout(self, user_id: int) -> None:
        try:
            await asyncio.sleep(BUB_VOICE_QUERY_TIMEOUT_SEC)
        except asyncio.CancelledError:
            return
        if self._phase != _VOICE_PHASE_CAPTURE or self._active_user_id != user_id:
            return
        print(
            f"[bv-voice] guild={self.guild_id} query timed out after {BUB_VOICE_QUERY_TIMEOUT_SEC:.1f}s",
            flush=True,
        )
        self._reset_to_scanning()
        self.listening = True

    async def _play_acknowledgement(self) -> None:
        ack_path = voice_ack_sound_path()
        self.ack_chime_plays += 1
        print(f"[bv-voice] guild={self.guild_id} playing acknowledgement chime", flush=True)
        await self._play_audio_file(ack_path, resume_listening=False, playback_timeout=3.0)

    def _ignore_input(self) -> bool:
        return bool(self.speaking or self.processing or not self.listening)

    def enqueue_pcm(self, user: discord.User | discord.Member | None, pcm: bytes) -> None:
        """Thread-safe entry point used by the voice receive sink."""
        if not user or getattr(user, "bot", False):
            return
        user_id = getattr(user, "id", None)
        if user_id is None or user_id == self.bot_user_id:
            return
        if not BUB_VOICE_LISTEN_ALL_USERS and int(user_id) != self.owner_user_id:
            self.ignored_other_speakers += 1
            return
        if not is_voice_pcm(pcm):
            return
        self.received_voice_chunks += 1
        display_name = getattr(user, "display_name", None) or getattr(user, "name", "user")
        self.loop.call_soon_threadsafe(
            self._enqueue_pcm_on_loop,
            int(user_id),
            str(display_name),
            bytes(pcm),
        )

    def _enqueue_pcm_on_loop(self, user_id: int, display_name: str, pcm: bytes) -> None:
        if self._ignore_input():
            return
        if time.monotonic() < self._next_stream_allowed_at:
            self.stream_backoffs += 1
            return

        if self._phase == _VOICE_PHASE_SCANNING:
            self._schedule_wake_scan(user_id, display_name, pcm)
            return

        if self._phase != _VOICE_PHASE_CAPTURE:
            return
        if user_id != self._active_user_id:
            return

        buffer = self._query_buffer
        if buffer is None:
            return
        if buffer.byte_count + len(pcm) > MAX_PCM_BYTES:
            return
        buffer.append(pcm)
        if self._awaiting_query_start:
            self._begin_query_capture(user_id, display_name)
        if buffer.timer_task and not buffer.timer_task.done():
            buffer.timer_task.cancel()
        buffer.timer_task = self.loop.create_task(self._query_silence_timer(user_id))

    async def _query_silence_timer(self, user_id: int) -> None:
        try:
            await asyncio.sleep(SILENCE_TIMEOUT_SEC)
            await self._finalize_query(user_id)
        except asyncio.CancelledError:
            return

    async def _finalize_query(self, user_id: int) -> None:
        if self._phase != _VOICE_PHASE_CAPTURE or self._ignore_input():
            return
        if self._query_timeout_task and not self._query_timeout_task.done():
            self._query_timeout_task.cancel()
            self._query_timeout_task = None
        buffer = self._query_buffer
        if not buffer or buffer.user_id != user_id:
            return
        now = time.time()
        pcm = buffer.take_pcm()
        self._query_buffer = None
        if len(pcm) < MIN_PCM_BYTES:
            if BUB_VOICE_DEBUG:
                print(
                    f"[bv-voice] dropped short query guild={self.guild_id} user={user_id} bytes={len(pcm)}",
                    flush=True,
                )
            self._reset_to_scanning()
            return
        self.finalized_utterances += 1
        self.processing = True
        try:
            stt_client, tts_client = await self._ensure_clients()
            self.stt_attempts += 1
            if BUB_VOICE_DEBUG:
                duration = len(pcm) / (DISCORD_PCM_SAMPLE_RATE * DISCORD_PCM_CHANNELS * DISCORD_PCM_SAMPLE_WIDTH)
                print(
                    f"[bv-voice] stt attempt guild={self.guild_id} user={user_id} "
                    f"duration={duration:.2f}s rms={pcm_rms(pcm):.1f}",
                    flush=True,
                )
            transcript = await stt_client.speech_to_text(pcm)
            prompt = normalize_transcript(transcript)
            print(
                f"[bv-voice] transcript guild={self.guild_id} "
                f"user={buffer.display_name} ({user_id}): {transcript}",
                flush=True,
            )
            if not prompt:
                self.empty_transcripts += 1
                return
            self._last_user_ts[user_id] = now
            reply_text = await self.llm_callback(buffer.display_name, prompt)
            if not reply_text:
                return
            audio_path = await tts_client.text_to_speech_file(reply_text)
            self._temp_files.add(audio_path)
            await self._play_response(audio_path)
        except (AssemblyAIError, CartesiaError) as exc:
            if "empty transcript" in str(exc).lower():
                self.empty_transcripts += 1
            if "too many concurrent sessions" in str(exc).lower():
                self._next_stream_allowed_at = max(
                    self._next_stream_allowed_at,
                    time.monotonic() + ASSEMBLYAI_CONCURRENT_BACKOFF_SEC,
                )
            print(f"[bv-voice] guild={self.guild_id} voice API error: {exc}", flush=True)
        except Exception as exc:
            print(f"[bv-voice] guild={self.guild_id} query error: {exc}", flush=True)
        finally:
            self.processing = False
            self._next_stream_allowed_at = max(
                self._next_stream_allowed_at,
                time.monotonic() + ASSEMBLYAI_STREAM_GAP_SEC,
            )
            self._reset_to_scanning()
            self.listening = True

    async def _play_audio_file(
        self,
        audio_path: str,
        resume_listening: bool = True,
        playback_timeout: Optional[float] = None,
    ) -> None:
        if not self.voice_client or not self.voice_client.is_connected():
            return
        self.speaking = True
        self.listening = False
        if self.voice_client.is_playing():
            self.voice_client.stop()
        loop = self.loop
        done = asyncio.Event()

        def _after_playback(error):
            if error:
                print(f"[bv-voice] playback error guild={self.guild_id}: {error}", flush=True)
            loop.call_soon_threadsafe(done.set)

        source = discord.FFmpegPCMAudio(audio_path)
        self.voice_client.play(source, after=_after_playback)
        try:
            if playback_timeout is None:
                await done.wait()
            else:
                await asyncio.wait_for(done.wait(), timeout=playback_timeout)
        except asyncio.TimeoutError:
            print(
                f"[bv-voice] playback wait timed out guild={self.guild_id} file={os.path.basename(audio_path)}",
                flush=True,
            )
            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.stop()
        finally:
            self.speaking = False
            if resume_listening:
                self.listening = True

    async def _play_response(self, audio_path: str) -> None:
        self._active_stream_user_id = None
        self._next_stream_allowed_at = 0.0
        await self._play_audio_file(audio_path, resume_listening=True)

    async def speak_text_response(self, text: str) -> bool:
        if not self.voice_client or not self.voice_client.is_connected():
            return False
        if self._phase != _VOICE_PHASE_SCANNING or self.processing:
            return False
        reply_text = str(text or "").strip()
        if not reply_text:
            return False
        self.processing = True
        try:
            tts_client = await self._ensure_tts_client()
            audio_path = await tts_client.text_to_speech_file(reply_text)
            self._temp_files.add(audio_path)
            await self._play_response(audio_path)
            return True
        except CartesiaError as exc:
            print(f"[bv-voice] guild={self.guild_id} text-chat TTS error: {exc}", flush=True)
            return False
        except Exception as exc:
            print(f"[bv-voice] guild={self.guild_id} text-chat voice reply error: {exc}", flush=True)
            return False
        finally:
            self.processing = False
            self.listening = True

    async def connect_and_listen(self, channel: discord.VoiceChannel) -> None:
        try:
            from bubbot.features.voice_recv_dave_patch import apply_voice_recv_dave_patch
            apply_voice_recv_dave_patch()
            from discord.ext import voice_recv
        except ImportError as exc:
            raise RuntimeError(
                "discord-ext-voice-recv is not installed. Run `pip install -r requirements.txt` "
                "on the bot host, then restart Bub."
            ) from exc

        logging.getLogger("discord.ext.voice_recv.gateway").setLevel(logging.WARNING)
        logging.getLogger("discord.ext.voice_recv.reader").setLevel(logging.WARNING)
        logging.getLogger("discord.ext.voice_recv.opus").setLevel(logging.ERROR)

        if not discord.opus.is_loaded():
            try:
                discord.opus._load_default()
            except Exception as exc:
                print(f"[bv-voice] opus load warning: {exc}", flush=True)

        self.voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient, reconnect=False)
        session = self

        class _WakeSink(voice_recv.AudioSink):
            def __init__(self):
                super().__init__()

            def wants_opus(self) -> bool:
                return False

            def write(self, user, data):
                session.enqueue_pcm(user, data.pcm)

            def cleanup(self):
                return None

        self._sink = _WakeSink()
        def _after_listen(error):
            if error:
                print(f"[bv-voice] receive stopped guild={self.guild_id}: {error}", flush=True)
                self.loop.call_soon_threadsafe(
                    self.loop.create_task,
                    self._notify_receive_error(error),
                )

        self.voice_client.listen(self._sink, after=_after_listen)
        await self._warmup_wake_detector()
        self.listening = True

    async def _notify_receive_error(self, error) -> None:
        self.listening = False
        channel = None
        if self.voice_client and getattr(self.voice_client, "client", None):
            channel = self.voice_client.client.get_channel(self.text_channel_id)
        if channel is None:
            return
        error_name = error.__class__.__name__
        try:
            await channel.send(
                "Bub joined voice, but voice receive stopped while decoding Discord audio "
                f"({error_name}). Text-to-speech may still work, but spoken `hey bub` input is unavailable in this channel."
            )
        except Exception:
            pass

    async def disconnect(self) -> None:
        self.listening = False
        self._reset_to_scanning()
        for buffer in self._user_buffers.values():
            if buffer.timer_task and not buffer.timer_task.done():
                buffer.timer_task.cancel()
        self._user_buffers.clear()
        if self.voice_client:
            try:
                if self.voice_client.is_playing():
                    self.voice_client.stop()
                await self.voice_client.disconnect(force=True)
            except Exception as exc:
                print(f"[bv-voice] disconnect error guild={self.guild_id}: {exc}", flush=True)
            self.voice_client = None
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        for path in list(self._temp_files):
            try:
                os.remove(path)
            except OSError:
                pass
        self._temp_files.clear()

    def status_lines(self) -> list[str]:
        return [
            f"Guild: {self.guild_id}",
            f"Voice channel: {self.voice_channel_name} ({self.voice_channel_id})",
            f"Voice owner: {self.owner_display_name} ({self.owner_user_id})",
            f"Listen all users: {'yes' if BUB_VOICE_LISTEN_ALL_USERS else 'no'}",
            f"Listening: {'yes' if self.listening else 'no'}",
            f"Speaking: {'yes' if self.speaking else 'no'}",
            f"Processing: {'yes' if self.processing else 'no'}",
            f"Phase: {self._phase}"
            + (" (awaiting query start)" if self._awaiting_query_start else ""),
            f"Query start window: {BUB_VOICE_QUERY_GRACE_SEC:.1f}s",
            f"Query timeout: {BUB_VOICE_QUERY_TIMEOUT_SEC:.1f}s",
            f"Ack chimes played: {self.ack_chime_plays}",
            f"Wake phrase: {self.wake_phrase!r}",
            f"Wake aliases: {', '.join(BUB_VOICE_WAKE_ALIASES) or 'none'}",
            f"Wake engine: {BUB_VOICE_WAKE_ENGINE}",
            f"Local wake model: {OPENWAKEWORD_MODEL}",
            f"Local wake threshold: {OPENWAKEWORD_THRESHOLD}",
            f"Local wake detections: {self.local_wake_detections}",
            f"Local wake misses: {self.local_wake_misses}",
            f"Local wake errors: {self.local_wake_errors}",
            f"Local wake bypass: {'yes' if self._local_wake_bypass else 'no'}",
            f"Last wake score: {self.last_wake_score:.3f}",
            f"STT: AssemblyAI streaming ({ASSEMBLYAI_STREAMING_URL})",
            f"STT model: {ASSEMBLYAI_STREAMING_MODEL}",
            f"TTS: Cartesia ({CARTESIA_BASE_URL})",
            f"TTS model: {CARTESIA_TTS_MODEL}",
            f"TTS voice: {CARTESIA_VOICE_ID}",
            f"Voice chunks: {self.received_voice_chunks}",
            f"Utterances finalized: {self.finalized_utterances}",
            f"STT attempts: {self.stt_attempts}",
            f"Empty transcripts: {self.empty_transcripts}",
            f"Wake misses: {self.wake_misses}",
            f"Stream backoffs: {self.stream_backoffs}",
            f"Ignored other speakers: {self.ignored_other_speakers}",
        ]


class BuenavistaVoiceManager:
    def __init__(self, extension: "BuenavistaExtension"):
        self.extension = extension
        self._sessions: dict[int, BuenavistaVoiceSession] = {}
        self._joining_guild_ids: set[int] = set()

    def session_for_guild(self, guild_id: int) -> Optional[BuenavistaVoiceSession]:
        return self._sessions.get(guild_id)

    async def join_voice_channel(
        self,
        *,
        guild: discord.Guild,
        member: discord.Member | discord.User,
        text_channel: discord.abc.Messageable | None,
        bot_user_id: int,
    ) -> str:
        enabled, reason = self.extension.voice_enabled_status()
        if not enabled:
            return reason
        if not guild or guild.id not in self.extension.buenavista_guild_ids:
            return "Buenavista voice commands are only available in configured Buenavista guilds."
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            return "Join a voice channel first, then say `@bub join voice`."
        if guild.id in self._joining_guild_ids:
            return "Bub is already trying to join voice. Wait a moment, then try again if needed."

        existing = self._sessions.get(guild.id)
        if existing and (existing.listening or existing.voice_client):
            return (
                f"Already connected to **{existing.voice_channel_name}**. "
                "Say `@bub leave voice` first."
            )

        guild_voice_client = getattr(guild, "voice_client", None)
        if guild_voice_client is not None:
            return "Bub already has a voice connection in this server. Say `@bub leave voice` first."

        if existing:
            await existing.disconnect()

        async def llm_callback(display_name: str, prompt: str) -> str:
            return await self.extension.generate_voice_llm_response(
                guild=guild,
                user_display_name=display_name,
                prompt_text=prompt,
            )

        session = BuenavistaVoiceSession(
            guild_id=guild.id,
            text_channel_id=getattr(text_channel, "id", None) or 0,
            voice_channel_id=member.voice.channel.id,
            voice_channel_name=member.voice.channel.name,
            bot_user_id=bot_user_id,
            owner_user_id=member.id,
            owner_display_name=getattr(member, "display_name", None) or getattr(member, "name", "user"),
            loop=asyncio.get_running_loop(),
            llm_callback=llm_callback,
        )
        self._joining_guild_ids.add(guild.id)
        self._sessions[guild.id] = session
        try:
            await session.connect_and_listen(member.voice.channel)
        except asyncio.TimeoutError:
            self._sessions.pop(guild.id, None)
            await session.disconnect()
            return "Voice join timed out. Try `@bub join voice` again in a few seconds."
        except Exception as exc:
            self._sessions.pop(guild.id, None)
            await session.disconnect()
            return f"Voice join failed: {exc}"
        finally:
            self._joining_guild_ids.discard(guild.id)
        notice = (
            f'Say "{OPENWAKEWORD_MODEL}" to wake Bub. After the chime, start your question within '
            f"{BUB_VOICE_QUERY_GRACE_SEC:.0f} seconds."
        )
        if text_channel is not None:
            await text_channel.send(notice)
        return f"Joined **{member.voice.channel.name}**. {notice}"

    async def join_voice(self, interaction: discord.Interaction) -> str:
        if not interaction.guild:
            return "This command must be used in a guild."
        return await self.join_voice_channel(
            guild=interaction.guild,
            member=interaction.user,
            text_channel=interaction.channel,
            bot_user_id=interaction.client.user.id,
        )

    async def join_voice_from_message(self, message: discord.Message, *, bot_user_id: int | None = None) -> str:
        if not message.guild:
            return "This command must be used in a guild."
        if bot_user_id is None:
            bot_member = getattr(message.guild, "me", None)
            bot_user_id = getattr(bot_member, "id", None)
        if bot_user_id is None:
            return "I could not identify Bub's bot user for the voice session."
        return await self.join_voice_channel(
            guild=message.guild,
            member=message.author,
            text_channel=message.channel,
            bot_user_id=bot_user_id,
        )

    async def leave_voice_for_guild(self, guild_id: int) -> str:
        session = self._sessions.pop(guild_id, None)
        if not session:
            return "Bub is not connected to a voice channel in this server."
        await session.disconnect()
        return "Left the voice channel and stopped listening."

    async def leave_voice(self, interaction: discord.Interaction) -> str:
        if not interaction.guild:
            return "This command must be used in a guild."
        return await self.leave_voice_for_guild(interaction.guild.id)

    async def leave_voice_from_message(self, message: discord.Message) -> str:
        if not message.guild:
            return "This command must be used in a guild."
        return await self.leave_voice_for_guild(message.guild.id)

    async def speak_text_response_from_message(self, message: discord.Message, response_text: str) -> bool:
        guild = getattr(message, "guild", None)
        if guild is None:
            return False
        session = self._sessions.get(guild.id)
        if not session:
            return False
        channel_id = getattr(getattr(message, "channel", None), "id", None)
        if channel_id not in {session.text_channel_id, session.voice_channel_id}:
            return False
        spoken = await session.speak_text_response(response_text)
        if spoken:
            print(
                f"[bv-voice] guild={guild.id} spoke text-chat reply in {session.voice_channel_name}",
                flush=True,
            )
        return spoken

    def voice_status_text(self, *, guild_id: int | None) -> str:
        enabled, reason = self.extension.voice_enabled_status()
        lines = [f"Voice feature enabled: {'yes' if enabled else 'no'}"]
        if not enabled:
            lines.append(reason)
        if guild_id is None:
            lines.append("No guild context.")
            return "\n".join(lines)
        session = self._sessions.get(guild_id)
        if not session:
            lines.append("No active voice session in this guild.")
            return "\n".join(lines)
        lines.extend(session.status_lines())
        return "\n".join(lines)

    async def voice_status(self, interaction: discord.Interaction) -> str:
        guild_id = interaction.guild.id if interaction.guild else None
        return self.voice_status_text(guild_id=guild_id)

    async def voice_status_from_message(self, message: discord.Message) -> str:
        guild_id = message.guild.id if message.guild else None
        return self.voice_status_text(guild_id=guild_id)

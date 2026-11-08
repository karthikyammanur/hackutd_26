"""Live STT from the laptop: the call audio (WASAPI loopback) plus your own mic.

Prints one line per finished chunk:
  [caller] <what the laptop is playing>
  [me]     <what the default microphone hears>

Usage:
  python scripts/listen.py --devices
  python scripts/listen.py --seconds 12
  python scripts/listen.py --device "Speakers (Realtek(R) Audio) [Loopback]"
  python scripts/listen.py --no-mic
  python scripts/listen.py --mic "Microphone Array"
"""

import argparse
import os
import queue
import sys
import threading
import time

import numpy as np
import pyaudiowpatch as pa
from faster_whisper import WhisperModel

CHUNK_SECONDS = 2.0
TARGET_RATE = 16000
READ_SECONDS = 0.1
MAX_BACKLOG = 60


def list_devices() -> None:
    p = pa.PyAudio()
    try:
        for i in range(p.get_device_count()):
            d = p.get_device_info_by_index(i)
            kind = "loopback" if d.get("isLoopbackDevice") else "input"
            print(f"{i}: [{kind}] {d['name']} ({int(d['defaultSampleRate'])} Hz)")
    finally:
        p.terminate()


def resample(audio: np.ndarray, src_rate: int) -> np.ndarray:
    if src_rate == TARGET_RATE or audio.size == 0:
        return audio
    n = int(audio.size * TARGET_RATE / src_rate)
    return np.interp(
        np.linspace(0, audio.size - 1, n, dtype=np.float64),
        np.arange(audio.size, dtype=np.float64),
        audio,
    ).astype(np.float32)


def find_loopback(p: pa.PyAudio, wanted: str | None) -> dict:
    if not wanted:
        return p.get_default_wasapi_loopback()
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        if d.get("isLoopbackDevice") and wanted.lower() in d["name"].lower():
            return d
    raise SystemExit(f"no loopback device matching {wanted!r}")


def find_mic(p: pa.PyAudio, wanted: str | None) -> dict | None:
    if wanted:
        for i in range(p.get_device_count()):
            d = p.get_device_info_by_index(i)
            if d.get("isLoopbackDevice") or int(d.get("maxInputChannels", 0)) < 1:
                continue
            if wanted.lower() in d["name"].lower():
                return d
        raise SystemExit(f"no microphone matching {wanted!r}")
    try:
        d = p.get_default_input_device_info()
    except OSError:
        return None
    if d.get("isLoopbackDevice") or int(d.get("maxInputChannels", 0)) < 1:
        return None
    return d


def open_capture(p: pa.PyAudio, info: dict):
    rate = int(info["defaultSampleRate"])
    channels = max(1, int(info["maxInputChannels"]))
    stream = p.open(
        format=pa.paInt16,
        channels=channels,
        rate=rate,
        input=True,
        input_device_index=info["index"],
        frames_per_buffer=1024,
    )
    return stream, rate, channels


def pump(stream, rate: int, channels: int, who: str, q, stop, dead) -> None:
    read_frames = max(160, int(rate * READ_SECONDS))
    while not stop.is_set():
        try:
            raw = stream.read(read_frames, exception_on_overflow=False)
        except Exception as exc:
            dead.append((who, str(exc)))
            return
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if channels > 1:
            pcm = pcm.reshape(-1, channels).mean(axis=1)
        rms = float(np.sqrt(np.mean(pcm**2))) if pcm.size else 0.0
        q.put((who, pcm, time.time(), rms))


def transcribe(model: WhisperModel, audio: np.ndarray, rate: int) -> str:
    audio = resample(audio, rate)
    segments, _ = model.transcribe(
        audio,
        language="en",
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    text = " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.6).strip()
    return " ".join(text.split())


def is_echo(text: str, recent: "list[tuple[float, str]]") -> bool:
    words = set(text.lower().split())
    if not words:
        return False
    now = time.time()
    for at, line in recent:
        if now - at > 8:
            continue
        if len(words & set(line.lower().split())) / len(words) > 0.6:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--devices", action="store_true", help="list devices and exit")
    ap.add_argument("--device", default=None, help="loopback device name substring")
    ap.add_argument("--mic", default=None, help="microphone name substring (default: system default)")
    ap.add_argument("--no-mic", action="store_true", help="do not capture the microphone")
    ap.add_argument("--model", default="base.en")
    ap.add_argument("--seconds", type=float, default=0, help="stop after N seconds (0 = forever)")
    args = ap.parse_args()

    if args.devices:
        list_devices()
        return 0

    p = pa.PyAudio()
    call = find_loopback(p, args.device)
    mic = None if args.no_mic else find_mic(p, args.mic)

    call_stream, call_rate, call_ch = open_capture(p, call)
    print(f"# listening on {call['name']} ({call_rate} Hz, {call_ch} ch)", file=sys.stderr, flush=True)

    mic_stream = mic_rate = None
    if mic is not None and mic["index"] != call["index"]:
        mic_stream, mic_rate, mic_ch = open_capture(p, mic)
        print(f"# mic {mic['name']} ({mic_rate} Hz, {mic_ch} ch)", file=sys.stderr, flush=True)
    else:
        mic_stream = None
        print("# mic off", file=sys.stderr, flush=True)

    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    warm = time.time()
    transcribe(model, np.zeros(TARGET_RATE, dtype=np.float32), TARGET_RATE)
    print(
        f"# model {args.model} ready (warm {int((time.time() - warm) * 1000)} ms)",
        file=sys.stderr,
        flush=True,
    )

    started = time.time()
    q: queue.Queue[tuple[str, np.ndarray]] = queue.Queue()
    stop = threading.Event()
    dead: list[tuple[str, str]] = []

    threading.Thread(
        target=pump, args=(call_stream, call_rate, call_ch, "caller", q, stop, dead), daemon=True
    ).start()
    if mic_stream is not None:
        threading.Thread(
            target=pump, args=(mic_stream, mic_rate, mic_ch, "me", q, stop, dead), daemon=True
        ).start()

    rates = {"caller": call_rate, "me": mic_rate}
    frames = {who: int(rate * CHUNK_SECONDS) for who, rate in rates.items() if rate}
    buf: dict[str, list[np.ndarray]] = {who: [] for who in frames}
    have = {who: 0 for who in frames}
    last = {who: "" for who in frames}
    recent: list[tuple[float, str]] = []
    caller_log: list[tuple[float, float]] = []

    try:
        while True:
            if args.seconds and time.time() - started >= args.seconds:
                break
            if dead:
                who, msg = dead.pop(0)
                print(f"# {who} capture stopped: {msg}", file=sys.stderr, flush=True)
            while q.qsize() > MAX_BACKLOG:
                q.get_nowait()
            try:
                who, pcm, at, rms = q.get(timeout=0.5)
            except queue.Empty:
                continue
            if who == "caller":
                caller_log = [(t, r) for t, r in caller_log if at - t <= 3] + [(at, rms)]
            buf[who].append(pcm)
            have[who] += pcm.size
            if have[who] < frames[who]:
                continue
            audio = np.concatenate(buf[who])[: frames[who]]
            buf[who] = []
            have[who] = 0

            if os.environ.get("STT_DEBUG"):
                print(f"# {who} chunk rms {rms:.5f}", file=sys.stderr, flush=True)

            # the mic hears the laptop speakers; drop chunks where the caller is louder
            if who == "me":
                if rms < 0.008:
                    continue
                if any(abs(at - t) <= 2.5 and r > rms * 0.6 for t, r in caller_log):
                    continue

            text = transcribe(model, audio, rates[who])
            if len(text) < 3 or text.lower() == last[who].lower():
                continue
            if who == "me" and is_echo(text, recent):
                continue
            print(f"[{who}] {text}", flush=True)
            last[who] = text
            recent = [(t, s) for t, s in recent if time.time() - t <= 8] + [(time.time(), text)]
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for s in (call_stream, mic_stream):
            if s is not None:
                try:
                    s.stop_stream()
                    s.close()
                except Exception:
                    pass
        p.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

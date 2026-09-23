from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


@dataclass(frozen=True)
class VoiceResult:
    path: Path
    duration: float


class VoiceProvider(Protocol):
    provider_id: str
    voice_id: str
    model_id: str

    def synthesize(self, text: str, output: Path) -> VoiceResult: ...


def probe_audio_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def _run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


class MacOSVoiceProvider:
    provider_id = "macos"
    model_id = "say"
    output_suffix = ".aiff"

    def __init__(
        self,
        voice_id: str = "Tingting",
        rate: int = 175,
        run_command: Callable[[list[str]], None] = _run_command,
        duration_probe: Callable[[Path], float] = probe_audio_duration,
    ) -> None:
        self.voice_id = voice_id
        self.rate = rate
        self._run_command = run_command
        self._duration_probe = duration_probe

    def synthesize(self, text: str, output: Path) -> VoiceResult:
        output.parent.mkdir(parents=True, exist_ok=True)
        self._run_command(
            [
                "say",
                "-v",
                self.voice_id,
                "-r",
                str(self.rate),
                "-o",
                str(output),
                text,
            ]
        )
        return VoiceResult(path=output, duration=self._duration_probe(output))


def _cache_key(provider: VoiceProvider, text: str) -> str:
    value = json.dumps(
        {
            "provider": provider.provider_id,
            "voice": provider.voice_id,
            "model": provider.model_id,
            "text": text,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_voice_segments(
    provider: VoiceProvider,
    texts: list[str],
    cache_dir: Path,
) -> list[VoiceResult]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    results = []
    suffix = getattr(provider, "output_suffix", ".audio")
    for text in texts:
        cache_key = _cache_key(provider, text)
        audio_path = cache_dir / f"{cache_key}{suffix}"
        metadata_path = cache_dir / f"{cache_key}.json"
        if audio_path.is_file() and metadata_path.is_file():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            results.append(
                VoiceResult(path=audio_path, duration=float(metadata["duration"]))
            )
            continue
        result = provider.synthesize(text, audio_path)
        metadata_path.write_text(
            json.dumps({"duration": result.duration}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        results.append(result)
    return results

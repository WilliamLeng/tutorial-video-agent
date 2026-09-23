import importlib
from pathlib import Path

from tutorial_video.models import TimeRange, Transcript, TranscriptSegment


def transcribe_local(audio_path: Path, model_name: str) -> Transcript:
    mlx_whisper = importlib.import_module("mlx_whisper")
    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=model_name,
    )
    return Transcript(
        language=result.get("language", "zh"),
        text=result["text"].strip(),
        segments=[
            TranscriptSegment(
                text=item["text"].strip(),
                source_range=TimeRange(start=item["start"], end=item["end"]),
            )
            for item in result["segments"]
            if item["end"] > item["start"]
        ],
    )

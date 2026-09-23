import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from tutorial_video.models import MediaInfo


def _require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"required binary not found: {name}")


def probe_media(video_path: Path) -> MediaInfo:
    _require_binary("ffprobe")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,avg_frame_rate",
            "-of",
            "json",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    video = next(item for item in payload["streams"] if item["codec_type"] == "video")
    return MediaInfo(
        path=str(video_path),
        duration=float(payload["format"]["duration"]),
        width=int(video["width"]),
        height=int(video["height"]),
        fps=float(Fraction(video["avg_frame_rate"])),
        has_audio=any(item["codec_type"] == "audio" for item in payload["streams"]),
    )


def extract_audio(video_path: Path, output_path: Path) -> Path:
    _require_binary("ffmpeg")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path

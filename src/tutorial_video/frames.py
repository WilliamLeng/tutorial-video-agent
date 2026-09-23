import json
import math
import subprocess
from pathlib import Path


def sample_timestamps(duration: float, interval: float = 2.5) -> list[float]:
    values = []
    current = 0.0
    while current < duration:
        values.append(round(current, 3))
        current += interval
    near_end = float(math.floor(duration))
    if values[-1] != near_end:
        values.append(near_end)
    return values


def extract_frames(
    video_path: Path,
    output_dir: Path,
    timestamps: list[float],
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    scale = "scale='if(gt(iw,ih),768,-2)':'if(gt(iw,ih),-2,768)'"
    for timestamp in timestamps:
        output = output_dir / f"frame_{round(timestamp * 1000):07d}.jpg"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-vf",
                scale,
                "-q:v",
                "3",
                str(output),
            ],
            check=True,
            capture_output=True,
        )
        outputs.append(output)
    return outputs


def write_frame_index(
    paths: list[Path],
    timestamps: list[float],
    output_path: Path,
) -> Path:
    data = [
        {"timestamp": timestamp, "frame_path": str(path)}
        for path, timestamp in zip(paths, timestamps)
    ]
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path

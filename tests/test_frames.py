import json
from pathlib import Path
from unittest.mock import patch

from tutorial_video.frames import extract_frames, sample_timestamps, write_frame_index


def test_sample_timestamps_covers_end_of_video() -> None:
    assert sample_timestamps(6.2, 2.5) == [0.0, 2.5, 5.0, 6.0]


def test_frames_are_scaled_and_indexed(tmp_path: Path) -> None:
    source = tmp_path / "source.MP4"
    source.touch()
    with patch("tutorial_video.frames.subprocess.run") as run:
        frames = extract_frames(source, tmp_path / "frames", [2.5])
    command = run.call_args.args[0]
    assert "768" in command[command.index("-vf") + 1]
    index = write_frame_index(frames, [2.5], tmp_path / "frame-index.json")
    assert json.loads(index.read_text()) == [
        {"timestamp": 2.5, "frame_path": str(frames[0])}
    ]

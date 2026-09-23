import json
from pathlib import Path
from unittest.mock import patch

from tutorial_video.media import extract_audio, probe_media


def test_probe_media_reads_video_and_audio_streams(tmp_path: Path) -> None:
    source = tmp_path / "source.MP4"
    source.touch()
    payload = {
        "streams": [
            {"codec_type": "video", "width": 1284, "height": 2778, "avg_frame_rate": "60/1"},
            {"codec_type": "audio"},
        ],
        "format": {"duration": "148.56"},
    }
    with patch("tutorial_video.media.subprocess.run") as run:
        run.return_value.stdout = json.dumps(payload)
        media = probe_media(source)
    assert media.duration == 148.56
    assert media.width == 1284
    assert media.has_audio is True


def test_extract_audio_is_local_mono_wav(tmp_path: Path) -> None:
    source = tmp_path / "source.MP4"
    output = tmp_path / "audio.wav"
    source.touch()
    with patch("tutorial_video.media.subprocess.run") as run:
        extract_audio(source, output)
    command = run.call_args.args[0]
    assert command[-5:] == ["-ac", "1", "-ar", "16000", str(output)]

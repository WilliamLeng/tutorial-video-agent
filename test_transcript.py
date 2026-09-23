from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tutorial_video.transcript import transcribe_local


def test_transcribe_local_preserves_segment_timestamps(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    audio.touch()
    payload = {
        "language": "zh",
        "text": "点击聊天工具栏",
        "segments": [{"start": 1.2, "end": 3.4, "text": "点击聊天工具栏"}],
    }
    module = SimpleNamespace()
    module.transcribe = lambda *args, **kwargs: payload
    with patch("tutorial_video.transcript.importlib.import_module", return_value=module) as load:
        result = transcribe_local(audio, "local-model")
    load.assert_called_once_with("mlx_whisper")
    assert result.segments[0].source_range.start == 1.2

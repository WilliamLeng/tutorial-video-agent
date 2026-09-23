from pathlib import Path

from tutorial_video.voice import (
    MacOSVoiceProvider,
    VoiceResult,
    generate_voice_segments,
)


class FileVoiceProvider:
    provider_id = "file-test"
    voice_id = "voice-a"
    model_id = "model-a"

    def __init__(self, fail_if_called: bool = False) -> None:
        self.fail_if_called = fail_if_called

    def synthesize(self, text: str, output: Path) -> VoiceResult:
        if self.fail_if_called:
            raise AssertionError("缓存命中时不应再次生成语音")
        output.write_bytes(f"audio:{text}".encode())
        return VoiceResult(path=output, duration=1.25)


def test_generate_voice_segments_reuses_cache_without_calling_provider(
    tmp_path: Path,
) -> None:
    first = generate_voice_segments(
        FileVoiceProvider(),
        ["先打开示例应用。", "再选择需要的功能。"],
        tmp_path,
    )
    second = generate_voice_segments(
        FileVoiceProvider(fail_if_called=True),
        ["先打开示例应用。", "再选择需要的功能。"],
        tmp_path,
    )

    assert [item.path for item in second] == [item.path for item in first]
    assert [item.duration for item in second] == [1.25, 1.25]
    assert all(item.path.read_bytes().startswith(b"audio:") for item in second)


def test_generate_voice_segments_creates_one_file_per_sentence(tmp_path: Path) -> None:
    results = generate_voice_segments(
        FileVoiceProvider(),
        ["第一句。", "第二句。", "第三句。"],
        tmp_path,
    )

    assert len(results) == 3
    assert len({item.path for item in results}) == 3
    assert [item.duration for item in results] == [1.25, 1.25, 1.25]


def test_macos_provider_returns_generated_file_and_duration(tmp_path: Path) -> None:
    def fake_run(command: list[str]) -> None:
        Path(command[command.index("-o") + 1]).write_bytes(b"aiff")

    provider = MacOSVoiceProvider(
        voice_id="Tingting",
        rate=175,
        run_command=fake_run,
        duration_probe=lambda _path: 2.5,
    )

    result = provider.synthesize("测试旁白", tmp_path / "voice.aiff")

    assert result.path.read_bytes() == b"aiff"
    assert result.duration == 2.5

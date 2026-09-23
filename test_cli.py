from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from tutorial_video.cli import app
from tutorial_video.models import (
    CourseDraft,
    CourseStep,
    Evidence,
    MediaInfo,
    TimeRange,
    Transcript,
)


def test_prepare_rejects_missing_video() -> None:
    result = CliRunner().invoke(app, ["prepare", "missing.MP4"])
    assert result.exit_code == 2
    assert "视频不存在" in result.output


def test_prepare_writes_local_evidence(tmp_path: Path) -> None:
    video = tmp_path / "source.MP4"
    video.touch()
    output = tmp_path / "output"
    media = MediaInfo(
        path=str(video),
        duration=6.2,
        width=1284,
        height=2778,
        fps=60,
        has_audio=True,
    )
    transcript = Transcript(language="zh", text="测试", segments=[])
    frame = output / "frames" / "frame.jpg"
    with (
        patch("tutorial_video.cli.probe_media", return_value=media),
        patch("tutorial_video.cli.extract_audio", return_value=output / "audio.wav"),
        patch("tutorial_video.cli.transcribe_local", return_value=transcript),
        patch("tutorial_video.cli.extract_frames", return_value=[frame]),
        patch("tutorial_video.cli.sample_timestamps", return_value=[0.0]),
        patch("tutorial_video.cli.write_frame_index") as write_index,
    ):
        result = CliRunner().invoke(
            app,
            ["prepare", str(video), "--output", str(output)],
        )
    assert result.exit_code == 0
    assert (output / "media.json").is_file()
    assert (output / "transcript.raw.json").is_file()
    write_index.assert_called_once()


def test_render_uses_validated_project_file(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    project.write_text("{}", encoding="utf-8")
    final = tmp_path / "final.mp4"

    with patch("tutorial_video.cli.render_project", return_value=final) as render:
        result = CliRunner().invoke(app, ["render", str(project)])

    assert result.exit_code == 0
    assert str(final) in result.output
    render.assert_called_once_with(project, None)


def test_validate_draft_reports_valid_course(tmp_path: Path) -> None:
    media = MediaInfo(
        path="source.MP4",
        duration=10,
        width=1284,
        height=2778,
        fps=60,
        has_audio=True,
    )
    draft = CourseDraft(
        title="测试教程",
        introduction="介绍",
        learning_goal="完成操作",
        steps=[
            CourseStep(
                id="step-001",
                title="打开入口",
                narration="点击入口。",
                source_range=TimeRange(start=1, end=3),
                confidence=1,
                needs_review=False,
                evidence=[Evidence(kind="screen", description="入口可见", timestamp=1)],
            )
        ],
    )
    media_path = tmp_path / "media.json"
    draft_path = tmp_path / "draft.json"
    media_path.write_text(media.model_dump_json(), encoding="utf-8")
    draft_path.write_text(draft.model_dump_json(), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["validate-draft", str(draft_path), "--media", str(media_path)],
    )

    assert result.exit_code == 0
    assert "结构稿校验通过" in result.output


def test_validate_draft_returns_failure_for_invalid_evidence(tmp_path: Path) -> None:
    media = MediaInfo(
        path="source.MP4",
        duration=2,
        width=1284,
        height=2778,
        fps=60,
        has_audio=True,
    )
    draft = CourseDraft(
        title="测试教程",
        introduction="介绍",
        learning_goal="完成操作",
        steps=[
            CourseStep(
                id="step-001",
                title="打开入口",
                narration="点击入口。",
                source_range=TimeRange(start=1, end=3),
                confidence=1,
                needs_review=False,
            )
        ],
    )
    media_path = tmp_path / "media.json"
    draft_path = tmp_path / "draft.json"
    media_path.write_text(media.model_dump_json(), encoding="utf-8")
    draft_path.write_text(draft.model_dump_json(), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["validate-draft", str(draft_path), "--media", str(media_path)],
    )

    assert result.exit_code == 1
    assert "source range exceeds media duration" in result.output

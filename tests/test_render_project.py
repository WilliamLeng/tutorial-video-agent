from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from tutorial_video.models import MediaInfo
from tutorial_video.render_project import (
    IntroCard,
    RenderProject,
    RenderStep,
    SourceClip,
    VisualEffect,
    _build_video_filter,
    _effect_filters,
    _mix_master_audio,
    _phone_geometry,
    _verify_rendered_output,
    build_timeline,
    load_render_project,
)


def _project(tmp_path: Path) -> RenderProject:
    return RenderProject(
        title="示例教程",
        source_video=tmp_path / "source.mp4",
        output_video=tmp_path / "final.mp4",
        intro=IntroCard(
            narration="先介绍功能。",
            title="示例功能",
            subtitle="操作教程",
            screenshot_at=1.0,
        ),
        steps=[
            RenderStep(
                title="打开入口",
                narration="点击入口。",
                clips=[SourceClip(start=2.0, end=6.0)],
            )
        ],
    )


def test_render_project_requires_source_clips() -> None:
    with pytest.raises(ValidationError):
        RenderStep(title="空步骤", narration="没有画面", clips=[])


def test_file_voice_project_requires_one_file_per_timeline_item(tmp_path: Path) -> None:
    project = _project(tmp_path).model_dump()
    project["voice_provider"] = "files"
    project["voice_files"] = ["intro.wav"]

    with pytest.raises(ValidationError, match="voice_files"):
        RenderProject.model_validate(project)


def test_load_render_project_resolves_file_voice_paths(tmp_path: Path) -> None:
    project = _project(tmp_path).model_dump(mode="json")
    project["voice_provider"] = "files"
    project["voice_files"] = ["intro.wav", "step.wav"]
    project_path = tmp_path / "render-project.json"
    project_path.write_text(
        RenderProject.model_validate(project).model_dump_json(),
        encoding="utf-8",
    )

    loaded = load_render_project(project_path)

    assert loaded.voice_files == [
        (tmp_path / "intro.wav").resolve(),
        (tmp_path / "step.wav").resolve(),
    ]


def test_load_render_project_resolves_background_music_path(tmp_path: Path) -> None:
    project = _project(tmp_path).model_dump(mode="json")
    project["background_music_file"] = "music.wav"
    project_path = tmp_path / "render-project.json"
    project_path.write_text(
        RenderProject.model_validate(project).model_dump_json(),
        encoding="utf-8",
    )

    loaded = load_render_project(project_path)

    assert loaded.background_music_file == (tmp_path / "music.wav").resolve()


def test_visual_effect_coordinates_are_normalized() -> None:
    with pytest.raises(ValidationError):
        VisualEffect(
            kind="click",
            start=0.0,
            end=1.0,
            x=1.2,
            y=0.5,
            width=0.1,
            height=0.1,
        )


def test_phone_geometry_preserves_phone_aspect_ratio_with_side_bars() -> None:
    left, top, width, height = _phone_geometry(1284, 2778)

    assert top == 0
    assert height == 1920
    assert round(left) == 96
    assert round(width) == 888


def test_master_mix_keeps_background_music_audible(tmp_path: Path) -> None:
    voice = tmp_path / "voice.m4a"
    music = tmp_path / "music.m4a"
    output = tmp_path / "master.m4a"

    with patch("tutorial_video.render_project._run") as run:
        _mix_master_audio(voice, 58.5, output, True, music)

    command = run.call_args.args[0]
    filter_complex = command[command.index("-filter_complex") + 1]
    assert "loudnorm=I=-24:LRA=7:TP=-3" in filter_complex
    assert "volume=0.60[bgm]" in filter_complex
    assert "sidechaincompress" not in filter_complex
    assert "[0:a][bgm]amix=inputs=2" in filter_complex


def test_effect_label_has_high_contrast_background() -> None:
    effect = VisualEffect(
        kind="click",
        start=0,
        end=2,
        x=0.75,
        y=0.52,
        width=0.2,
        height=0.08,
        label="点击发送",
    )

    filters = _effect_filters(effect, 1284, 2778, "/font.ttc")

    assert any("color=0x10243A@0.94:t=fill" in item for item in filters)
    assert any("fontcolor=white:fontsize=44" in item for item in filters)


def test_intro_filter_contains_timed_course_background_sections(tmp_path: Path) -> None:
    project = _project(tmp_path)
    project.intro.scene_text = "适用场景：新员工学习系统操作"
    project.intro.result_text = "完成设置并查看处理结果"
    timeline = build_timeline(project, [2.0, 3.0])

    filter_script = _build_video_filter(
        project,
        timeline,
        width=1284,
        height=2778,
        font="/font.ttc",
    )

    assert "适用场景" in filter_script
    assert "完成设置" in filter_script
    assert "between(t,2.000,5.000)" in filter_script
    assert "between(t,5.000,7.600)" in filter_script


def test_transition_effect_marks_step_boundary() -> None:
    effect = VisualEffect(
        kind="transition",
        start=0.4,
        end=2.8,
        x=0.08,
        y=0.04,
        width=0.84,
        height=0.08,
        label="基础设置 → 结果确认",
    )

    filters = _effect_filters(effect, 1284, 2778, "/font.ttc")

    assert any("基础设置 → 结果确认" in item for item in filters)
    assert any("color=0x1B4A7A@0.96:t=fill" in item for item in filters)


def test_build_timeline_uses_voice_duration_and_limits_speed(tmp_path: Path) -> None:
    project = _project(tmp_path)
    timeline = build_timeline(project, [2.0, 3.0])

    assert timeline[0].start == 0
    assert timeline[0].duration == 8.0
    assert timeline[1].start == 8.0
    assert timeline[1].duration == 4.0
    assert timeline[1].speed == 1.0


def test_build_timeline_rejects_unreadable_fast_operation(tmp_path: Path) -> None:
    project = _project(tmp_path)
    project.steps[0].clips = [SourceClip(start=2.0, end=12.0)]

    with pytest.raises(ValueError, match="超过最大允许值"):
        build_timeline(project, [2.0, 3.0])


def test_verify_rendered_output_rejects_truncated_video(tmp_path: Path) -> None:
    media = MediaInfo(
        path=str(tmp_path / "final.mp4"),
        duration=40.9,
        width=1080,
        height=1920,
        fps=30,
        has_audio=True,
    )

    with pytest.raises(RuntimeError, match="时长不一致"):
        _verify_rendered_output(media, expected_duration=54.9)

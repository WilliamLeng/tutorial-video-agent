from pathlib import Path
from typing import Optional

import typer

from tutorial_video.frames import extract_frames, sample_timestamps, write_frame_index
from tutorial_video.media import extract_audio, probe_media
from tutorial_video.models import CourseDraft, MediaInfo
from tutorial_video.render_project import render_project
from tutorial_video.transcript import transcribe_local
from tutorial_video.validate import validate_draft as validate_course_draft

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """准备和处理录屏操作教程。"""


@app.command()
def prepare(
    video: Path,
    output: Path = typer.Option(Path("outputs/latest"), "--output", "-o"),
    model: str = typer.Option(
        "mlx-community/whisper-large-v3-turbo",
        "--model",
    ),
) -> None:
    if not video.is_file():
        typer.echo(f"视频不存在：{video}", err=True)
        raise typer.Exit(code=2)
    output.mkdir(parents=True, exist_ok=True)
    media = probe_media(video)
    if not media.has_audio:
        typer.echo("录屏没有音轨，无法整理原始讲解", err=True)
        raise typer.Exit(code=2)
    (output / "media.json").write_text(
        media.model_dump_json(indent=2),
        encoding="utf-8",
    )
    audio = extract_audio(video, output / "audio.wav")
    transcript = transcribe_local(audio, model)
    (output / "transcript.raw.json").write_text(
        transcript.model_dump_json(indent=2),
        encoding="utf-8",
    )
    timestamps = sample_timestamps(media.duration)
    frames = extract_frames(video, output / "frames", timestamps)
    write_frame_index(frames, timestamps, output / "frame-index.json")
    typer.echo(f"本地分析素材已生成：{output}")


@app.command()
def render(
    project: Path,
    work_dir: Optional[Path] = typer.Option(None, "--work-dir"),
) -> None:
    """根据已校验的项目配置生成新配音教程成片。"""
    if not project.is_file():
        typer.echo(f"项目配置不存在：{project}", err=True)
        raise typer.Exit(code=2)
    output = render_project(project, work_dir)
    typer.echo(f"教程成片已生成：{output}")


@app.command("validate-draft")
def validate_draft_command(
    draft: Path,
    media: Path = typer.Option(..., "--media"),
) -> None:
    """校验课程结构稿的时间范围和证据完整性。"""
    if not draft.is_file() or not media.is_file():
        typer.echo("结构稿或媒体信息文件不存在", err=True)
        raise typer.Exit(code=2)
    course = CourseDraft.model_validate_json(draft.read_text(encoding="utf-8"))
    media_info = MediaInfo.model_validate_json(media.read_text(encoding="utf-8"))
    errors = validate_course_draft(course, media_info)
    if errors:
        for error in errors:
            typer.echo(error, err=True)
        raise typer.Exit(code=1)
    typer.echo("结构稿校验通过")

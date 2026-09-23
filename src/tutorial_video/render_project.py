from __future__ import annotations

# ruff: noqa: ISC004, UP045
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from tutorial_video.media import probe_media
from tutorial_video.models import MediaInfo
from tutorial_video.render import NarrationCue, paginate_narration_cues, write_ass_subtitles
from tutorial_video.voice import (
    MacOSVoiceProvider,
    generate_voice_segments,
)


class SourceClip(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_order(self) -> SourceClip:
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self

    @property
    def duration(self) -> float:
        return self.end - self.start


class VisualEffect(BaseModel):
    kind: Literal["click", "focus", "privacy", "transition"]
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    label: Optional[str] = None

    @model_validator(mode="after")
    def validate_effect(self) -> VisualEffect:
        if self.end <= self.start:
            raise ValueError("effect end must be greater than start")
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("effect rectangle must stay inside the source frame")
        return self


class IntroCard(BaseModel):
    title: str
    subtitle: str = "操作教程"
    narration: str
    screenshot_at: float = Field(ge=0)
    value_text: Optional[str] = None
    scene_text: Optional[str] = None
    result_text: Optional[str] = None
    duration: float = Field(default=8.0, ge=8.0, le=15.0)


class RenderStep(BaseModel):
    title: str
    narration: str
    clips: list[SourceClip] = Field(min_length=1)
    effects: list[VisualEffect] = Field(default_factory=list)
    min_duration: Optional[float] = Field(default=None, gt=0)


class RenderProject(BaseModel):
    schema_version: str = "1.0"
    title: str
    source_video: Path
    output_video: Path
    intro: IntroCard
    steps: list[RenderStep] = Field(min_length=1)
    voice: str = "Tingting"
    voice_rate: int = Field(default=175, ge=120, le=240)
    voice_provider: Literal["macos", "files"] = "macos"
    voice_files: list[Path] = Field(default_factory=list)
    voice_cache_dir: Optional[Path] = None
    max_speed: float = Field(default=1.5, ge=1.0, le=2.0)
    background_music: bool = True
    background_music_file: Optional[Path] = None

    @model_validator(mode="after")
    def validate_voice_provider(self) -> RenderProject:
        if self.voice_provider == "files" and len(self.voice_files) != len(self.steps) + 1:
            raise ValueError("voice_files must contain one file for intro and each step")
        return self


@dataclass(frozen=True)
class TimelineItem:
    kind: Literal["intro", "step"]
    index: int
    start: float
    duration: float
    voice_duration: float
    speed: float


def build_timeline(
    project: RenderProject,
    voice_durations: list[float],
) -> list[TimelineItem]:
    if len(voice_durations) != len(project.steps) + 1:
        raise ValueError("voice duration count does not match intro and steps")

    intro_duration = max(project.intro.duration, voice_durations[0] + 0.6)
    if intro_duration > 15:
        raise ValueError("片头解说超过 15 秒，请精简介绍文案")
    timeline = [
        TimelineItem(
            kind="intro",
            index=0,
            start=0,
            duration=intro_duration,
            voice_duration=voice_durations[0],
            speed=1.0,
        )
    ]
    cursor = intro_duration
    for index, (step, voice_duration) in enumerate(
        zip(project.steps, voice_durations[1:]),
        start=1,
    ):
        source_duration = sum(clip.duration for clip in step.clips)
        spoken_duration = max(voice_duration + 0.6, step.min_duration or 0)
        target_duration = (
            source_duration
            if spoken_duration <= source_duration <= spoken_duration + 1.0
            else spoken_duration
        )
        speed = source_duration / target_duration
        if speed > project.max_speed + 1e-6:
            raise ValueError(
                f"步骤 {index}「{step.title}」需要 {speed:.2f}x，"
                f"超过最大允许值 {project.max_speed:.2f}x；请缩短 clips 或延长文案"
            )
        if speed < 0.85 - 1e-6:
            raise ValueError(
                f"步骤 {index}「{step.title}」画面只有 {source_duration:.2f} 秒，"
                f"无法容纳 {voice_duration:.2f} 秒解说；请延长 clips 或缩短文案"
            )
        item = TimelineItem(
            kind="step",
            index=index,
            start=cursor,
            duration=target_duration,
            voice_duration=voice_duration,
            speed=speed,
        )
        timeline.append(item)
        cursor += target_duration
    return timeline


def load_render_project(path: Path) -> RenderProject:
    project = RenderProject.model_validate_json(path.read_text(encoding="utf-8"))
    base = path.parent
    if not project.source_video.is_absolute():
        project.source_video = (base / project.source_video).resolve()
    if not project.output_video.is_absolute():
        project.output_video = (base / project.output_video).resolve()
    if project.voice_cache_dir is not None and not project.voice_cache_dir.is_absolute():
        project.voice_cache_dir = (base / project.voice_cache_dir).resolve()
    project.voice_files = [
        path if path.is_absolute() else (base / path).resolve()
        for path in project.voice_files
    ]
    if (
        project.background_music_file is not None
        and not project.background_music_file.is_absolute()
    ):
        project.background_music_file = (base / project.background_music_file).resolve()
    return project


def _require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"缺少本机程序：{name}")


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    values = [
        float(line)
        for line in result.stdout.splitlines()
        if line and line != "N/A"
    ]
    if not values:
        raise RuntimeError(f"无法读取音频时长：{path}")
    return max(values)


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("%", r"\%")
    )


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def _generate_voice(project: RenderProject, work_dir: Path) -> tuple[list[Path], list[float]]:
    if project.voice_provider == "files":
        for path in project.voice_files:
            if not path.is_file():
                raise FileNotFoundError(f"配音文件不存在：{path}")
        return project.voice_files, [_probe_duration(path) for path in project.voice_files]
    texts = [project.intro.narration, *[step.narration for step in project.steps]]
    provider = MacOSVoiceProvider(
        voice_id=project.voice,
        rate=project.voice_rate,
    )
    results = generate_voice_segments(
        provider,
        texts,
        project.voice_cache_dir or work_dir / "voice-cache",
    )
    return [item.path for item in results], [item.duration for item in results]


def _phone_geometry(width: int, height: int) -> tuple[float, float, float, float]:
    phone_height = 1920.0
    phone_width = round((phone_height * width / height) / 2) * 2
    left = (1080 - phone_width) / 2
    return left, 0, phone_width, phone_height


def _effect_filters(
    effect: VisualEffect,
    width: int,
    height: int,
    font: str,
) -> list[str]:
    left, top, phone_width, phone_height = _phone_geometry(width, height)
    x = round(left + effect.x * phone_width)
    y = round(top + effect.y * phone_height)
    box_width = round(effect.width * phone_width)
    box_height = round(effect.height * phone_height)
    enable = f"between(t,{effect.start:.3f},{effect.end:.3f})"
    if effect.kind == "privacy":
        return [
            "drawbox="
            f"x={x}:y={y}:w={box_width}:h={box_height}:"
            f"color=0xF2F5F8@0.82:t=fill:enable='{enable}'"
        ]
    if effect.kind == "transition":
        transition_label = _escape_drawtext(effect.label or "步骤切换")
        return [
            "drawbox="
            "x=110:y=115:w=860:h=92:"
            f"color=0x1B4A7A@0.96:t=fill:enable='{enable}'",
            "drawtext="
            f"fontfile='{font}':text='{transition_label}':"
            "fontcolor=white:fontsize=52:x=(w-text_w)/2:y=132:"
            f"enable='{enable}'",
        ]
    filters = [
        "drawbox="
        f"x={x}:y={y}:w={box_width}:h={box_height}:"
        f"color=0xFF5A5F@0.24:t=13:enable='{enable}'"
    ]
    if effect.kind == "click":
        filters.append(
            "drawbox="
            f"x={x + 8}:y={y + 8}:w={max(1, box_width - 16)}:"
            f"h={max(1, box_height - 16)}:"
            f"color=0xD44830@0.92:t=7:enable='{enable}'"
        )
    if effect.label:
        label_width = min(600, max(220, len(effect.label) * 50 + 70))
        label_x = min(x, 1080 - label_width - 30)
        label_y = max(30, y - 78)
        filters.append(
            "drawbox="
            f"x={label_x}:y={label_y}:w={label_width}:h=68:"
            f"color=0x10243A@0.94:t=fill:enable='{enable}'"
        )
        filters.append(
            "drawtext="
            f"fontfile='{font}':text='{_escape_drawtext(effect.label)}':"
            f"fontcolor=white:fontsize=44:x={label_x + 20}:y={label_y + 8}:"
            f"enable='{enable}'"
        )
    return filters


def _build_video_filter(
    project: RenderProject,
    timeline: list[TimelineItem],
    width: int,
    height: int,
    font: str,
) -> str:
    filters: list[str] = []
    intro = timeline[0]
    screenshot_end = project.intro.screenshot_at + 0.08
    filters.extend(
        [
            f"[0:v]trim=start={project.intro.screenshot_at}:end={screenshot_end},"
            "select='eq(n,0)',loop=loop=-1:size=1:start=0,"
            f"trim=duration={intro.duration:.3f},setpts=PTS-STARTPTS,"
            "scale=-2:1920,pad=1080:1920:(ow-iw)/2:0:color=white[introbase]",
        ]
    )
    intro_chain = [
        "[introbase]eq=brightness=-0.24:saturation=0.72",
        "drawbox=x=75:y=100:w=930:h=240:color=0x10243A@0.90:t=fill:"
        "enable='between(t,0.000,2.200)'",
        "drawtext="
        f"fontfile='{font}':text='{_escape_drawtext(project.intro.title)}':"
        "fontcolor=white:fontsize=66:x=(w-text_w)/2:y=145:"
        "enable='between(t,0.000,2.200)'",
        "drawtext="
        f"fontfile='{font}':text='{_escape_drawtext(project.intro.subtitle)}':"
        "fontcolor=0x63E6BE:fontsize=48:x=(w-text_w)/2:y=235:"
        "enable='between(t,0.000,2.200)'",
    ]
    if project.intro.scene_text:
        intro_chain.extend(
            [
                "drawbox=x=90:y=690:w=900:h=180:"
                "color=0x1B4A7A@0.94:t=fill:"
                "enable='between(t,2.000,5.000)'",
                "drawtext="
                f"fontfile='{font}':text='{_escape_drawtext(project.intro.scene_text)}':"
                "fontcolor=white:fontsize=48:x=(w-text_w)/2:y=748:"
                "enable='between(t,2.000,5.000)'",
            ]
        )
    if project.intro.result_text:
        intro_chain.extend(
            [
                "drawbox=x=70:y=680:w=940:h=200:"
                "color=0xD44830@0.94:t=fill:"
                "enable='between(t,5.000,7.600)'",
                "drawtext="
                f"fontfile='{font}':text='{_escape_drawtext(project.intro.result_text)}':"
                "fontcolor=white:fontsize=46:x=(w-text_w)/2:y=752:"
                "enable='between(t,5.000,7.600)'",
            ]
        )
    if project.intro.value_text:
        intro_chain.append(
            "drawtext="
            f"fontfile='{font}':text='{_escape_drawtext(project.intro.value_text)}':"
            "fontcolor=white:fontsize=40:x=(w-text_w)/2:y=1600"
        )
    intro_chain.extend(
        [
            "fade=t=in:st=0:d=0.7",
            f"fade=t=out:st={intro.duration - 0.7:.3f}:d=0.7",
            f"trim=duration={intro.duration:.3f},setpts=PTS-STARTPTS[intro]",
        ]
    )
    filters.append(",".join(intro_chain))

    for step_index, (step, item) in enumerate(
        zip(project.steps, timeline[1:]),
        start=1,
    ):
        clip_labels = []
        for clip_index, clip in enumerate(step.clips):
            label = f"s{step_index}c{clip_index}"
            filters.append(
                f"[0:v]trim=start={clip.start}:end={clip.end},"
                f"setpts=PTS-STARTPTS[{label}]"
            )
            clip_labels.append(f"[{label}]")
        raw_label = f"s{step_index}raw"
        if len(clip_labels) == 1:
            filters.append(
                f"{clip_labels[0]}null[{raw_label}]"
            )
        else:
            filters.append(
                f"{''.join(clip_labels)}concat=n={len(clip_labels)}:v=1:a=0"
                f"[{raw_label}]"
            )
        filters.append(
            f"[{raw_label}]setpts={1 / item.speed:.8f}*PTS,"
            f"trim=duration={item.duration:.3f},scale=-2:1920,"
            f"pad=1080:1920:(ow-iw)/2:0:color=white[s{step_index}full]"
        )
        title_width = min(800, max(360, 175 + len(step.title) * 45))
        chain = [
            f"[s{step_index}full]null",
            f"drawbox=x=55:y=38:w={title_width}:h=78:"
            "color=0x10243A@0.92:t=fill",
            "drawtext="
            f"fontfile='{font}':text='{step_index:02d}  "
            f"{_escape_drawtext(step.title)}':"
            "fontcolor=white:fontsize=38:x=85:y=57",
        ]
        for effect in step.effects:
            if effect.end > item.duration + 1e-6:
                raise ValueError(
                    f"步骤 {step_index}「{step.title}」的视觉效果超出步骤时长"
                )
            chain.extend(_effect_filters(effect, width, height, font))
        chain.append(f"format=yuv420p[v{step_index}]")
        filters.append(",".join(chain))

    concat_inputs = "[intro]" + "".join(
        f"[v{index}]" for index in range(1, len(project.steps) + 1)
    )
    filters.append(
        f"{concat_inputs}concat=n={len(project.steps) + 1}:v=1:a=0,"
        "format=yuv420p[vout]"
    )
    return ";\n".join(filters)


def _render_audio(
    project: RenderProject,
    timeline: list[TimelineItem],
    voices: list[Path],
    output: Path,
) -> None:
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning"]
    for voice in voices:
        command.extend(["-i", str(voice)])
    chains = []
    labels = []
    for index, item in enumerate(timeline):
        delay = round((item.start + 0.3) * 1000)
        chains.append(f"[{index}:a]adelay={delay}|{delay}[a{index}]")
        labels.append(f"[a{index}]")
    total = timeline[-1].start + timeline[-1].duration
    chains.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0,"
        f"loudnorm=I=-17:LRA=7:TP=-1.5,apad,atrim=duration={total:.3f}[voice]"
    )
    command.extend(
        [
            "-filter_complex",
            ";".join(chains),
            "-map",
            "[voice]",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-b:a",
            "192k",
            str(output),
        ]
    )
    _run(command)


def _mix_master_audio(
    voice_track: Path,
    duration: float,
    output: Path,
    background_music: bool,
    background_music_file: Optional[Path] = None,
) -> None:
    if not background_music:
        _run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "warning",
                "-i",
                str(voice_track),
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-b:a",
                "192k",
                str(output),
            ]
        )
        return
    command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-i",
            str(voice_track),
    ]
    if background_music_file is not None:
        command.extend(["-stream_loop", "-1", "-i", str(background_music_file)])
    else:
        command.extend(
            [
                "-f",
                "lavfi",
                "-t",
                f"{duration:.3f}",
                "-i",
                (
                    "aevalsrc=0.04*sin(2*PI*110*t)+0.025*sin(2*PI*165*t)"
                    "+0.018*sin(2*PI*220*t):s=48000"
                ),
            ]
        )
    command.extend(
        [
            "-filter_complex",
            (
                f"[1:a]atrim=duration={duration:.3f},lowpass=f=6500,"
                "loudnorm=I=-24:LRA=7:TP=-3,"
                "afade=t=in:st=0:d=2,"
                f"afade=t=out:st={max(0, duration - 3):.3f}:d=3,"
                "volume=0.60[bgm];"
                "[0:a][bgm]amix=inputs=2:duration=first:normalize=0,"
                "loudnorm=I=-16:LRA=8:TP=-1.2[a]"
            ),
            "-map",
            "[a]",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-b:a",
            "192k",
            str(output),
        ]
    )
    _run(command)


def _verify_rendered_output(
    media: MediaInfo,
    expected_duration: float,
) -> None:
    if not media.has_audio:
        raise RuntimeError("成片缺少解说音轨")
    if media.width != 1080 or media.height != 1920:
        raise RuntimeError(
            f"成片分辨率错误：{media.width}x{media.height}，应为 1080x1920"
        )
    if abs(media.duration - expected_duration) > 0.25:
        raise RuntimeError(
            f"成片与项目时间线时长不一致："
            f"成片 {media.duration:.2f} 秒，项目 {expected_duration:.2f} 秒"
        )


def render_project(project_path: Path, work_dir: Optional[Path] = None) -> Path:
    for binary in ("ffmpeg", "ffprobe"):
        _require_binary(binary)
    project = load_render_project(project_path)
    if project.voice_provider == "macos":
        _require_binary("say")
    if not project.source_video.is_file():
        raise FileNotFoundError(f"原始视频不存在：{project.source_video}")
    if (
        project.background_music
        and project.background_music_file is not None
        and not project.background_music_file.is_file()
    ):
        raise FileNotFoundError(f"背景音乐不存在：{project.background_music_file}")
    media = probe_media(project.source_video)
    for step_index, step in enumerate(project.steps, start=1):
        for clip in step.clips:
            if clip.end > media.duration:
                raise ValueError(
                    f"步骤 {step_index}「{step.title}」的画面范围超过原视频时长"
                )
    work_dir = work_dir or project.output_video.parent / ".render-work"
    work_dir.mkdir(parents=True, exist_ok=True)
    voices, voice_durations = _generate_voice(project, work_dir)
    timeline = build_timeline(project, voice_durations)
    font = "/System/Library/Fonts/STHeiti Medium.ttc"
    filter_script = work_dir / "video-filter.txt"
    filter_script.write_text(
        _build_video_filter(project, timeline, media.width, media.height, font),
        encoding="utf-8",
    )
    silent_video = work_dir / "silent.mp4"
    _run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-i",
            str(project.source_video),
            "-filter_complex_script",
            str(filter_script),
            "-map",
            "[vout]",
            "-an",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-movflags",
            "+faststart",
            str(silent_video),
        ]
    )
    cues = [
        NarrationCue(
            start=item.start + 0.3,
            end=item.start + 0.3 + item.voice_duration,
            text=(
                project.intro.narration
                if item.kind == "intro"
                else project.steps[item.index - 1].narration
            ),
        )
        for item in timeline
    ]
    captions = work_dir / "captions.ass"
    write_ass_subtitles(captions, paginate_narration_cues(cues))
    voice_track = work_dir / "voice.m4a"
    master_audio = work_dir / "master.m4a"
    _render_audio(project, timeline, voices, voice_track)
    duration = timeline[-1].start + timeline[-1].duration
    _mix_master_audio(
        voice_track,
        duration,
        master_audio,
        project.background_music,
        project.background_music_file,
    )
    project.output_video.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-i",
            str(silent_video),
            "-i",
            str(master_audio),
            "-vf",
            f"ass={captions}",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(project.output_video),
        ]
    )
    _verify_rendered_output(probe_media(project.output_video), duration)
    manifest = {
        "project": project.model_dump(mode="json"),
        "timeline": [
            {
                "kind": item.kind,
                "index": item.index,
                "start": item.start,
                "duration": item.duration,
                "voice_duration": item.voice_duration,
                "speed": item.speed,
            }
            for item in timeline
        ],
    }
    (project.output_video.parent / f"{project.output_video.stem}.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return project.output_video

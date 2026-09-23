from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NarrationCue:
    start: float
    end: float
    text: str


def paginate_narration_cues(
    cues: list[NarrationCue],
    max_chars_per_line: int = 16,
    max_lines: int = 2,
) -> list[NarrationCue]:
    if max_chars_per_line < 1 or max_lines < 1:
        raise ValueError("caption limits must be positive")
    result: list[NarrationCue] = []
    for cue in cues:
        clauses = re.findall(r"[^，。；！？!?;]+[，。；！？!?;]?", cue.text)
        lines: list[str] = []
        for clause in clauses or [cue.text]:
            lines.extend(
                clause[index : index + max_chars_per_line]
                for index in range(0, len(clause), max_chars_per_line)
            )
        pages = [
            lines[index : index + max_lines]
            for index in range(0, len(lines), max_lines)
        ]
        page_duration = (cue.end - cue.start) / len(pages)
        for index, page in enumerate(pages):
            start = cue.start + index * page_duration
            end = cue.end if index == len(pages) - 1 else start + page_duration
            result.append(NarrationCue(start=start, end=end, text="\n".join(page)))
    return result


def _ass_time(seconds: float) -> str:
    centiseconds = round(seconds * 100)
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    whole_seconds, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{fraction:02d}"


def write_ass_subtitles(path: Path, cues: list[NarrationCue]) -> None:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Caption,Heiti SC,58,&H00FFFFFF,&H00FFFFFF,&H0014212E,&H500A1018,-1,0,0,0,100,100,0,0,3,2,0,2,70,70,105,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = [header]
    for cue in cues:
        text = cue.text.replace("\n", r"\N")
        lines.append(
            "Dialogue: 0,"
            f"{_ass_time(cue.start)},{_ass_time(cue.end)},"
            f"Caption,,0,0,0,,{text}\n"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")

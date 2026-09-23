from pathlib import Path

from tutorial_video.render import NarrationCue, paginate_narration_cues, write_ass_subtitles


def test_write_ass_subtitles_creates_readable_mobile_captions(tmp_path: Path) -> None:
    output = tmp_path / "captions.ass"
    cues = [
        NarrationCue(
            start=1.2,
            end=4.5,
            text="进入示例应用，点击右下角的工具页。",
        )
    ]

    write_ass_subtitles(output, cues)

    content = output.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert "0:00:01.20,0:00:04.50" in content
    assert "进入示例应用，点击右下角的工具页。" in content
    assert "Style: Caption,Heiti SC,58" in content
    assert ",-1,0,0,0,100,100" in content
    assert "&H500A1018" in content
    assert ",3,2,0,2,70,70,105,1" in content


def test_ass_subtitles_escape_newlines_and_commas(tmp_path: Path) -> None:
    output = tmp_path / "captions.ass"

    write_ass_subtitles(
        output,
        [NarrationCue(start=0, end=2, text="第一行，\n第二行")],
    )

    content = output.read_text(encoding="utf-8")
    assert r"第一行，\N第二行" in content


def test_paginate_narration_cues_limits_each_screen_to_two_short_lines() -> None:
    cues = paginate_narration_cues(
        [
            NarrationCue(
                start=0,
                end=8,
                text="进入工具页，打开示例功能。完成设置后，查看处理结果。",
            )
        ],
        max_chars_per_line=8,
        max_lines=2,
    )

    assert cues == [
        NarrationCue(start=0, end=4, text="进入工具页，\n打开示例功能。"),
        NarrationCue(start=4, end=8, text="完成设置后，\n查看处理结果。"),
    ]

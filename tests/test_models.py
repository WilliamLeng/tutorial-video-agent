import pytest
from pydantic import ValidationError

from tutorial_video.models import CourseDraft, TimeRange


def test_time_range_rejects_reversed_values() -> None:
    with pytest.raises(ValidationError):
        TimeRange(start=5.0, end=2.0)


def test_course_draft_tracks_final_edit_decisions() -> None:
    draft = CourseDraft(
        title="示例",
        introduction="功能介绍",
        learning_goal="完成配置",
        original_audio_used=False,
        direct_final_mode=True,
        editing_notes=["删除静态等待"],
        steps=[],
    )

    assert draft.original_audio_used is False
    assert draft.direct_final_mode is True
    assert draft.editing_notes == ["删除静态等待"]

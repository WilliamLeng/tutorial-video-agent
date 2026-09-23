from tutorial_video.models import CourseDraft, CourseStep, MediaInfo, TimeRange
from tutorial_video.validate import validate_draft


def test_step_without_evidence_must_require_review() -> None:
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
        learning_goal="完成测试",
        steps=[
            CourseStep(
                id="step-001",
                title="保存",
                narration="点击保存",
                source_range=TimeRange(start=8, end=12),
                confidence=0.9,
                needs_review=False,
            )
        ],
    )
    assert validate_draft(draft, media) == [
        "step-001: source range exceeds media duration",
        "step-001: step without evidence must require review",
    ]

from tutorial_video.models import CourseDraft, MediaInfo


def validate_draft(draft: CourseDraft, media: MediaInfo) -> list[str]:
    errors = []
    for step in draft.steps:
        if step.source_range.end > media.duration:
            errors.append(f"{step.id}: source range exceeds media duration")
        if not step.evidence and not step.needs_review:
            errors.append(f"{step.id}: step without evidence must require review")
    return errors

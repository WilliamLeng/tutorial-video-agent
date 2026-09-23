from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class TimeRange(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_order(self) -> "TimeRange":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class MediaInfo(BaseModel):
    path: str
    duration: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    has_audio: bool


class TranscriptSegment(BaseModel):
    text: str
    source_range: TimeRange


class Transcript(BaseModel):
    language: str = "zh"
    text: str
    segments: list[TranscriptSegment]


class Evidence(BaseModel):
    kind: Literal["speech", "screen", "transition", "user"]
    description: str
    source_range: Optional[TimeRange] = None
    timestamp: Optional[float] = Field(default=None, ge=0)


class CourseStep(BaseModel):
    id: str
    title: str
    narration: str
    source_range: TimeRange
    output_range: Optional[TimeRange] = None
    click_text: Optional[str] = None
    result: Optional[str] = None
    visual_treatment: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    needs_review: bool
    evidence: list[Evidence] = Field(default_factory=list)


class ReviewIssue(BaseModel):
    id: str
    category: Literal[
        "business_rule",
        "click_target",
        "source_range",
        "privacy",
        "missing_evidence",
    ]
    question: str
    severity: Literal["low", "medium", "high"]


class CourseDraft(BaseModel):
    schema_version: str = "1.0"
    title: str
    introduction: str
    learning_goal: str
    steps: list[CourseStep]
    original_audio_used: bool = False
    direct_final_mode: bool = False
    editing_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    review_issues: list[ReviewIssue] = Field(default_factory=list)

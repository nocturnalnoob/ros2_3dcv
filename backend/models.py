"""Pydantic models shared across the API and the grading orchestrator."""
from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Curriculum models (mirror curriculum/schema.json)
# ---------------------------------------------------------------------------
class Check(BaseModel):
    kind: str
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class Verification(BaseModel):
    strategy: str
    humanDescription: str = ""
    checks: list[Check] = Field(default_factory=list)
    timeoutSeconds: int = 15
    harnessNotes: str = ""


class Exercise(BaseModel):
    prompt: str
    type: Literal["python", "terminal"] = "python"
    editorLanguage: str = "python"
    starterCode: str = ""
    solutionCode: str = ""
    supportFiles: dict[str, str] = Field(default_factory=dict)


class Module(BaseModel):
    id: str
    phase: int
    order: int
    title: str
    topic: str = ""
    estimatedMinutes: int = 30
    learningObjectives: list[str] = Field(default_factory=list)
    quickReference: list[dict[str, str]] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    lesson: dict[str, str]
    exercise: Exercise
    verification: Verification


# ---------------------------------------------------------------------------
# Submission / grading models
# ---------------------------------------------------------------------------
class RunRequest(BaseModel):
    moduleId: str
    code: str = Field(max_length=64_000)
    distro: Literal["humble", "jazzy"] = "humble"


class SubmitRequest(RunRequest):
    pass


class CheckResult(BaseModel):
    kind: str
    passed: bool
    message: str = ""


class Verdict(BaseModel):
    passed: bool
    checks: list[CheckResult] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    durationMs: int = 0
    error: Optional[str] = None

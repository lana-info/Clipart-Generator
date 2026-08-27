"""Workflow definitions for composing mode-specific pages and operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from v3_project_state import ProjectMode, StepId, route_for_mode


_STEP_KINDS: Final[frozenset[str]] = frozenset(
    {"processing", "local_export", "review_gate", "external_delivery"}
)


@dataclass(frozen=True, slots=True)
class WorkflowPageSpec:
    """One page in a workflow route and the component that renders it."""

    step: StepId
    component_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.step, StepId):
            raise TypeError("step must be a StepId")
        if not isinstance(self.component_id, str) or not self.component_id.strip():
            raise ValueError("component_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class WorkflowStepSpec:
    """A workflow operation and its artifact/side-effect contract."""

    step_id: str
    kind: str
    input_artifacts: tuple[str, ...]
    output_artifacts: tuple[str, ...]
    external_side_effect: bool = False
    requires_confirmation: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.step_id, str) or not self.step_id.strip():
            raise ValueError("step_id must be a non-empty string")
        if self.kind not in _STEP_KINDS:
            raise ValueError(f"unsupported workflow step kind: {self.kind!r}")
        if not self.input_artifacts or not self.output_artifacts:
            raise ValueError("workflow steps require input and output artifacts")
        if self.external_side_effect and not self.requires_confirmation:
            raise ValueError("external delivery requires explicit confirmation")


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """Declarative composition contract for one user workflow."""

    workflow_id: str
    mode: ProjectMode
    prompt_builder_id: str
    pages: tuple[WorkflowPageSpec, ...]
    processing_operations: tuple[str, ...] = ()
    post_steps: tuple[WorkflowStepSpec, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_id, str) or not self.workflow_id.strip():
            raise ValueError("workflow_id must be a non-empty string")
        if not isinstance(self.mode, ProjectMode):
            raise TypeError("mode must be a ProjectMode")
        if not isinstance(self.prompt_builder_id, str) or not self.prompt_builder_id.strip():
            raise ValueError("prompt_builder_id must be a non-empty string")
        if not self.pages:
            raise ValueError("a workflow must define at least one page")
        page_steps = [page.step for page in self.pages]
        if len(page_steps) != len(set(page_steps)):
            raise ValueError("workflow pages must have unique steps")
        for operation in self.processing_operations:
            if not isinstance(operation, str) or not operation.strip():
                raise ValueError("processing operations must be non-empty strings")
        step_ids = [step.step_id for step in self.post_steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("workflow post steps must have unique IDs")

    @property
    def page_steps(self) -> tuple[StepId, ...]:
        return tuple(page.step for page in self.pages)

    def page_for_step(self, step: StepId) -> WorkflowPageSpec:
        for page in self.pages:
            if page.step is step:
                return page
        raise KeyError(step)

    def allows_processing_operation(self, operation: str) -> bool:
        return operation in self.processing_operations


def _default_pages(mode: ProjectMode) -> tuple[WorkflowPageSpec, ...]:
    return tuple(
        WorkflowPageSpec(step, f"shared.{step.value}")
        for step in route_for_mode(mode)
    )


_CLIPART_OPERATIONS: Final[tuple[str, ...]] = (
    "visible_mark_cleanup",
    "upscale_before",
    "unsharp",
    "remove_background",
    "upscale_after",
    "edge_shrink",
    "trim",
    "metadata_cleanup",
)

_PINTEREST_OPERATIONS: Final[tuple[str, ...]] = (
    "upscale_before",
    "unsharp",
    "upscale_after",
)


_WORKFLOWS: Final[dict[ProjectMode, WorkflowDefinition]] = {
    ProjectMode.CLIPART: WorkflowDefinition(
        workflow_id="clipart",
        mode=ProjectMode.CLIPART,
        prompt_builder_id="clipart_structured",
        pages=_default_pages(ProjectMode.CLIPART),
        processing_operations=_CLIPART_OPERATIONS,
        post_steps=(
            WorkflowStepSpec(
                "save_png",
                "local_export",
                ("processed_image",),
                ("png",),
            ),
        ),
    ),
    ProjectMode.PINTEREST: WorkflowDefinition(
        workflow_id="pinterest",
        mode=ProjectMode.PINTEREST,
        prompt_builder_id="pinterest_structured",
        pages=_default_pages(ProjectMode.PINTEREST),
        processing_operations=_PINTEREST_OPERATIONS,
        post_steps=(
            WorkflowStepSpec(
                "save_png",
                "local_export",
                ("processed_image",),
                ("png",),
            ),
        ),
    ),
    ProjectMode.PROCESSING: WorkflowDefinition(
        workflow_id="processing",
        mode=ProjectMode.PROCESSING,
        prompt_builder_id="none",
        pages=_default_pages(ProjectMode.PROCESSING),
        processing_operations=_CLIPART_OPERATIONS,
        post_steps=(
            WorkflowStepSpec(
                "save_png",
                "local_export",
                ("processed_image",),
                ("png",),
            ),
        ),
    ),
}


def workflow_for_mode(mode: ProjectMode | str) -> WorkflowDefinition:
    normalized = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
    return _WORKFLOWS[normalized]


__all__ = [
    "WorkflowDefinition",
    "WorkflowPageSpec",
    "WorkflowStepSpec",
    "workflow_for_mode",
]

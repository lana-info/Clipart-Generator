"""Text-only architecture probe for scoped Studio capabilities."""
from studio_job_api import JobRequest
from studio_module_api import (
    CapabilityRequirement,
    CommandDeclaration,
    DocumentTypeDeclaration,
    ModuleRegistration,
    PageDeclaration,
)
from studio_project_api import ProjectDocument
from studio_provider_api import ProviderOperationRequest

_TEXT = CapabilityRequirement("providers.text", 1)
_PROJECTS = CapabilityRequirement("projects", 1)
_JOBS = CapabilityRequirement("jobs", 1)
_text = None
_projects = None
_jobs = None


def bind(context):
    global _text, _projects, _jobs
    if hasattr(context, "services"):
        raise ValueError("capability context exposed legacy services")
    _text = context.capabilities.require(_TEXT)
    _projects = context.capabilities.require(_PROJECTS)
    _jobs = context.capabilities.require(_JOBS)


def _normalize(value):
    result = _text.execute(ProviderOperationRequest(
        "normalize", "text-probe-model", {"text": str(value)},
    ))
    return str(result["text"])


def _create_note(name, body):
    document = _projects.create("note", str(name), {"body": str(body)})
    if not isinstance(document, ProjectDocument):
        raise RuntimeError("projects.v1 returned an invalid document")
    return document.project_id


def _read_note(project_id):
    document = _projects.open(str(project_id))
    if not isinstance(document, ProjectDocument):
        raise RuntimeError("projects.v1 returned an invalid document")
    return str(document.state["body"])


def _run_job(text):
    return _jobs.submit(JobRequest("normalize_job", {"text": str(text)})).job_id


def _home_page():
    return "text-probe.home"


def register(context):
    if hasattr(context, "services"):
        raise ValueError("public module context exposed legacy services")
    return ModuleRegistration(
        context.module_id,
        context.version,
        pages=(PageDeclaration("home", _home_page),),
        commands=(
            CommandDeclaration("normalize", _normalize),
            CommandDeclaration("create_note", _create_note),
            CommandDeclaration("read_note", _read_note),
            CommandDeclaration("run_job", _run_job),
        ),
        document_types=(DocumentTypeDeclaration(
            "note", "application/vnd.vibix.text-probe+json", 1,
        ),),
        capabilities=(_TEXT, _PROJECTS, _JOBS),
    )

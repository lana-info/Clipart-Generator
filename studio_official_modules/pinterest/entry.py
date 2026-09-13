"""Initial Pinterest module adapter; existing workflow behavior stays in the host.

This source is packaged and publisher-signed before ModuleRuntimeHost loads it.
No board creation, scheduling, external publication or paid calls occur here.
"""
from functools import partial

from studio_module_api import (
    CommandDeclaration, DocumentTypeDeclaration, ModuleRegistration, PageDeclaration,
)


def register(context):
    workflow_provider = context.services.get("legacy_workflow")
    page_factory = context.services.get("legacy_page_factory")
    if not callable(workflow_provider) or not callable(page_factory):
        raise ValueError("Pinterest requires legacy workflow and page services")
    workflow = workflow_provider("pinterest")
    if workflow.workflow_id != "pinterest":
        raise ValueError("Pinterest workflow identity mismatch")
    return ModuleRegistration(
        module_id=context.module_id,
        version=context.version,
        pages=tuple(PageDeclaration(
            page.step.value,
            partial(page_factory, "pinterest", page.component_id),
        ) for page in workflow.pages),
        commands=(CommandDeclaration("workflow", lambda: workflow),),
        document_types=(DocumentTypeDeclaration(
            "project", "application/vnd.vibix.pinterest-project+json", 1,
        ),),
    )

from studio_module_api import DocumentTypeDeclaration, ModuleRegistration


def register(context):
    return ModuleRegistration(
        context.module_id,
        context.version,
        document_types=(DocumentTypeDeclaration(
            "project", "application/vnd.vibix.processing-project+json", 1,
        ),),
    )


def install(host, *, locale):
    from v3_processing_flow import install_processing_flow
    return install_processing_flow(host)

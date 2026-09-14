from studio_module_api import DocumentTypeDeclaration, ModuleRegistration


def register(context):
    return ModuleRegistration(
        context.module_id,
        context.version,
        document_types=(DocumentTypeDeclaration(
            "project", "application/vnd.vibix.pinterest-project+json", 1,
        ),),
    )


def install(host, *, locale):
    from v3_pinterest_flow import install_pinterest_flow
    return install_pinterest_flow(host, locale=locale)

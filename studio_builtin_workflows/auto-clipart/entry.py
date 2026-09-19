from studio_module_api import DocumentTypeDeclaration, ModuleRegistration


def register(context):
    return ModuleRegistration(context.module_id, context.version,
        document_types=(DocumentTypeDeclaration(
            "project", "application/vnd.vibix.auto-clipart-project+json", 1,
        ),))


def install(host, *, locale):
    from studio_auto_clipart_flow import install_auto_clipart_flow
    return install_auto_clipart_flow(host)


def project_state_extension():
    from studio_auto_clipart_state import AutoClipartStateExtension
    return AutoClipartStateExtension()

from studio_module_api import DocumentTypeDeclaration, ModuleRegistration


def register(context):
    return ModuleRegistration(
        context.module_id,
        context.version,
        document_types=(DocumentTypeDeclaration(
            "project", "application/vnd.vibix.clipart-project+json", 1,
        ),),
    )



def install(host, *, locale):
    from v3_clipart_flow import install_clipart_flow
    return install_clipart_flow(host)


def project_state_extension():
    from clipart_project_state import ClipartProjectStateExtension
    return ClipartProjectStateExtension()

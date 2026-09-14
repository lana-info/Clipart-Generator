from studio_module_api import DocumentTypeDeclaration, ModuleRegistration


def register(context):
    return ModuleRegistration(
        context.module_id,
        context.version,
        document_types=(DocumentTypeDeclaration(
            "project", "application/vnd.vibix.clipart-project+json", 1,
        ),),
    )


def install(shell, *, runtime_settings_provider, worker_factory, authorization_provider, locale):
    from v3_clipart_flow import install_clipart_flow
    return install_clipart_flow(
        shell,
        runtime_settings_provider=runtime_settings_provider,
        worker_factory=worker_factory,
        authorization_provider=authorization_provider,
    )

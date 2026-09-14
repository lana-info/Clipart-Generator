MODULE_ID = "processing"


def install(shell, *, runtime_settings_provider, worker_factory, authorization_provider, locale):
    from v3_processing_flow import install_processing_flow
    return install_processing_flow(
        shell,
        runtime_settings_provider=runtime_settings_provider,
        worker_factory=worker_factory,
        authorization_provider=authorization_provider,
    )

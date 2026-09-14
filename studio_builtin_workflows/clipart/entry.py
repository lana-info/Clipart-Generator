MODULE_ID = "clipart"


def install(shell, *, runtime_settings_provider, worker_factory, authorization_provider, locale):
    from v3_clipart_flow import install_clipart_flow
    return install_clipart_flow(
        shell,
        runtime_settings_provider=runtime_settings_provider,
        worker_factory=worker_factory,
        authorization_provider=authorization_provider,
    )

MODULE_ID = "pinterest"


def install(shell, *, runtime_settings_provider, worker_factory, authorization_provider, locale):
    from v3_pinterest_flow import install_pinterest_flow
    return install_pinterest_flow(
        shell,
        runtime_settings_provider=runtime_settings_provider,
        worker_factory=worker_factory,
        authorization_provider=authorization_provider,
        locale=locale,
    )

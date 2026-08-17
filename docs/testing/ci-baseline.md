# Test baseline

## Default command

```bash
python -m pytest -q
```

The repository pytest configuration excludes only tests marked `network` or
`paid`. Those tests remain collected and can be run explicitly with:

```bash
python -m pytest -q -m "network or paid"
```

The default suite is offline, does not use a user config, and does not spend
provider credits. `--collect-only` is a separate CI step so an accidental test
discovery/import failure cannot look like a successful empty run.

## Windows-only acceptance

Linux offscreen checks do not replace packaged Windows verification. Before a
release, run the manual checklist for installer startup, online license
activation, updater consent/download/hash verification, SmartScreen behavior,
and Windows visual layout. The release workflow is manual and is not started by
ordinary pushes.

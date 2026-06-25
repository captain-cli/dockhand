# Dockhand Integration Contract

Dockhand is a standalone runtime wiring tool. Other tools, including Captain, should treat Dockhand as an optional executable dependency and call its CLI rather than importing its internals.

## Stable commands

```bash
dockhand --version
dockhand init --output manifest/dockhand.json
dockhand ports validate --config manifest/dockhand.json --json
dockhand ports plan --config manifest/dockhand.json --json
dockhand ports apply --config manifest/dockhand.json --json
```

## Captain-facing behavior

- `ports validate` validates manifest shape and identity/env-var uniqueness without writing files.
- `ports plan` returns planned allocations without writing reservation files, `.env` files, DB settings, or firewall rules.
- `ports apply` allocates/reuses ports and writes outputs requested by the manifest/CLI flags.
- `--print-env` prints `KEY=value` assignments for planned/applied results.
- Explicit CLI flags override manifest defaults.

## JSON result shape

```json
{
  "results": [
    {
      "projectName": "example",
      "applicationName": "api",
      "settingName": "port",
      "envVar": "EXAMPLE_API_PORT",
      "port": 41000,
      "protocol": "tcp",
      "host": "0.0.0.0",
      "reservedPortsFile": "config/reserved-ports.json",
      "envFile": ".env",
      "databaseEnabled": false,
      "firewallOpened": false,
      "dryRun": true
    }
  ]
}
```

## Minimal missing-tool guidance

If a caller cannot find `dockhand`, it should show a standalone command such as:

```bash
python -m pip install git+ssh://git@github.com/captain-cli/dockhand.git
```

Callers should not auto-install Dockhand unless the user explicitly asks for that behavior.

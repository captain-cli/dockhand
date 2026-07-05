# Dockhand

Dockhand is a lightweight, project-agnostic CLI for runtime port allocation and environment wiring.

It can:

- allocate or reuse service ports
- write `.env` variables
- maintain a JSON reservation file
- optionally read/write MySQL/MariaDB settings
- optionally open firewall rules
- run as a standalone tool without Captain

Dockhand belongs to the `captain-cli` tool family, but it does **not** require Captain.

## Install for local development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[test]"
```

Verify:

```bash
dockhand --version
dockhand --help
pytest -q
```

## No-install development mode

```bash
PYTHONPATH=src python -m dockhand.cli --version
PYTHONPATH=src python -m dockhand.cli ports plan --config examples/dockhand.json
```

## Initialize a project

```bash
dockhand init --project-name my-project --output manifest/dockhand.json
```

This creates a starter manifest at `manifest/dockhand.json`.

## Manifest convention

Recommended project layout:

```text
project/
  manifest/
    dockhand.json
  config/
    reserved-ports.json
  .env
```

Example manifest:

```json
{
  "projectName": "my-project",
  "defaults": {
    "startPort": 41000,
    "endPort": 41999,
    "host": "0.0.0.0",
    "protocol": "tcp",
    "envFile": ".env",
    "reservedPortsFile": "config/reserved-ports.json",
    "writeEnv": true
  },
  "applications": [
    {
      "applicationName": "api",
      "settingName": "port",
      "settingDescription": "API HTTP port"
    }
  ]
}
```

## Commands

### Validate

```bash
dockhand ports validate --config manifest/dockhand.json
```

JSON output:

```bash
dockhand ports validate --config manifest/dockhand.json --json
```

### Plan

Dry-run allocations without writing files, DB settings, or firewall rules:

```bash
dockhand ports plan --config manifest/dockhand.json --json
```

### Apply

Allocate/reuse ports and write requested outputs:

```bash
dockhand ports apply --config manifest/dockhand.json --json
```

### Print env assignments

```bash
dockhand ports plan --config manifest/dockhand.json --print-env
```

Example:

```env
MY_PROJECT_API_PORT=41000
MY_PROJECT_WORKER_PORT=41001
```

## CLI precedence

In batch mode, precedence is:

```text
argparse defaults < manifest top-level < manifest defaults < application entry < explicit CLI flags
```

So this command forces output files even if the manifest has different defaults:

```bash
dockhand ports apply \
  --config manifest/dockhand.json \
  --reserved-ports-file /tmp/reserved.json \
  --env-file /tmp/app.env \
  --write-env
```

## Legacy command compatibility

The original flat command still works:

```bash
dockhand --applications-file examples/dockhand.json --json
```

It behaves like:

```bash
dockhand ports apply --config examples/dockhand.json --json
```


## Servicewright reconciliation

Dockhand can now run before Servicewright in a monorepo deployment pipeline.
Dockhand reads `servicewright.json`, tries to honor each service's existing
`runtime.port`, assigns another port if the requested port is unavailable or
already assigned to another service, then writes a resolved Servicewright config
plus per-service env files.

Recommended flow:

```text
Dockhand servicewright reconcile
  -> .captain/runtime/servicewright.resolved.json
  -> .captain/runtime/environment/*.env
Servicewright generate
  -> systemd_units/*.service
```

Example Servicewright config committed to the project repo:

```json
{
  "projectName": "my-monorepo",
  "services": [
    {
      "name": "auth-api",
      "description": "Authentication API",
      "type": "system",
      "environmentFile": ".captain/runtime/environment/auth-api.env",
      "runtime": {
        "host": "0.0.0.0",
        "port": 6751,
        "portRange": [6700, 6799]
      }
    },
    {
      "name": "media-api",
      "description": "Media API",
      "type": "system",
      "environmentFile": ".captain/runtime/environment/media-api.env",
      "runtime": {
        "host": "0.0.0.0",
        "port": 6752,
        "portRange": [6700, 6799]
      }
    }
  ]
}
```

Reconcile it:

```bash
dockhand servicewright reconcile \
  --config servicewright.json \
  --root . \
  --write-config .captain/runtime/servicewright.resolved.json \
  --write-env .captain/runtime/environment \
  --json
```

Dry-run first:

```bash
dockhand servicewright reconcile \
  --config servicewright.json \
  --write-config .captain/runtime/servicewright.resolved.json \
  --write-env .captain/runtime/environment \
  --dry-run \
  --json
```

Port resolution rules:

```text
requested port is free -> keep it
requested port is already reserved for the same service -> keep it
requested port is already assigned in this run -> assign next available port
requested port is unavailable/unowned -> assign next available port
no requested port -> assign first available port from the service range
```

Dockhand updates only runtime-owned fields in the resolved config:

```text
runtime.host
runtime.port
runtime.protocol
runtime.requestedPort, when reassigned
runtime.assignedBy
runtime.assignmentReason
environmentFile, when --write-env is supplied
```

The generated env file contains:

```env
SERVICE_NAME=media-api
HOST=0.0.0.0
PORT=6752
```

Then Servicewright consumes the resolved config:

```bash
servicewright generate \
  --config .captain/runtime/servicewright.resolved.json \
  --root . \
  --output-dir ./systemd_units
```

## Optional Captain integration

Captain should treat Dockhand as optional. A project can use Dockhand directly:

```bash
dockhand ports apply --config manifest/dockhand.json
```

Captain can later delegate to Dockhand when a project opts in:

```bash
captain prepare-runtime --plan
```

Internally, Captain should call:

```bash
dockhand ports plan --config manifest/dockhand.json --json
```

See [`docs/INTEGRATION_CONTRACT.md`](docs/INTEGRATION_CONTRACT.md).

## Test

```bash
python -m py_compile src/dockhand/*.py
pytest -q
```

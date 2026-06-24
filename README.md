# Dockhand

A project-agnostic Python utility for finding, reserving, and optionally publishing available TCP/UDP ports for one service or a whole application manifest.

It was designed to replace project-specific installer scripts that hardcode app names, config paths, environment variable mappings, database settings, and firewall behavior.

---

## What it does

`dockhand` allocates a stable port for an application setting such as:

- `metadata-api:port`
- `audio-engine:httpPort`
- `worker:socketPort`
- `video-analysis:port`

It tries to reuse existing reservations before assigning a new port.

Reservation priority:

1. Existing DB setting, when `--enable-db` is used.
2. Existing `.env` value.
3. Existing JSON reservation file value.
4. First available unreserved port in the configured range.

---

## Features

- Single service mode.
- Batch mode using an applications JSON file.
- Project namespace support.
- TCP or UDP port checks.
- Existing `.env` value detection.
- Optional `.env` writing.
- JSON reservation file persistence.
- Optional MySQL/MariaDB read/write support.
- Configurable DB table and column names.
- Optional UFW / Windows Firewall opening.
- JSON output for automation.
- Shell-friendly plain-text output.
- No hardcoded Crispy Disco assumptions.

---

## Requirements

### Basic usage

Only Python 3 is required.

```bash
python3 --version
```

### Optional database support

Install `mysql-connector-python` only when using `--enable-db`:

```bash
python3 -m pip install mysql-connector-python
```

### Optional firewall support

Firewall changes are not automatic. They only happen when `--open-firewall` is passed.

- Linux: uses `ufw` when available and active.
- Windows: uses `netsh advfirewall`.

Use `--require-admin-for-firewall` if you want the script to fail when it cannot run with elevated privileges.

---

## Installation

Run install commands from the repository root, which is the folder containing `pyproject.toml`.

Editable local development install:

```bash
python3 -m pip install -e .
```

Then verify the CLI entrypoint:

```bash
dockhand --help
```

You can also run it without installing by setting `PYTHONPATH` from the repo root:

```bash
PYTHONPATH=src python3 -m dockhand.cli --help
```

---

## Files produced

The utility can maintain two kinds of local config files.

### Reservation file

A JSON file tracking known port reservations.

Example:

```json
{
  "crispy-metadata-enrichment:metadata-api:port": {
    "application_name": "metadata-api",
    "description": "Metadata enrichment API HTTP port",
    "env_var": "CRISPY_METADATA_ENRICHMENT_METADATA_API_PORT",
    "port": 41000,
    "project_name": "crispy-metadata-enrichment",
    "protocol": "tcp",
    "setting_name": "port"
  }
}
```

### Environment file

A standard `.env` file can be read and optionally updated.

Example:

```env
CRISPY_METADATA_ENRICHMENT_METADATA_API_PORT=41000
CRISPY_METADATA_ENRICHMENT_VIDEO_ANALYSIS_PORT=41001
WORKER_SOCKET_PORT=41002
```

---

## Single service usage

### Allocate a port

```bash
dockhand \
  --project-name crispy-metadata-enrichment \
  --application-name metadata-api \
  --setting-name port \
  --start-port 41000 \
  --end-port 41999 \
  --reserved-ports-file ./config/reserved-ports.json
```

Output:

```text
41000
```

### JSON output

```bash
dockhand \
  --project-name crispy-metadata-enrichment \
  --application-name metadata-api \
  --setting-name port \
  --start-port 41000 \
  --end-port 41999 \
  --reserved-ports-file ./config/reserved-ports.json \
  --json
```

Output:

```json
{
  "applicationName": "metadata-api",
  "databaseEnabled": false,
  "envFile": null,
  "envVar": "CRISPY_METADATA_ENRICHMENT_METADATA_API_PORT",
  "firewallOpened": false,
  "host": "0.0.0.0",
  "port": 41000,
  "projectName": "crispy-metadata-enrichment",
  "protocol": "tcp",
  "reservedPortsFile": "./config/reserved-ports.json",
  "settingName": "port"
}
```

---

## Environment file usage

### Read an existing `.env` reservation

```bash
dockhand \
  --project-name crispy-metadata-enrichment \
  --application-name metadata-api \
  --setting-name port \
  --env-file ./.env \
  --reserved-ports-file ./config/reserved-ports.json
```

By default, the env var name is generated from:

```text
PROJECT_APPLICATION_SETTING
```

Example:

```text
crispy-metadata-enrichment + metadata-api + port
```

becomes:

```text
CRISPY_METADATA_ENRICHMENT_METADATA_API_PORT
```

### Write the selected port to `.env`

```bash
dockhand \
  --project-name crispy-metadata-enrichment \
  --application-name metadata-api \
  --setting-name port \
  --env-file ./.env \
  --write-env \
  --reserved-ports-file ./config/reserved-ports.json
```

### Use a custom env var name

```bash
dockhand \
  --project-name crispy-metadata-enrichment \
  --application-name metadata-api \
  --setting-name port \
  --env-file ./.env \
  --env-var METADATA_API_PORT \
  --write-env \
  --reserved-ports-file ./config/reserved-ports.json
```

---

## Batch mode

Batch mode allows one command to allocate ports for many applications.

```bash
dockhand \
  --applications-file ./applications.json \
  --json
```

### Batch output without `--json`

```text
metadata-api:port=41000
video-analysis:port=41001
worker:socketPort=41002
```

### Batch output with `--json`

```json
{
  "results": [
    {
      "applicationName": "metadata-api",
      "envVar": "CRISPY_METADATA_ENRICHMENT_METADATA_API_PORT",
      "port": 41000,
      "projectName": "crispy-metadata-enrichment",
      "settingName": "port"
    }
  ]
}
```

---

## Applications manifest format

The manifest can be either:

1. A JSON object with `projectName`, `defaults`, and `applications`.
2. A bare JSON array of application entries.

The object format is recommended.

```json
{
  "projectName": "crispy-metadata-enrichment",
  "defaults": {
    "startPort": 41000,
    "endPort": 41999,
    "host": "0.0.0.0",
    "protocol": "tcp",
    "envFile": "./.env",
    "reservedPortsFile": "./config/reserved-ports.json",
    "writeEnv": true
  },
  "applications": [
    {
      "applicationName": "metadata-api",
      "settingName": "port",
      "settingDescription": "Metadata enrichment API HTTP port"
    },
    {
      "applicationName": "video-analysis",
      "settingName": "port",
      "settingDescription": "Video analysis lane HTTP port"
    },
    {
      "applicationName": "worker",
      "settingName": "socketPort",
      "envVar": "WORKER_SOCKET_PORT",
      "settingDescription": "Worker socket listener port"
    }
  ]
}
```

### Key naming

Manifest keys may use camelCase or snake_case.

Both are valid:

```json
{
  "applicationName": "metadata-api",
  "settingName": "port"
}
```

```json
{
  "application_name": "metadata-api",
  "setting_name": "port"
}
```

Unknown keys fail fast so typos do not silently create bad config.

---

## Manifest field reference

### Top-level fields

| Field | Type | Description |
|---|---:|---|
| `projectName` | string | Project namespace used for env var names, reservations, and firewall rule names. |
| `defaults` | object | Default options applied to every application entry. |
| `applications` | array | List of app/setting port requests. |

### Common defaults

| Field | Type | Default | Description |
|---|---:|---:|---|
| `startPort` | number | `3000` | Start of allocation range. |
| `endPort` | number | `65000` | End of allocation range. |
| `host` | string | `0.0.0.0` | Host/interface used for bind availability check. |
| `protocol` | string | `tcp` | `tcp` or `udp`. |
| `envFile` | string/null | `null` | `.env` file to read/write. |
| `reservedPortsFile` | string/null | per-user config path | JSON reservation file. |
| `writeEnv` | boolean | `false` | Whether to update `envFile`. |
| `enableDb` | boolean | `false` | Whether to use MySQL/MariaDB. |
| `dbSkipWrite` | boolean | `false` | Read from DB but skip DB writeback. |
| `openFirewall` | boolean | `false` | Open selected ports in firewall. |
| `json` | boolean | `false` | Prefer CLI `--json`; included here for completeness. |

### Application fields

| Field | Type | Required | Description |
|---|---:|---:|---|
| `applicationName` | string | yes | Application/service name. |
| `settingName` | string | no | Setting name. Defaults to `port`. |
| `settingDescription` | string | no | Description stored in JSON/DB. |
| `envVar` | string | no | Explicit env var name. Otherwise generated. |
| `startPort` | number | no | Per-app range override. |
| `endPort` | number | no | Per-app range override. |
| `host` | string | no | Per-app host override. |
| `protocol` | string | no | Per-app protocol override. |

---

## Database mode

Database mode is optional.

```bash
dockhand \
  --project-name crispy-metadata-enrichment \
  --application-name metadata-api \
  --setting-name port \
  --enable-db \
  --db-host 127.0.0.1 \
  --db-user root \
  --db-password '' \
  --db-name crispy-settings \
  --reserved-ports-file ./config/reserved-ports.json
```

### Default DB table shape

By default, the script expects this kind of table:

```sql
CREATE TABLE application_settings (
  application_name varchar(255) NOT NULL,
  application_setting_name varchar(255) NOT NULL,
  application_setting_value varchar(255) NOT NULL,
  application_setting_description varchar(255) NULL,
  last_modified_userid int NOT NULL DEFAULT 0,
  PRIMARY KEY (application_name, application_setting_name)
);
```

### Custom DB columns

Use these flags if your table uses different names:

```bash
--db-table app_config \
--db-application-column app_name \
--db-setting-column setting_key \
--db-value-column setting_value \
--db-description-column description \
--db-modified-userid-column modified_by
```

### DB env vars

The script can read database connection values from the configured `.env` file or process environment.

Supported generic names:

```env
DB_HOST=127.0.0.1
DB_USER=root
DB_PASSWORD=
DB_NAME=crispy-settings
DB_PORT=3306
```

Backward-compatible names are also recognized:

```env
DB_PASS=
CRISPY_DB_HOST=127.0.0.1
CRISPY_DB_USER=root
CRISPY_DB_PASS=
```

---

## Firewall mode

Firewall updates are skipped unless explicitly requested.

```bash
dockhand \
  --project-name crispy-metadata-enrichment \
  --application-name metadata-api \
  --setting-name port \
  --open-firewall
```

Require elevated privileges:

```bash
dockhand \
  --project-name crispy-metadata-enrichment \
  --application-name metadata-api \
  --setting-name port \
  --open-firewall \
  --require-admin-for-firewall
```

---

## Recommended project layout

```text
my-project/
  config/
    applications.json
    reserved-ports.json
  .env
  scripts/
    dockhand
```

Example command from the project root:

```bash
python3 scripts/dockhand \
  --applications-file config/applications.json \
  --json
```

---

## Crispy Metadata Enrichment example

For the C++/MySQL service that scans files, calculates BPM, and updates the database, a practical manifest could look like this:

```json
{
  "projectName": "crispy-metadata-enrichment",
  "defaults": {
    "startPort": 41000,
    "endPort": 41999,
    "host": "0.0.0.0",
    "protocol": "tcp",
    "envFile": "./.env",
    "reservedPortsFile": "./config/reserved-ports.json",
    "writeEnv": true
  },
  "applications": [
    {
      "applicationName": "metadata-api",
      "settingName": "port",
      "settingDescription": "Metadata enrichment API HTTP port"
    },
    {
      "applicationName": "audio-analysis",
      "settingName": "port",
      "settingDescription": "Audio BPM analysis service port"
    },
    {
      "applicationName": "video-analysis",
      "settingName": "port",
      "settingDescription": "Video analysis lane service port"
    },
    {
      "applicationName": "worker",
      "settingName": "socketPort",
      "envVar": "WORKER_SOCKET_PORT",
      "settingDescription": "Worker socket listener port"
    }
  ]
}
```

---

## CLI reference

```text
identity:
  --project-name
  --application-name
  --setting-name
  --setting-description
  --applications-file

port selection:
  --start-port
  --end-port
  --host
  --protocol tcp|udp

files:
  --env-file
  --env-var
  --reserved-ports-file
  --write-env

database optional:
  --enable-db
  --db-host
  --db-user
  --db-password
  --db-name
  --db-port
  --db-table
  --db-application-column
  --db-setting-column
  --db-value-column
  --db-description-column
  --db-modified-userid-column
  --modified-userid
  --db-skip-write

firewall optional:
  --open-firewall
  --firewall-comment
  --require-admin-for-firewall

output:
  --json
  --quiet
```

---

## Behavior notes

### Existing reserved ports are reused

If a reservation already exists and the port is still available, it is reused.

### Busy ports are skipped

If a reserved or env-defined port is already bound by another process, the script skips it and allocates the next available port.

### Existing `.env` values win before JSON reservation file values

The priority is DB, env, JSON, then new allocation.

### Batch mode writes once

In batch mode, all app reservations are loaded into memory and saved once after the batch completes.

---

## Troubleshooting

### `--write-env requires --env-file`

You passed `--write-env` without an explicit env file. Add:

```bash
--env-file ./.env
```

### `--application-name is required unless --applications-file is provided`

Single mode needs an application name. Batch mode needs an applications file.

### `mysql-connector-python is required when --enable-db is used`

Install the optional dependency:

```bash
python3 -m pip install mysql-connector-python
```

### `No available TCP port found in range ...`

The entire range is blocked by existing reservations or currently bound sockets. Use a wider range or clear stale reservations.

### Firewall did not update

Firewall mode is opt-in. Pass `--open-firewall`. On Linux, UFW must be installed and active. On Windows, run from an elevated shell.

---

## Exit behavior

- On success, prints the selected port or result list.
- On failure, prints a clear error to stderr and exits non-zero.
- Unknown manifest keys fail immediately.
- Invalid DB table/column identifiers fail immediately.

---

## Suggested automation flow

For installers or CI scripts:

```bash
python3 scripts/dockhand \
  --applications-file config/applications.json \
  --json > config/allocated-ports.json
```

Then your installer can consume:

- `.env`
- `config/reserved-ports.json`
- `config/allocated-ports.json`

This keeps project-specific application definitions in JSON and keeps the locator reusable across projects.

# Generic Port Locator Test Report

Date: 2026-06-23

## Environment

- Python: Python 3.13.5
- Script: `/mnt/data/generic_port_locator.py`
- Test workspace: `/tmp/port-locator-tests.o5Nlnp`

## Tests Run

| # | Test | Result | Notes |
|---:|---|---|---|
| 1 | Python compilation | PASS | `python3 -m py_compile /mnt/data/generic_port_locator.py` completed successfully. |
| 2 | Single JSON allocation | PASS | Allocated port `43000` within configured range. |
| 3 | Reservation reuse | PASS | Reused the existing `test-suite:api:port` reservation. |
| 4 | `.env` writing with custom env var | PASS | Wrote `WORKER_SOCKET_PORT=<port>` to `.env`. |
| 5 | Batch manifest mode | PASS | Allocated 3 unique ports and wrote both `.env` and reservation JSON. |
| 6 | Busy port skip | PASS | Bound port `43200` before running; allocator skipped it and selected `43201`. |
| 7 | Invalid manifest key failure | PASS | Unknown key was rejected with a clear error. |

## Generated Test Artifacts

```text
.env
apps.json
bad-apps.json
bad.err
bad.out
bad2.err
bad2.out
batch-reserved.json
batch.env
batch.json
busy-reserved.json
env_port.txt
reserved.json
single.json
```

## Batch Test Output

```json
{
  "results": [
    {
      "applicationName": "metadata-api",
      "databaseEnabled": false,
      "envFile": "/tmp/port-locator-tests.o5Nlnp/batch.env",
      "envVar": "BATCH_DEMO_METADATA_API_PORT",
      "firewallOpened": false,
      "host": "0.0.0.0",
      "port": 43100,
      "projectName": "batch-demo",
      "protocol": "tcp",
      "reservedPortsFile": "/tmp/port-locator-tests.o5Nlnp/batch-reserved.json",
      "settingName": "port"
    },
    {
      "applicationName": "video-analysis",
      "databaseEnabled": false,
      "envFile": "/tmp/port-locator-tests.o5Nlnp/batch.env",
      "envVar": "BATCH_DEMO_VIDEO_ANALYSIS_PORT",
      "firewallOpened": false,
      "host": "0.0.0.0",
      "port": 43101,
      "projectName": "batch-demo",
      "protocol": "tcp",
      "reservedPortsFile": "/tmp/port-locator-tests.o5Nlnp/batch-reserved.json",
      "settingName": "port"
    },
    {
      "applicationName": "worker",
      "databaseEnabled": false,
      "envFile": "/tmp/port-locator-tests.o5Nlnp/batch.env",
      "envVar": "WORKER_SOCKET_PORT",
      "firewallOpened": false,
      "host": "0.0.0.0",
      "port": 43102,
      "projectName": "batch-demo",
      "protocol": "tcp",
      "reservedPortsFile": "/tmp/port-locator-tests.o5Nlnp/batch-reserved.json",
      "settingName": "socketPort"
    }
  ]
}

```

## Batch .env Output

```env
BATCH_DEMO_METADATA_API_PORT=43100

BATCH_DEMO_VIDEO_ANALYSIS_PORT=43101

WORKER_SOCKET_PORT=43102

```

## Conclusion

The utility is ready for project-level use in both single-service and batch-manifest mode. The tested non-DB path covers the default portable workflow. Database mode remains dependent on a live MySQL/MariaDB instance and `mysql-connector-python`, so it should be integration-tested inside a project environment that has the target settings table available.

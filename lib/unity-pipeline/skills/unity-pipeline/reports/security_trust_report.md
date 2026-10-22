# Security Trust Report

- OK: `True`
- Scanned files: `14`
- Scripts: `4`
- Internal script modules: `0`
- Secret findings: `0`
- Network-capable scripts: `0`
- Network policy covered scripts: `0`
- Network policy missing scripts: `0`
- File-write scripts: `1`
- Permission approvals: `1 / 2`
- Permission approval gaps: `1`
- CLI help smoke checked: `4`
- CLI help smoke failures: `0`
- Interactive scripts: `0`
- Package hash scope: `source-contract-without-generated-reports`
- Package hash files: `14`
- Package SHA256: `5575139fdc7bb49b9e851743f681d45bd378f609b84bd968658ba535e24264d4`

## Failures

- None

## Warnings

- No dependency or lock file detected
- Permission approvals missing: file_write

## Dependency Evidence

- Files: `none`
- Pinned entries: `0`
- Unpinned entries: `0`

## Network Policy

- Policy file: `security/network_policy.json`
- Present: `False`
- Covered scripts: `0`
- Missing scripts: `none`
- Mismatches: `0`

## Permission Governance

- Policy file: `security/permission_policy.json`
- Present: `True`
- Required capabilities: `file_write, subprocess`
- Approved capabilities: `subprocess`
- Missing approvals: `file_write`
- Invalid approvals: `none`
- Expired approvals: `none`

## CLI Help Smoke

- Enabled: `True`
- Timeout seconds: `5.0`
- Checked scripts: `4`
- Passed scripts: `4`
- Failed scripts: `none`

## Script Surface

| Script | Interface | Declared | Argparse | Main Guard | Input | Network | File Write | Subprocess | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| scripts\check_unity_cli.py | cli | False | True | True | False | False | True | True | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts\unity_test_summary.py | cli | False | True | True | False | False | False | False | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts\unity_version_check.py | cli | False | True | True | False | False | False | True | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts\unity_wait.py | cli | False | True | True | False | False | False | True | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |

# Security Trust Report

- OK: `True`
- Scanned files: `8`
- Scripts: `1`
- Internal script modules: `0`
- Secret findings: `0`
- Network-capable scripts: `0`
- Network policy covered scripts: `0`
- Network policy missing scripts: `0`
- File-write scripts: `0`
- Permission approvals: `0 / 1`
- Permission approval gaps: `1`
- CLI help smoke checked: `1`
- CLI help smoke failures: `0`
- Interactive scripts: `0`
- Package hash scope: `source-contract-without-generated-reports`
- Package hash files: `8`
- Package SHA256: `f1a58c33bfba5357cae940a9b182e5948d7fa866d1d3658a005ce96feff7d5a0`

## Failures

- None

## Warnings

- No dependency or lock file detected
- Permission approvals missing: subprocess

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
- Present: `False`
- Required capabilities: `subprocess`
- Approved capabilities: `none`
- Missing approvals: `subprocess`
- Invalid approvals: `none`
- Expired approvals: `none`

## CLI Help Smoke

- Enabled: `True`
- Timeout seconds: `5.0`
- Checked scripts: `1`
- Passed scripts: `1`
- Failed scripts: `none`

## Script Surface

| Script | Interface | Declared | Argparse | Main Guard | Input | Network | File Write | Subprocess | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| scripts\collect_review_targets.py | cli | False | True | True | False | False | False | True | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |

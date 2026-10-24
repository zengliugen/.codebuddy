# Security Trust Report

- OK: `True`
- Scanned files: `10`
- Scripts: `2`
- Internal script modules: `0`
- Secret findings: `0`
- Network-capable scripts: `0`
- Network policy covered scripts: `0`
- Network policy missing scripts: `0`
- File-write scripts: `0`
- Permission approvals: `0 / 1`
- Permission approval gaps: `1`
- CLI help smoke checked: `2`
- CLI help smoke failures: `0`
- Interactive scripts: `0`
- Package hash scope: `source-contract-without-generated-reports`
- Package hash files: `10`
- Package SHA256: `dec3e8417bb42f4419a00c7b480583dfcfa0c0134b3792864845077fe411f835`

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
- Checked scripts: `2`
- Passed scripts: `2`
- Failed scripts: `none`

## Script Surface

| Script | Interface | Declared | Argparse | Main Guard | Input | Network | File Write | Subprocess | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| scripts\collect_targets.py | cli | False | True | True | False | False | False | True | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts\run_ruff.py | cli | False | True | True | False | False | False | True | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |

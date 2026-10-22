# Security Trust Report

- OK: `True`
- Scanned files: `13`
- Scripts: `4`
- Internal script modules: `0`
- Secret findings: `0`
- Network-capable scripts: `0`
- Network policy covered scripts: `0`
- Network policy missing scripts: `0`
- File-write scripts: `2`
- Permission approvals: `0 / 2`
- Permission approval gaps: `2`
- CLI help smoke checked: `4`
- CLI help smoke failures: `0`
- Interactive scripts: `0`
- Package hash scope: `source-contract-without-generated-reports`
- Package hash files: `13`
- Package SHA256: `4bdff74d00f9e5353480cde68f24317903f29d1248b5b4cdc2da284da573609f`

## Failures

- None

## Warnings

- No dependency or lock file detected
- Permission approvals missing: file_write, subprocess

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
- Required capabilities: `file_write, subprocess`
- Approved capabilities: `none`
- Missing approvals: `file_write, subprocess`
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
| scripts\check_comments.py | cli | False | True | True | False | False | True | True | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts\diff_comment_report.py | cli | False | True | True | False | False | False | False | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts\split_report.py | cli | False | True | True | False | False | True | False | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts\trigger_eval.py | cli | False | True | True | False | False | False | False | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |

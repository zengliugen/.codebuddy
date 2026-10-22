# Security Trust Report

- OK: `True`
- Scanned files: `16`
- Scripts: `6`
- Internal script modules: `0`
- Secret findings: `0`
- Network-capable scripts: `0`
- Network policy covered scripts: `0`
- Network policy missing scripts: `0`
- File-write scripts: `5`
- Permission approvals: `0 / 2`
- Permission approval gaps: `2`
- CLI help smoke checked: `5`
- CLI help smoke failures: `0`
- Interactive scripts: `0`
- Package hash scope: `source-contract-without-generated-reports`
- Package hash files: `16`
- Package SHA256: `f4fe206193a38075acb4d4ac1261c22a89a7f6295cf0781983600afbddfa5b8a`

## Failures

- None

## Warnings

- No dependency or lock file detected
- CLI scripts without argparse/help surface: scripts\skill_config.py
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
- Checked scripts: `5`
- Passed scripts: `5`
- Failed scripts: `none`

## Script Surface

| Script | Interface | Declared | Argparse | Main Guard | Input | Network | File Write | Subprocess | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| scripts\check_coverage.py | cli | False | True | True | False | False | True | True | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts\collect_real_coverage.py | cli | False | True | True | False | False | True | True | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts\generate_skeletons.py | cli | False | True | True | False | False | True | False | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts\parse_unity_coverage.py | cli | False | True | True | False | False | True | False | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts\skill_config.py | cli | False | False | False | False | False | True | False | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts\trigger_eval.py | cli | False | True | True | False | False | False | False | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |

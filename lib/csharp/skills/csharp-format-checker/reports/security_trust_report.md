# Security Trust Report

- OK: `True`
- Scanned files: `12`
- Scripts: `2`
- Internal script modules: `0`
- Secret findings: `0`
- Network-capable scripts: `0`
- Network policy covered scripts: `0`
- Network policy missing scripts: `0`
- File-write scripts: `1`
- Permission approvals: `0 / 2`
- Permission approval gaps: `2`
- CLI help smoke checked: `2`
- CLI help smoke failures: `0`
- Interactive scripts: `0`
- Package hash scope: `source-contract-without-generated-reports`
- Package hash files: `12`
- Package SHA256: `cfd424b4774ff808dde6b46345fc506ae231020a4f68222b70fdfbad00781884`

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
- Checked scripts: `2`
- Passed scripts: `2`
- Failed scripts: `none`

## Script Surface

| Script | Interface | Declared | Argparse | Main Guard | Input | Network | File Write | Subprocess | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| scripts\check_eol.py | cli | False | True | True | False | False | False | True | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts\dotnet_format.py | cli | False | True | True | False | False | True | True | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |

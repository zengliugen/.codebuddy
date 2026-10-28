# Package Verification

- OK: `True`
- Package directory: `lib/devflow/skills/devflow-guard/dist`
- Targets: `4 / 4` adapters present
- Archive present: `True`
- Archive SHA256: `9036494a6f0915c8a8ba1cb4ca7619f4df1e8c0169818d8b827a80b2e10c50e3`
- Nested SKILL.md entries: `0`
- Failures: `0`
- Warnings: `0`

## Checks

| Check | Status | Detail |
| --- | --- | --- |
| `package-manifest` | `pass` | Package manifest exists: lib/devflow/skills/devflow-guard/dist/manifest.json |
| `claude-adapter` | `pass` | Adapter exists for target: claude |
| `generic-adapter` | `pass` | Adapter exists for target: generic |
| `openai-adapter` | `pass` | Adapter exists for target: openai |
| `vscode-adapter` | `pass` | Adapter exists for target: vscode |
| `archive-safe-paths` | `pass` | Archive has no absolute or parent-traversal entries |
| `archive-entry-devflow-guard/SKILL.md` | `pass` | Archive contains devflow-guard/SKILL.md |
| `archive-entry-devflow-guard/manifest.json` | `pass` | Archive contains devflow-guard/manifest.json |
| `archive-entry-devflow-guard/agents/interface.yaml` | `pass` | Archive contains devflow-guard/agents/interface.yaml |
| `archive-single-skill-entrypoint` | `pass` | Archive exposes only the root SKILL.md entrypoint |
| `archive-excludes-generated` | `pass` | Archive excludes local caches, platform noise, .yao state, external submission drafts, local evidence pointers, generated dist/, .previews/, and tests/tmp* contents |
| `archive-portable-evidence-index` | `pass` | Archive includes a self-contained portable evidence pointer and verified report index |
| `registry-name-match` | `pass` | Registry package name matches package manifest |
| `registry-version-match` | `pass` | Registry package version matches package manifest |
| `registry-compat-claude` | `pass` | Registry compatibility is reviewable for target: claude |
| `registry-compat-generic` | `pass` | Registry compatibility is reviewable for target: generic |
| `registry-compat-openai` | `pass` | Registry compatibility is reviewable for target: openai |
| `registry-compat-vscode` | `pass` | Registry compatibility is reviewable for target: vscode |

## Failures

- None

## Warnings

- None

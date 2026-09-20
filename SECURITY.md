# Security policy

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/JDeffner/px-toolkit-sublime/security/advisories/new). Do not put exploit details, sensitive files, or credentials in a public issue or pull request. If the private reporting form is unavailable, open an issue asking only for a private security contact, without describing the vulnerability.

Include the affected package revision, Sublime/LSP/server versions, operating system, steps to reproduce, and the security impact. A small proof of concept is useful. Share only the files needed to reproduce the problem and remove unrelated personal data. Please coordinate public disclosure with the maintainer.

## Maintenance and supported versions

This package is maintained when time allows, with the main Paradox Modding Toolkit taking priority. There is no guaranteed response or fix deadline and no paid support or bug bounty. Reports will be reviewed as availability permits.

Security work targets the latest package release and current development branch. Older releases and candidates do not have a separate backport commitment. During the initial release-candidate phase, fixes may be available on the development branch before a new release. Include the revision you tested; you do not need to delay reporting a serious issue while upgrading.

Confirmed fixes should include regression coverage and be described in a release or security advisory when disclosure is appropriate. Reporter credit can be omitted on request.

## Scope

Report security problems in this repository's installer, archive extraction, process launch, file watching, source writers, report rendering, and LSP integration here. Examples include writing outside an intended editable mod, loading an unverified executable, or turning untrusted report content into unintended commands.

The language server is maintained in the [main toolkit](https://github.com/JDeffner/paradox-modding-toolkit/security/policy). Tiger, Sublime Text, and the Sublime LSP client are separate upstream projects. Use their reporting process for vulnerabilities in those components. If it is unclear which component is responsible, report privately here and explain what you observed.

Ordinary script diagnostics, mod compatibility problems, and game crashes without a security impact belong in the bug tracker. The package cannot protect an already compromised operating system or editor process.

## Local files and network access

The adapter starts a local language-server process and, when requested, Tiger. It reads configured game, mod, dependency, and log files. Configuration creation, scaffolding, caches, and downloads write local files; authoring edits generally remain in buffers until saved.

Managed server/runtime installation checks the upstream GitHub latest stable release on startup and verifies archives against the SHA-256 digests in GitHub's asset metadata. It accepts server downloads only from the toolkit's GitHub release URLs. The bootstrap server and Tiger use pinned URLs and hashes. Failed updates preserve cached installations. Set `px.auto_update_server` to `false` to disable server update checks. Documentation and source links may open external sites when selected. The adapter does not provide telemetry or upload mod/game contents. A custom `server_command`, `node_path`, or `tiger_path` selects software that runs with your user permissions; use executables you trust.

Checksums, archive containment checks, and source-write guards must not be disabled to resolve installation or editing problems.

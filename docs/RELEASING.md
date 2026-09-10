# Release procedure

1. Run pure tests, `python scripts/ci_protocol.py`, real editor workflows and Tiger fixtures. Review all platform CI jobs. Record limitations in VALIDATION.md rather than implying unperformed checks passed.
2. Regenerate menus/schema. Build twice and compare SHA-256 hashes. Inspect the zip: no `.dev`, tests, user paths, caches, credentials, game assets or runtime binaries.
3. Clean-install and upgrade the packed artifact in isolated profiles. Confirm restart/process cleanup and offline reuse of the cached server. Keep the minimum Sublime/LSP and pinned server mapping current.
4. Review README, changelog, GPL notices and matching upstream source. The repository must be public before Package Control can fetch it; this checkout was private during implementation. Review repository history before changing visibility.
5. Merge the reviewed branch, tag a semantic release such as `v0.1.0`, and attach the deterministic `LSP-px.sublime-package` and SHA-256 checksum to that release. Do not tag a stable release while acceptance checks remain open.
6. Submit a reviewed entry to [Package Control channel](https://github.com/wbond/package_control_channel) under the appropriate repository file. Use package name `LSP-px`, repository URL, description, labels, `sublime_text: ">=4200"`, supported platforms and a tagged-release selector. See [official submission requirements](https://packagecontrol.io/docs/submitting_a_package).

Package Control installs the package from the repository root and tracks tags; `sublime-package.json` contributes settings schemas, not ordinary-package dependency installation. Users must install LSP separately. Maintainer acceptance of a channel submission is external to this repository.

Future server upgrades must update URL/hash pins, protocol tests, version gates, notices and the compatibility table together. Keep a manual command override for development/offline use.

| Package | Server | Upstream toolkit | Sublime | LSP |
| --- | --- | --- | --- | --- |
| 0.1.0 candidate | 0.3.4 | v0.4.3 | >=4200 | >=2.13 |

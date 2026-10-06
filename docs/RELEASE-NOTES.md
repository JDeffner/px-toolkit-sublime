# LSP-px 0.1.0

CK3 modding in Sublime Text 4, powered by Paradox Language Server. This release uses **px-lsp 0.3.8 from the toolkit v0.5.5 prerelease**. It requires Sublime Text build 4200 or newer and the separate LSP package, version 2.13 or newer.

## Changes

- Use the tested LSP 0.3.8 baseline, including its updated CK3 knowledge, reference handling, semantic tokens, and localization support.
- Refresh the script grammar from toolkit v0.5.5 and add the texture-hover background setting.
- Keep automatic updates, verified downloads, cached offline use, and explicit version selection. Automatic updates use the package baseline or a newer stable server. Other future prereleases are not selected automatically.
- Keep rollback to supported older servers, starting at 0.3.4. A version pin takes priority over automatic updates.
- Fix the Paradox dark color scheme and opening an existing source in the adjacent pane.
- Add PX/ST branding and illustrated wiki guides.

This package provides native Sublime commands and reports. It does not include the main toolkit's graphical editors or migration tools.

## Validation

All 84 tests passed inside Sublime Text 4200 on Windows. All 26 live CK3/Tiger workflow checks passed. DDS transparency, native color conversion and undo, localization previews, constant hints, and scope hints were checked in the editor. Protocol checks passed on LSP 0.3.8 and the minimum supported 0.3.4.

## Limited maintenance

I do not plan much further development of this Sublime Text package. My focus is the [main Paradox Modding Toolkit](https://github.com/JDeffner/paradox-modding-toolkit). I may fix bugs when time allows, but there is no planned feature or release schedule. Contributions are welcome. If you want to maintain this package, please [open an issue](https://github.com/JDeffner/px-toolkit-sublime/issues) to arrange a handover.

## Install

Install **LSP** through Package Control, then copy `LSP-px.sublime-package` into Sublime's **Installed Packages** directory. Restart Sublime and run **Paradox: Setup**. The package is not yet listed in Package Control. See the [README](https://github.com/JDeffner/px-toolkit-sublime/blob/v0.1.0/README.md) for full setup and platform requirements, and the [validation record](https://github.com/JDeffner/px-toolkit-sublime/blob/v0.1.0/docs/VALIDATION.md) for test results and scope.

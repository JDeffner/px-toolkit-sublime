# Third-party notices

## Paradox Modding Toolkit

Syntax grammars, the descriptor field/tag data and `vendor/descriptorMod.ts` originate from [JDeffner/paradox-modding-toolkit](https://github.com/JDeffner/paradox-modding-toolkit), tag v0.4.3, commit `f517501e0edb83fb0473a5db1c2a9c42afb06886`, GPL-3.0. The grammars are converted from JSON TextMate syntax to XML plist without changing their scope/rule content. Descriptor metadata is generated from the included TypeScript source. The original license is included as `LICENSE`; this package is distributed under that license.

Regenerate against an exact matching sibling checkout using `python scripts/vendor_upstream.py ../paradox-modding-toolkit`, then `npx --yes --package=esbuild@0.25.12 esbuild vendor/descriptorMod.ts --bundle --platform=node --outfile=.dev/descriptor.cjs` and `node scripts/export_descriptor.cjs`. On Windows use `npx.cmd` where execution policy blocks the PowerShell shim.

The managed px-lsp server is downloaded separately from the same upstream release. Its source, data provenance and third-party licenses remain upstream; the release directory layout is preserved. Source: [v0.4.3](https://github.com/JDeffner/paradox-modding-toolkit/tree/v0.4.3).

## Sublime LSP and Tiger

[Sublime LSP](https://github.com/sublimelsp/LSP) is a separately installed dependency; its code is not bundled here. [Tiger](https://github.com/amtep/tiger/tree/v1.19.0) is an optional separately downloaded validator. The downloaded release's license files are retained. See each upstream project for its license and corresponding source.

No CK3 installation assets, textures, saves or user mod files are included in the package artifact.

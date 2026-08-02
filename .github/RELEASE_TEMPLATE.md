# MORICE vVERSION

## Highlights

- 

## Improvements

- 

## Fixes

- 

## Breaking Changes

None, unless listed here.

## Performance

-

## UI

-

## Install

### Installer

Download the setup executable and every adjacent numbered `.bin` slice into one folder, then run setup.

### Portable

Download every portable ZIP part, the parts manifest, and the PowerShell reassembler into one folder. Run `powershell -NoProfile -ExecutionPolicy Bypass -File .\MORICE-Portable-v0.7.0-Windows-x64-reassemble.ps1`, verify the resulting archive, extract it, and launch `MORICE.exe`.

Verify all files with `checksums.json`.

### Python package

Install the downloaded wheel with `python -m pip install <wheel-path>`, then launch `morice`.
Do not show a public package-index command until that channel is verifiably published.

## Upgrade Notes

- Back up settings and project work before replacing an existing portable installation.
- Do not copy old `_internal` runtime files over a new release.

## Known Limitations

- 

## Verification

- [ ] Python test suite passed
- [ ] VNext tests and typecheck passed
- [ ] Installer launch tested
- [ ] Portable package reassembled and launched
- [ ] Icons and shortcuts verified
- [ ] Checksums verified
- [ ] Package-content report passed with no forbidden files or possible secrets
- [ ] Wheel and source distribution passed `twine check`
- [ ] Version matches application, installer, executable, tag, changelog, and release notes
- [ ] Release is created from the verified commit, not an unmerged or dirty checkout

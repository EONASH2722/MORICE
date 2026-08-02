# Security Policy

## Supported Version

Security fixes are applied to the latest published MORICE release and the current `main` branch.

## Reporting A Vulnerability

Do not open a public issue for an exploitable vulnerability. Use GitHub's private vulnerability
reporting for `EONASH2722/MORICE`, or contact the maintainer privately through the repository owner
profile. Include the affected version, reproduction steps, impact, and any proposed mitigation.

Please allow reasonable time for triage before public disclosure.

## Security Model

- Local models do not receive direct filesystem or renderer authority.
- Folder-limited project paths are resolved against the selected root.
- Sensitive desktop and Git mutations require explicit approval.
- Plugin packages and model files are validated before activation.
- Update packages are checksum-verified before staging.
- Secrets and private runtime data are excluded from release archives.

MORICE is local-first software, but users remain responsible for reviewing generated code and
permissions before running or applying changes.

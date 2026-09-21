# Contributing

This is a free, open-source tool (MIT) for the AAC community. Bug reports,
feature ideas, and pull requests are all welcome.

## Getting set up

```bash
pip install ".[dev]"
python -m pytest                    # unit tests, no fixtures needed
ruff check tdsnap tests packaging scripts
coverage run -m pytest && coverage report
python scripts/fetch_fixture.py     # downloads a real page set (~16 MB)
python -m pytest                    # now includes the integration tests
python -m tdsnap.web --no-browser   # run the web app locally
```

Optional built-in AI engine: `pip install ".[ai]"` (packaged releases include
it). Native desktop window: `pip install ".[desktop]"`.

## Ground rules

- **Never commit a real TD Snap page set.** They are proprietary Tobii
  Dynavox content; `.gitignore` blocks `*.sps`/`*.spb` and the tests download
  their fixture instead. Only the schema-only `schema_snapshot.sql` is
  committed.
- **Every write path must be validated.** If you extend the editor, extend
  `tdsnap/validate.py` (and the tests) so a bad edit fails before the file is
  saved rather than after it crashes someone's communication device. The
  round-trip snapshot diff (`EXPECTED_CHANGED_TABLES`) must name every table
  your edit touches.
- **Verify against a real file.** Don't guess columns — check the downloaded
  fixture (`python -m tdsnap inspect`) the way the existing code was built.
- Reporting a bug where TD Snap rejects an edited file? Include the output of
  `python -m tdsnap verify <file> --show-sync`.

## Releasing

`tdsnap/__init__.py` is the single version source; package metadata reads it
dynamically. Bump it, commit the complete release, then create and push the
matching tag (`git tag vX.Y.Z && git push origin vX.Y.Z`). Manual workflow runs
also require an existing tag and check out that exact ref.

Releases are not code-signed. The workflow builds the executable and
installer, installs the package, checks its health/version endpoint,
uninstalls it, writes a SHA-256 checksum, attests build provenance, and only
then attaches everything to a draft GitHub Release. Review the draft, then
publish it. Exact direct build inputs live in
`packaging/release-constraints.txt` and should be updated deliberately.

An unsigned build must keep `uiAccess="false"`: Windows will not start a
`uiAccess="true"` executable without a trusted Authenticode signature. Live
Grid 3 editing relies on the administrator restart instead, on every launch.

`packaging/build.ps1` picks the manifest from the signing mode, so that stays
true without anyone remembering it: an ordinary build embeds
`aac-editor.manifest`, and `-Sign` embeds `aac-editor-uiaccess.manifest`.
`packaging/verify_manifest.ps1` refuses any binary that requests `uiAccess`
without a valid signature, whatever it was told to expect, which is why signing
runs before verification. If a certificate becomes available, `-Sign` is the
whole change, and live Grid 3 editing stops needing administrator approval.

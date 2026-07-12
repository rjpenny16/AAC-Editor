# Contributing

This is a free, open-source tool (MIT) for the AAC community. Bug reports,
feature ideas, and pull requests are all welcome.

## Getting set up

```bash
pip install -r requirements.txt pytest
python -m pytest                    # unit tests, no fixtures needed
python scripts/fetch_fixture.py     # downloads a real page set (~16 MB)
python -m pytest                    # now includes the integration tests
python -m tdsnap.web --no-browser   # run the web app locally
```

Optional built-in AI engine: `pip install llama-cpp-python` (the packaged
releases include it).

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

Maintainers: bump the version in `pyproject.toml` and `tdsnap/__init__.py`,
then `git tag vX.Y.Z && git push --tags`. The Release workflow builds the
packaged Windows app and attaches it to a draft GitHub Release.

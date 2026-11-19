# Repository rulesets

GitHub does not read these files: they are the repository's protection rules written down, to import once and to
review like any other change. To apply one: **Settings → Rules → Rulesets → New ruleset → Import a ruleset**, choose
the file, then **Create**.

- `main.json`: the default branch takes changes only through a pull request whose tests pass on Linux, macOS and
  Windows. No one, admins included, can push to it directly, force-push it or delete it.
- `release-tags-create.json`: a `v*` tag publishes a release (see `.github/workflows/build.yml`), so only repository
  admins can create one.
- `release-tags-locked.json`: once pushed, no one, admins included, can move or delete a `v*` tag, so a release
  always points at the commit it was built from. To withdraw a broken release, publish a newer one; switch this
  ruleset off only if a tag truly must go.

If a test job is renamed in `build.yml`, update the `required_status_checks` in `main.json` to match, or pull
requests will wait for a check that never comes.

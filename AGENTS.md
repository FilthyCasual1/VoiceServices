# ServiceReady project instructions

For every completed code or interface edit, increment the release version and
record the change in CHANGELOG.md. Use tools/bump_version.py: patch (+0.0.1) for every small change, minor (+0.1.0) for major features,
and major (+1.0.0) for major releases. The footer and
package metadata must use voiceservices/version.py as their single version source.

## Required regression checks

Every update must run the full regression suite, including UI-only changes.
Focused tests are supplementary and never replace the full suite. Add a regression
test for each bug fix that reproduces the reported failure where practical.
Run `python -m unittest discover -s tests` and
`node --test tests/test_portal_wizard.js` after building addon packages.
Do not declare an update ready or publish a release until the full suite passes
for that exact commit. If local restrictions prevent a test from running, report
that limitation and require the complete GitHub checks to pass before release.

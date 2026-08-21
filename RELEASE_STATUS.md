# Candidate release status

Updated: 2026-08-18. This is a release checklist, not evidence for a published
build or an immutable revision.

Status: not ready. The candidate package is `mailarium` `0.5.0a1`, an alpha
for local Outlook `.olm` archive work on macOS 14 or later on Apple Silicon.
Optional EWS support remains experimental. Offline verified; live EWS writes unverified.

## Recorded local evidence

The most recent full local evidence was recorded on 2026-08-14. It included a
valid lockfile, Python syntax checks, static demo checks, and a whitespace
check. Dependency-enabled tests, type checks, security tools, artifact builds,
and the tracked-only privacy scan were not current candidate evidence in that
environment. Historical audit results do not replace checks on a release
revision.

## Required before publication

1. Freeze and review an exact candidate revision.
2. Resolve or explicitly disposition dependency advisories in an authorized
   lockfile update, then run the complete configured suite.
3. Run the privacy, artifact, installed-wheel, and configured CI checks against
   that exact revision.
4. Confirm package and project-name availability for each intended publication
   channel.
5. If EWS is described in release notes, validate an authorized disposable
   server profile or retain the offline-only limitation.

Do not publish from an unreviewed working tree.

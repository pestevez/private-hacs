# Private HACS

A small Home Assistant custom integration that installs and updates other custom
integrations from **private GitHub repositories**.

It is conceptually similar to [HACS](https://hacs.xyz), but stripped to a single
job: pull a custom integration out of a GitHub repo you own — public or private —
and write it into your `custom_components/` folder. There is no central catalog;
you add repos by their `owner/repo` name.

Useful when you maintain integrations that you do not want to publish (work
projects, personal experiments, betas, internal tools) but still want to deploy
to your Home Assistant instance the same way you would any other community
integration.

## Features

- Authenticated GitHub access via a Personal Access Token, so private repos work.
- Track a repo by **latest release**, a specific **tag**, a **branch** (e.g.
  `main`), or a pinned **commit SHA**.
- **No background polling** — Private HACS never reaches out to GitHub on its
  own. Updates happen when you click **Install / update**, on your schedule.
  Designed for repos you control yourself, where you already know when there's
  something new to pull.
- Path-traversal-safe tarball extraction.

Themes, frontend cards, AppDaemon apps, and other HACS categories are out of
scope. This is integrations only.

## Installation

### Recommended: install via HACS

1. In Home Assistant, open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/pestevez/private-hacs` as an **Integration**
   category.
3. Click **Install** on the new "Private HACS" entry, then **restart Home
   Assistant**.

### Manual

If you don't have HACS, copy `custom_components/private_hacs/` into your
Home Assistant `config/custom_components/` directory and restart.

## First-time setup

1. **Settings → Devices & services → Add integration → "Private HACS"**.
2. Paste a GitHub Personal Access Token. Either works:
   - **Classic** PAT with the `repo` scope, or
   - **Fine-grained** PAT scoped to the specific repos you want to install,
     with **Repository permissions → Contents: Read-only**.

   The token is stored in Home Assistant's encrypted config-entry store.

## Adding a private repository (UI)

1. **Settings → Devices & services → Private HACS → Configure**.
2. Pick **"Add a private repository"**.
3. Paste the repo URL (`https://github.com/owner/repo`) or `owner/repo`.
4. Choose how to track it. The default is **branch** with `main` pre-filled,
   which fits a personal "I push when it's ready, then click update" workflow.
   You can also pick latest **release**, a specific **tag**, or a pinned
   **commit** SHA.
5. Leave **"Install immediately after adding"** checked. The form will both
   register the repo and copy its `custom_components/<name>/` folder into
   place.
6. **Restart Home Assistant** to load the new integration. HA does not
   hot-reload custom integration code — this constraint applies to HACS too.

## Managing tracked repositories (UI)

**Settings → Devices & services → Private HACS → Configure → "Manage…"**
lets you pick a tracked repo and:

- **Install / update** — re-download the configured ref and overwrite the
  installed files. This is also how you pick up a new release: push to the
  upstream repo, then click here. Restart Home Assistant afterwards to load
  the new code.
- **Remove** — delete the integration from `custom_components/` and stop
  tracking it.

There is no background polling. Private HACS only contacts GitHub when you
explicitly add, install, or update a repo.

## Service API (optional)

Everything the UI does is also exposed as services if you want to drive it
from automations:

```yaml
service: private_hacs.add_repository
data:
  full_name: https://github.com/pestevez/my-private-integration
  ref_type: release      # release | tag | branch | commit
  # ref: v1.2.0          # required for tag/branch/commit
  # integration_name: my_integration   # only if the repo has multiple integrations
```

Other services: `private_hacs.install`, `private_hacs.update`,
`private_hacs.remove_repository`.

## Repository layout requirements

The repo must contain a `custom_components/<integration_name>/` directory at
its root, the same convention HACS uses. Private HACS extracts only that
folder, ignoring everything else in the repo.

If a repo contains more than one integration, set `integration_name` when
calling `add_repository` to pick which one to install.

## Why not just use HACS?

HACS is great. Use it if your integrations are public or you are happy
configuring HACS's "custom repositories" feature — that flow does support
private repos with a token. Private HACS exists because:

- I wanted a tool that is private-first instead of private-as-a-side-feature.
- I wanted no UI dependency on the HACS panel, just plain HA services.
- It is small enough to read end-to-end (~600 lines) and audit before running.

## License

MIT — see [LICENSE](LICENSE).

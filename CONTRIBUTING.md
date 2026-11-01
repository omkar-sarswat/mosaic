# Contributing to Mosaic

Mosaic is an investigation and intelligence workspace by Weirwood. Start with the [README](README.md), [development guide](docs/development.md), and [architecture](docs/architecture.md).

## Report a problem

Use a minimal synthetic example. Describe the workspace, account role, case context, steps, expected behaviour, actual behaviour, and browser/runtime versions. Include a screenshot when it clarifies a visual issue. Do not include credentials, real case evidence, or personal records in an issue.

## Make a change

1. Create a focused branch and keep the change tied to a concrete problem.
2. Preserve the existing `drishti` command and configuration interfaces unless the change explicitly includes a migration.
3. Keep policy enforcement on the server. Hiding a UI control is not an access-control check.
4. Distinguish recorded evidence, inferred relationships, proposed matches, and approved decisions in the interface.
5. Update the relevant documentation and include reproducible verification steps.

For frontend changes, run `npm run build` and `npm run lint` in `web/`. For backend changes, check Python syntax and imports, then exercise the changed workflow against a disposable synthetic database. Historical research references tests not present in this snapshot; do not claim to have run those suites.

For changes to identity, access policy, masking, audit, or approvals, provide concrete permitted and refused examples, including the two-officer boundary where relevant. Behavioural tests should accompany meaningful changes to those boundaries.

## Pull requests

Explain the problem and resulting behaviour, list the checks actually run, and identify any remaining limitation. Include before-and-after screenshots for visible changes. Keep unrelated formatting and dependency upgrades out of the change.

## Data and documentation

Use synthetic investigative data in examples and captures. Keep original image dimensions and source notices. Follow the [documentation standards](docs/documentation-standards.md), and retain third-party attribution when adding assets.

The project is distributed under [Apache 2.0](LICENSE). Existing data and asset licenses continue to apply.

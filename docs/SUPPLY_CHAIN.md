# Supply chain — OS_V1

## What the system depends on

| Dependency | Origin | Licence | Note |
|---|---|---|---|
| Python | python.org | PSF | the runtime |
| llama.cpp | ggml-org/llama.cpp | MIT | serves the local model over an OpenAI-compatible API |
| REA (morluto/rea) | github.com/morluto/rea | MIT | pinned; the adapter refuses an unpinned copy |
| Ghidra | NationalSecurityAgency/ghidra | Apache-2.0 | the default engine for native binaries |
| The local model | the user | recorded in the provenance register | the user supplies the weights and their licence |

The runtime record lives in `data-osv1/provenance.json` and is readable with:

```bash
oss-v1 provenance
```

Anything whose licence is not permissive goes into the review queue, and the
queue is meant to be worked before a release. The review flag is derived from
the licence every time the register is loaded, so a record whose licence
changed cannot slip through by being saved earlier.

## Rules that hold in the code

- **Pinned versions.** The expected REA version lives in
  `osv1/tools/rea.py`. An installed copy that reports another version is
  refused, and the reason is returned.
- **Official sources only.** The dependency list above names the upstream
  project for each component. Look-alike repositories are a known risk, and
  the supply chain is not widened by convenience.
- **Licence first.** A custom, community, or non-commercial licence needs a
  legal review before use. The specification says this; the register is where
  it is checked.
- **No runtime installation.** The system never installs a package at run
  time. Dependencies are installed once, from the locked environment.
- **No unsigned updates.** The self-evolution gate promotes skills, memory,
  and calibration — never a new set of model weights, and never a change to
  the safety layer. A weight update needs the user's approval.
- **Archive hygiene.** The published archive excludes caches, runtime
  databases, logs, local secrets, and the working data directory. Its
  integrity is checked when it is built, and a hash proves the bytes are
  intact — not that the source is free of vulnerabilities.

## What still has to happen before a production release

- A dependency and licence review, and an SBOM generated from the locked
  environment.
- A signed build, and a signed artifact check in the release job.
- An independent penetration test and a red-team suite over the safety
  layer, before any new permission is released.
- A test on every update, with a reviewed version pin and a tested rollback.

These are listed in `todo.md`. They are not implied to be done by the
existence of this file.

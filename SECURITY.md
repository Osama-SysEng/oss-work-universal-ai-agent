# Security — OSS Work / OS_V1

Security here means risk reduction, not a promise of safety. The system has
real access to the user's files, so the safety layer is mandatory and sits
under every other component.

## The rules the code enforces

| Rule | Where it is enforced | How it is tested |
|---|---|---|
| No action without a permission | `osv1/layers/action.py` | `tests/test_safety_layer.py` |
| No irreversible action without human approval | `osv1/safety/approvals.py` | `tests/test_safety_layer.py` |
| The kill switch stops everything, immediately | `osv1/safety/killswitch.py` | `tests/test_safety_layer.py` |
| Content from files, web pages, and tools is data, never an instruction | `osv1/safety/injection.py` | `tests/test_safety_layer.py` |
| The audit log is tamper-evident | `osv1/safety/audit.py` | `tests/test_safety_layer.py` |
| No secret in plain text | `osv1/safety/secrets.py` | `tests/test_safety_layer.py` |
| Untrusted code runs with no network and no inherited secrets | `osv1/tools/sandbox.py` | `tests/test_osv1_tools.py` |
| The safety layer cannot be changed by self-improvement | `osv1/learning/evolution.py` | `tests/test_osv1_learning.py` |

## Known limits — stated, not hidden

- The sandbox blocks the network for Python children by refusing socket
  creation. A child that compiles native code, or runs another runtime, can
  get past that. For a real jail, run the same tool inside a container or a
  virtual machine.
- The prompt-injection check is a heuristic over common patterns. It flags
  what it recognises; it is not a proof, and the action layer is what
  actually stops an instruction from becoming an action.
- The local API has no authentication. It binds to `127.0.0.1`, so only the
  machine itself can reach it. Do not expose it to a network.
- The secret store uses the Windows DPAPI. On other platforms it refuses to
  store a secret rather than falling back to plain text.
- The local model is a 3B quantized model. It is good at light tasks and
  decisions; heavy work is split or queued. Its outputs are never presented
  as the output of a frontier model.

## Reporting

Open an issue on the repository. Do not include secrets, tokens, or personal
data in a report. If a credential is exposed, rotate it first and say so
without quoting it.

## Supply chain

- Base weights must be under Apache 2.0 or MIT. Any other licence needs a
  legal review before it is used.
- The REA engine is pinned to an exact version and refuses to run an
  unpinned copy. The expected version lives in `osv1/tools/rea.py`.
- The dependency review and the penetration test are still open work; they
  are listed in `todo.md`, not implied to be done.

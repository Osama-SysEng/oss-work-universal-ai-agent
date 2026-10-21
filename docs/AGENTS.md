# The 300 agents

Thirty domains times ten specializations. Every combination is a working
agent with its own capabilities, risk level, verification rules, plan
template, and prompt.

## The domains (30)

| Domain | Keywords it answers to | Typical tools |
|---|---|---|
| software-engineering | code, refactor, function, class, bug | files, code |
| backend-api | api, endpoint, route, service, queue | files, code |
| frontend-web | react, html, css, component, layout | files, code, web |
| mobile-apps | android, ios, flutter, apk, screen | files, code |
| desktop-apps | electron, tauri, installer, window | files, code |
| data-engineering | csv, pipeline, duplicate, rows, export | files, sheets |
| databases | sql, schema, migration, index, query | files, code |
| ai-ml | model, prompt, rag, lora, evaluation | files, code |
| nlp | text, arabic, dialect, tokenize, summary | files, code |
| computer-vision | image, video, frame, ocr, fps | files, code |
| robotics-iot | robot, sensor, servo, mqtt, control | files, code |
| embedded-systems | arduino, mcu, flash, timer, uart | files, code |
| devops-sre | deploy, pipeline, docker, rollback, slo | files, code |
| cloud-infrastructure | cloud, terraform, bucket, tls, cost | files, code, web |
| networks | ip, dns, port, firewall, latency | files, code |
| security-engineering | vulnerability, xss, jwt, rbac, secret | files, code, rea |
| quality-assurance | test, coverage, regression, mock | files, code |
| test-automation | playwright, headless, selector, script | files, code, web |
| supply-chain | dependency, license, sbom, pinning | files, code |
| technical-writing | documentation, readme, guide, manual | files, office |
| product-analysis | requirement, scope, roadmap, priority | files, sheets |
| business-process | workflow, procedure, approval, sop | files, sheets, office |
| finance-accounting | invoice, tax, payroll, ledger, margin | files, sheets |
| marketing-growth | campaign, positioning, funnel, copy | files, office, web |
| seo-content | seo, keyword, sitemap, canonical | files, office, web |
| legal-compliance | license, terms, gdpr, privacy, consent | files, office |
| hr-talent | employee, hiring, candidate, attendance | files, sheets, office |
| education-training | course, lesson, exercise, rubric | files, office |
| scientific-computing | simulation, matrix, monte carlo, tolerance | files, code |
| media-visualization | chart, dashboard, svg, render, slide | files, sheets, office |

## The specializations (10)

| Specialization | What it does | Deliverable |
|---|---|---|
| analysis | read and explain, with the evidence named | an explanation that names its sources |
| implementation | make the change, keep it reversible | the changed files and the result |
| review | find what is wrong, with severity | ranked findings with evidence |
| testing | design the checks, run them, say what is uncovered | the tests, the result, the gap |
| optimization | measure first, then change, then report the gain | the measurement before and after |
| debugging | reproduce, find the cause, prove the fix | the reproduction, the cause, the fix |
| migration | move without losing data and without a dead end | the migrated data and the rollback |
| integration | connect the two sides and state the contract | the integration and its failure behaviour |
| documentation | write it so the next person can act | the document and its audience |
| research | gather from named sources, separate fact from guess | the findings with their sources |

## How routing works

1. System One classifies the request against the 30 domain vocabularies and
   the 10 specialization vocabularies. The probabilities and the signals are
   returned, not just the label.
2. If System One abstains, the transparent keyword scorer in the registry
   takes over, and the result says so.
3. The chosen agent id is reported in every result, so a decision can always
   be traced to the agent that made it.

## Using an agent directly

```bash
oss-v1 agents --domain security-engineering
oss-v1 agent A153
oss-v1 plan "review core/policy.py for security issues" --agent A153
```

```bash
curl -X POST http://127.0.0.1:8080/build \
  -H 'Content-Type: application/json' \
  -d '{"task": "review core/policy.py for security issues", "agent_id": "A153"}'
```

## What an agent is not

An agent is not a persona and not a costume. It is a capability profile: what
it may use, what it must produce, and what has to be true before its answer
is delivered. The verifier checks the last part, and it does not ask the
agent whether it did a good job.

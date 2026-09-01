# OSS Work Console

The web console is a restrained operator interface built from the supplied dashboard direction and orchestration graph. It keeps the useful information architecture—overview, agent fleet, activity, and coordination map—while replacing inflated telemetry and live-action language with explicit labels such as **Ready**, **Simulation**, and **Approval**.

The visual system uses a dark slate canvas, quiet borders, one mint accent, one blue secondary accent, responsive layouts, semantic headings, keyboard-friendly controls, and a reduced-motion media query. The interface is intentionally information-dense without relying on excessive gradients, animated noise, or generic “AI magic” copy.

The page is currently a static console presentation. Connecting it to the Python runtime requires a reviewed API boundary with authentication, authorization, CSRF protection where applicable, request validation, rate limits, and redacted audit events. No live credentials are expected in the browser bundle.

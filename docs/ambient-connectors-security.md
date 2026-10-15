# Phase 7: connectors, ambient events and defensive security

Phase 7 extends the existing capability kernel, AgentCoordinator, nine roles, TaskGraph, WorkerManager, SharedTaskState, permission controller, resource leases, EventBus and VerifiedActionRuntime. It adds no agent runtime, task graph, permission manager or verification engine. RuntimeServices initializes the new services lazily when the Ambient panel is opened. No account authentication, network listener, collector or monitoring thread starts at normal boot.

## Architecture and extension contract

`morice/connectors` supplies a provider protocol, descriptor, operation bindings, registry, bounded HTTPS transport and GitHub issues provider. An operation declares a handler, read/write/auth scope, mutation flag and input schema. The registry registers `connector.<id>.<operation>` in the existing kernel, requires every advertised operation to exist, and rejects namespace collisions. Future providers implement their official authentication, operation verification and event normalization under this contract; registration does not grant authority. GitHub is the implemented external service. Email, calendar, cloud drives and media services are future adapters, rather than connected accounts or advertised working features.

`morice/ambient` extends the existing desktop AutomationEngine with persistent watches. The same kernel EventBus carries validated event envelopes. A bounded intake queue and one timing thread evaluate scalar conditions and due times. The timing thread performs no provider I/O or model inference. It submits read/analysis work to the existing AgentCoordinator. The existing NotificationManager handles local notices; its durable `publish_once` receipt prevents duplicate notices after a partially committed event tick. Existing legacy automation actions and scheduler remain compatible; Phase 7 watches use the nonblocking timing service.

`morice/security` collects selected local metadata, records findings and incidents, and registers containment capabilities with the same kernel. Its containment bindings observe through the existing VerifiedActionRuntime and use its action journal and VerificationResult contracts. Security is off by default. Enabling monitoring grants a read scope; containment additionally requires a granted containment scope and an exact one-use approval for the selected arguments.

```mermaid
flowchart TD
    sources[Connectors, authenticated devices, selected local sources] --> bus[Existing kernel EventBus]
    bus --> watches[Persistent deterministic watches and schedules]
    watches --> policy[Existing permissions, risk and ambient budgets]
    policy --> graph[Existing TaskGraph and AgentCoordinator]
    graph --> connector[Registered connector capabilities]
    graph --> action[Existing verified action runtime]
    graph --> security[Scoped security capabilities]
    connector --> verify[Observe and verify using existing contracts]
    action --> verify
    security --> verify
    verify --> user[Receipts and policy-bound user notifications]
    direct[Simple user commands] --> kernel[Existing direct kernel / PC path]
    kernel --> verify
```

## Connect and disconnect

Open **Ambient → Connectors**, enter `owner/repository` and the client id of a registered GitHub OAuth app with device flow enabled, then choose **Add GitHub** and **Authorize read access**. The existing network permission must be granted before the initial authorization request. Complete the displayed challenge at GitHub. Authorization polls respect the provider interval and `slow_down`; the timing service schedules each bounded request outside worker waits. The provider independently retrieves `/user`, and assignment events are filtered to the observed account. No browser cookie scraping or account password entry is supported.

The OAuth `repo` scope is broader than an issues-only GitHub App installation permission. This initial OAuth adapter restricts local operations to the configured repository and separately gates reads and writes. Configure a fine-grained GitHub App provider when finer server-side grants are required; that provider is not implemented here. An actual registered client and real account consent are required for live operation. Validation used an explicitly authorized loopback HTTP provider; no real account was authenticated or modified.

Access and refresh tokens and webhook secrets are stored through the existing Windows DPAPI SecureVault. Expiry timestamps and public account references contain no bearer secrets. Refresh performs one bounded token rotation, stores the new pair in secure storage, and stops after failure until explicit reauthorization. Device codes stay in transient provider state and never enter task inputs, prompts, logs, event envelopes or SQLite.

**Disconnect** cancels connector work, disables dependent watches and polling, removes local credentials and grants, and clears transient authorization and read caches. This public OAuth client has no application secret for server-side app-token revocation. Revoke the OAuth app in GitHub account settings to revoke server-side authorization; local disconnect does not claim that additional effect.

## Provider verification and transport

Reads retrieve actual API objects and return retrieval time, object identity, untrusted-content provenance and ETag. A 304 must correspond to a cached object and is marked as a fresh server revalidation, not a new body download. The cache holds at most 32 issues. Creating an issue needs a separate write grant and exact approval; the provider then retrieves the created issue independently and compares identity, title and body. An HTTP success without that observed object fails. No external mutation is retried automatically or silently overwritten. Update/delete/merge/deploy capabilities are not advertised.

Requests do not follow redirects, cannot move bearer credentials to another origin, use official GitHub HTTPS origins and cap responses at 1 MiB and writes at 128 KiB. Explicit test fixtures may use loopback HTTP. A socket deadline watchdog bounds header/body trickling, and cancellation is checked between response chunks. DNS resolution still uses the OS resolver; its latency can exceed a Python socket deadline. The kernel retains physical execution leases until its existing cleanup boundary completes. Background admission is one workflow by default, rather than a pool of sleeping network workers.

Retry-After and rate-limit exhaustion set a future retry time. Polling uses at least 15 seconds, a 30-call/minute background budget and bounded exponential backoff. Reconciliation fetches the newest 30 matching issue revisions with a persisted `since` cursor and reports a full-page truncation; it does not blindly traverse all historical events.

## Signed webhook receiver

Explicitly configure the provider's webhook secret with `configure_webhook(secret, user_confirmed=True)` and start `connectors.start_webhooks(user_confirmed=True)`. This opens only a loopback receiver at an ephemeral port. Configure an authorized HTTPS relay separately to deliver to `/webhooks/<connector_id>`; Phase 7 creates no public listener, tunnel, subscription or deployment automatically.

The receiver has one transport thread, an eight-connection backlog, a two-second request watchdog, a 128 KiB body limit and rejects chunked bodies. The adapter validates HMAC-SHA256 with constant-time comparison before parsing content, validates repository/account/event identity, and assigns signed provenance internally. It retains at most 1,024 signed-body hashes per webhook secret. Changed unsigned delivery headers cannot defeat dedupe. The replay ledger fails closed when full; explicitly rotate the secret to accept more deliveries. Old signed bodies then fail under the new secret. Private issue bodies are not persisted in event envelopes.

## Watch policies and persistence

Watch templates support build completion/failure, experiment completion/failure, battery below 15% and assigned issues. The API also supports deterministic `eq/ne/lt/le/gt/ge` conditions, project/source/device filters, static target nodes, expected outcomes, cooldowns, severity filters, expiration, one-time times and recurring intervals of at least 60 seconds. Creation defaults to disabled; enabling or changing an active action requires explicit authorization. Inspect, edit, pause, disable and delete through the service API; the panel provides common watch creation and enable/pause/delete controls. `dry_run` matches without executing.

Autonomy levels are notify, read/analyze, reversible local action and exact-confirmation consequence. Level 0 only publishes notices. External mutations cannot run as reversible local actions. Level 3 creates a pending receipt, which can be previewed and confirmed through the existing one-use approval mechanism. A committed atomic claim prevents simultaneous confirmations from dispatching that receipt twice. File paths are fixed by the user, not interpolated from external events. Event content cannot select another capability, change policy, issue approvals or enable monitoring.

SQLite persists watch configuration, references, cursors, action receipts and causal keys. Event, action and causal history retain 5,000 entries each; local dedupe is bounded to that retained history. Signed webhook replay has the separate fail-closed ledger. Interrupted action receipts become `interrupted_review` after restart and never replay a possible mutation. Expired watches are removed when loaded. Overdue recurring schedules emit one catch-up event and advance from the current time. Monitoring and security collection require explicit enablement after restart.

The queue holds at most 256 envelopes. A tick processes at most 32 events within its time budget; per-minute action and network budgets cap work. Critical events can replace ordinary queued events. Interactive actions call their existing direct kernel/PC path and never join this queue. Derived producers call `publish(event, context=context)` to carry bounded correlation and depth references through the existing worker context allowlist. A watch cannot repeat within one causal chain; depth and rate bounds provide additional safeguards. Default background model budget is the existing `ModelBudget(0, 0)`. Free-form semantic classification is unavailable rather than an uncontrolled per-event inference feature.

Notifications occur only for an enabled matching watch. Quiet periods, minimum severity, failure-only policy and an explicitly configured critical override are available. Event audit stores references, decisions, task ids, verification state and notification receipts. It does not store provider message bodies, screenshots, microphone/camera data or private reasoning. Only the existing local notification channel is implemented; external messaging and paired-device notification adapters require separate implementation and explicit grants.

## Cross-phase events

Project Builder publishes final persisted build status through the same EventBus. Research Lab publishes real terminal experiment state after its durable checkpoint. `research.refresh_source` imports an explicitly selected new source version with the existing ingestion engine, preserves provenance and marks prior versions and dependent results stale for review. Device Mesh validates battery percentages and attaches the actual authenticated TLS peer identity; connection, disconnection and revocation also publish structured events. A watch may route a registered read/analysis capability to a statically selected paired node, whose existing remote permission, lease and observation contracts still apply.

Controlled integration tests read an assigned issue, run an approved local repair through the existing Builder, observe failure/completion notices and verify no push; refresh a literature file and observe dependent staleness; complete a real three-run laboratory experiment; and send a genuine paired TLS node event followed by a remotely verified calculation.

## Defensive monitoring and containment

Choose local metadata sources explicitly. The implemented process collector observes accessible Windows executable identity and start time, up to 128 processes; selected PIDs may also be compared with explicitly sourced SHA-256 indicators. New or odd executable names alone do not establish a threat. Protected/inaccessible processes are counted. Parent trees, command-line capture, Authenticode enrichment and CPU anomaly classification are not implemented.

Optional collectors use bounded read-only Windows queries for TCP listeners and owning PIDs, Win32 startup-command metadata, and at most 16 recent System log errors. They do not scan remote hosts or attempt privilege elevation. They do not enumerate all scheduled tasks/services/registry persistence locations, or infer that an OS error proves an attack. Collection failure is visible and cannot establish monitoring success. File monitoring is limited to at most eight selected local directories, their immediate entries and 64 files per collection, each at most 8 MiB. It does not recursively scan a disk. New startup/listener entries and changed files are low-severity context for review.

Findings record node, category, severity, confidence, evidence, object references, optional process/file/network identity, recommendation, status and indicator origin. Incidents record references, timeline, verified actions, resolution and OPEN/INVESTIGATING/CONTAINED/RESOLVED/FALSE_POSITIVE/MONITORING state. Exact finding suppression persists a reason and prevents repeat alerts. Baseline metadata is bounded at 5,000 entries, findings at 2,000 and trusted indicators at 512. The implementation is a scoped defensive tool, not an antivirus or forensic certification.

Process termination checks PID, canonical executable and native start identity and retains the same OS process handle through termination and exit observation, protecting against PID reuse. MORICE itself, system PID values and core executables under the Windows directory are excluded. The harmless fixture process remains alive after denied or changed-identity requests, and exits only after its exact approval.

Quarantine and restore need exact approvals and a selected directory scope. Symlinks, reparse paths and multiple hard links are refused. Quarantine holds a Windows file handle that blocks concurrent writes/deletes, checks the selected SHA-256, preserves a DPAPI-encrypted copy plus intent metadata, and removes that exact file by handle. Restore creates an exclusive new file, validates the canonical handle path, writes the decrypted bytes, and independently observes the original hash. Existing files are never overwritten. Protected copies remain as evidence; quarantine is capped at 256 entries/128 MiB and does not automatically delete them. A crash can leave a `COPY_PRESERVED` intent or a partial restore requiring manual review; mutations are not replayed automatically.

No offensive capability, credential dumping, exploitation, persistence creation, lateral movement, security-tool bypass or unsolicited containment exists. Broad network isolation is explicitly unavailable because no authorized firewall adapter is installed. Mesh revocation and connector disconnect remain available through their existing services; remote security telemetry does not grant containment. Remote security collectors and automatic remote containment are not implemented. The security panel accurately says **Monitoring off**, **Selected collector failed**, or **No high-severity finding in monitored sources**, rather than asserting the machine is completely safe.

## Validation and further work

Tests and evidence are described in `ambient-connectors-security-report.md` and the separate review in `ambient-connectors-security-audit.md`. Run all four Phase 7 test modules, then the full suite. `scripts/benchmark_ambient.py`, `scripts/verify_ambient_startup.py` and `scripts/verify_ambient_package.py` produce reproducible local evidence under `build/`.

Phase 8 can harden more providers, richer collectors, relay configuration, scope UX, outage/capacity review, frozen builds and physical device validation on this shared foundation. Phase 9 media models are not installed or changed. Official protocol references: [GitHub device authorization and refresh](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps), [GitHub webhook authentication](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries), [GitHub issues API](https://docs.github.com/en/rest/issues/issues), [Windows process termination](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess).

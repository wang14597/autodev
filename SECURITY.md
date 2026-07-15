# Security Policy

## Vulnerability Reporting

If you discover a security vulnerability in AutoDev, please report it responsibly:

**Contact:** `待填` (fill in: security-team@example.com or security@feishu-group)

**Process:**
1. Do **not** open a public issue or merge request.
2. Email the security contact with:
   - Description of the vulnerability
   - Steps to reproduce (if applicable)
   - Potential impact
   - Suggested fix (if any)
3. Allow up to 48 hours for acknowledgment; we will work with you on a coordinated disclosure timeline.

---

## Threat Model: Autonomous Code-Writing Agent

AutoDev is designed to autonomously propose and implement code changes. This amplifies both productivity and risk. The following threat categories are **identified but not yet fully mitigated** and represent high-priority work for Iteration 2 and beyond.

### 1. Execution Sandbox Boundary (执行沙箱边界)
**Threat:** Claude Code runs in the user's environment with access to the git repository, file system, and potentially CI/CD secrets.

**Risk:** A compromised or malicious agent could:
- Exfiltrate secrets (GitLab tokens, API keys, credentials)
- Modify critical files outside the task scope
- Push malicious commits to the repository
- Trigger unwanted CI/CD pipeline executions

**Mitigation Status:** 🔴 **计划 2 / 后续必须落实**
- Define a strict **workspace isolation boundary:** Claude Code must operate only within a designated git worktree or sandbox directory.
- Enforce **file ACLs:** Restrict Claude Code from reading/writing files outside the repository and sensitive config paths (`.env`, `~/.ssh`, etc.).
- Audit **subprocess execution:** Log all shell commands executed by Claude Code and review unexplained system calls.
- **Action:** Design and implement a capability-based security model (e.g., OS-level sandboxing or containerized Claude Code execution).

---

### 2. Prompt Injection from Untrusted Content (不可信输入的 Prompt 注入)
**Threat:** Requirements, repository content (comments, READMEs, commit messages), and existing code may contain crafted instructions that manipulate the Claude Code agent.

**Risk:**
- An attacker embeds instructions in a commit message or issue description that tricks the agent into:
  - Bypassing code review gates
  - Modifying unrelated sensitive code
  - Exfiltrating repository secrets
  - Deleting or corrupting artifacts
- Malicious dependencies in `pyproject.toml` or lockfiles could present as requirements.

**Mitigation Status:** 🔴 **计划 2 / 后续必须落实**
- **Sanitize inputs:** Strip and validate all user-supplied content (requirements, repo context, feedback) before passing to Claude Code.
- **Input boundaries:** Clearly separate system prompts (agent configuration) from user prompts (task descriptions) and mark user-supplied content as untrusted.
- **Rate limiting & anomaly detection:** Monitor for unusual prompt patterns or repeated attempts to inject instructions; flag for human review.
- **Prompt hardening:** Use structured templates and enums where possible (e.g., "fix type: [bug|perf|refactor]") instead of free-form text.
- **Action:** Implement a prompt sanitization layer in the `adapters/execution/` module; add tests for common injection patterns.

---

### 3. Credential & Token Least Privilege (凭证最小权限)
**Threat:** Claude Code integrates with GitLab and Lark APIs. Tokens with overly broad permissions enable token theft to compromise the system.

**Risk:**
- A leaked GitLab token with "maintainer" scope could:
  - Merge arbitrary MRs without review
  - Force-push to protected branches
  - Delete repositories or CI/CD pipelines
  - Access private projects unrelated to AutoDev
- A leaked Lark token with "chat_write" + "message_delete" could:
  - Send fraudulent messages on behalf of the team
  - Delete collaboration records
  - Impersonate decisions or approvals

**Mitigation Status:** 🔴 **计划 2 / 后续必须落实**
- **GitLab scopes:** Use API tokens scoped to:
  - **Repository:** Only the target repo(s) for this instance
  - **Access level:** Developer (not Maintainer) for read-write; Reporter for read-only
  - **Expiry:** Short-lived tokens (24h–7d rotation)
- **Lark scopes:** Request only:
  - `chat:write` for sending notifications (not message editing/deletion)
  - `contact:read` for team directory (if needed; prefer hardcoded team list)
  - `approval_instance:read` for querying approval state (not creating/modifying)
- **Secret rotation:** Implement automated token rotation and revocation on suspicious activity.
- **Action:** Audit current token scopes in adapter configurations; reduce to least privilege; document expected scopes per adapter.

---

### 4. Auto-Merge Guardrails (自动合并护栏)
**Threat:** Once WorkItem reaches `SUBMIT_MR`, an autonomous merge decision could bypass critical safeguards.

**Risk:**
- Auto-merging without human review enables:
  - Silent introduction of bugs or security vulnerabilities
  - Violation of team code standards or architecture rules (铁律)
  - Circumvention of CI/CD checks
  - Unaudited changes to critical paths (auth, data access, deployment)

**Mitigation Status:** 🔴 **计划 2 / 后续必须落实**
- **MR merge gate:** All merges (even auto-proposed ones) require:
  - At least one human approval (code owner or designated reviewer)
  - Green CI/CD status (all checks passing)
  - No merge conflicts (force-resolved by human only)
  - Approval evidence in MR history (auditable)
- **Severity-based routing:**
  - **Low:** Small changes (typos, comments, simple refactors) → auto-merge candidate (with full traceability)
  - **Medium:** Feature additions, bug fixes → require human approval
  - **High:** Security, architecture, breaking changes → require at least 2 approvals
- **Rollback triggers:** Automated rollback if post-merge checks fail within 15 minutes.
- **Action:** Model merge decision as a **GatePoint** in the domain (`MERGE_GATE`); wire approval events and ensure `AutonomyDial` is respected.

---

## Current Scope (Iteration 1 / Baseline)

In the current iteration, AutoDev:
- **Does not yet have** execution sandboxing, prompt injection guards, or token privilege enforcement.
- **Operates with human review:** Merge gate is `HUMAN` by default; auto-merge is not enabled.
- **Assumes trusted environment:** The user running Claude Code is trusted; the repository content is reviewed before AutoDev is deployed.

---

## Security Incident Response

If a security incident is suspected (e.g., tokens leaked, unauthorized commit pushed):

1. **Immediate:** Revoke all GitLab and Lark tokens associated with the instance.
2. **Investigation:** Review audit logs and MR history for suspicious changes.
3. **Remediation:** Revert unauthorized commits; audit code for backdoors or exfiltration.
4. **Communication:** Notify the team and relevant stakeholders.
5. **Hardening:** Implement fixes to prevent recurrence; update this threat model.

---

## Future Work (Iteration 2 & Beyond)

All items in this section are **high-priority** and must be addressed before expanding AutoDev to larger teams or higher-risk repositories:

- [ ] **Execution Sandbox:** Containerize Claude Code or use OS-level isolation (seccomp, AppArmor).
- [ ] **Prompt Injection Guards:** Implement sanitization layer and anomaly detection.
- [ ] **Token Rotation:** Automate credential lifecycle management.
- [ ] **Auto-Merge Policy:** Model in domain; wire approval gates; test rollback.
- [ ] **Audit Trail:** Immutable, tamper-evident logging of all AI decisions and human approvals.
- [ ] **Security Scanning:** Integrate dependency scanning (e.g., `safety`, `bandit`) into verification gate.

---

See also:
- `CONTRIBUTING.md` — Code review standards
- `docs/architecture/2026-07-15-strategic-direction-and-domain-model.md` — Architecture & governance
- `CHANGELOG.md` — Feature timeline

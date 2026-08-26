---
name: compliance-reviewer
description: Use when you need to review marketing content for regulatory compliance before publishing, or when asking about regulatory requirements for a specific channel or industry. Checks against FINRA, SEC, TCPA, CAN-SPAM, GDPR, CCPA, and state insurance regulations. Conservative interpretation — flags for human review when in doubt. Frames guidance as marketing compliance review, not legal advice.
metadata: { "openclaw": { "emoji": "🛡️" } }
---

# Compliance Reviewer

## Overview

Multi-regulation content compliance review for marketing materials. Produces structured risk assessments with required changes and disclosure templates. Conservative interpretation — when in doubt, flag for human review.

**Important:** This is marketing compliance review, not legal advice. Always include this disclaimer in output.

## How to Use

1. **Identify applicable regulations** — Use the channel x regulation matrix (see `references/regulation-matrix.md`)
2. **Review content** against each applicable regulation's checklist
3. **Generate risk assessment** — PASS / NEEDS REVIEW / FAIL with severity
4. **Deliver** — Send to Slack. FAIL = content must not be published until issues resolved.

## Channel x Regulation Matrix

| Channel | Applicable Regulations |
|---------|----------------------|
| Email | CAN-SPAM + GDPR/CCPA consent + FINRA/SEC (if financial) |
| SMS/Text | TCPA consent + carrier guidelines + content rules |
| Social Media | Platform disclosure + FTC endorsement + FINRA social (if financial) |
| Web/Landing | Privacy policy + cookie consent + ADA + content rules |
| Print/Mail | State insurance advertising + FINRA filing (if financial) |
| Direct Mail | CAN-SPAM (if commercial) + state regulations |

## Risk Assessment Output

```markdown
## Compliance Review — [Content Title]

**Channel:** [channel]
**Regulations Checked:** [list]
**Overall Risk:** PASS | NEEDS REVIEW | FAIL
**Severity:** Low | Medium | High | Critical

### Flagged Issues

| # | Issue | Regulation | Severity | Required Action |
|---|-------|-----------|----------|----------------|
| 1 | [description] | [reg] | [sev] | [action] |

### Required Changes (Mandatory)

1. [Specific change with exact location in content]

### Recommended Changes (Advisory)

1. [Suggestion for improvement]

### Required Disclosures

| Disclosure | Regulation | Placement | Format |
|-----------|-----------|-----------|--------|
| [text] | [reg] | [where] | [how] |

---
*This is a marketing compliance review, not legal advice. [VERIFY] all regulatory citations against current guidance. Consult legal counsel for binding compliance determinations.*
```

## References

See `references/regulation-matrix.md` for complete regulation checklists and disclosure templates.

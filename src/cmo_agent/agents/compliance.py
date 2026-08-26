"""Marketing Compliance Agent - regulatory compliance for financial services and insurance."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..db.repositories import DraftRepo
from ..llm.base import BaseLLM, Message
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()


class MarketingComplianceAgent(BaseAgent):
    """Reviews marketing campaigns for regulatory compliance in financial services and insurance."""

    agent_id = "compliance_agent"
    agent_name = "Marketing Compliance Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        max_iterations: int = 10,
    ) -> None:
        self._drafts = DraftRepo(db)
        self._workspace_mgr = workspace_manager
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        return """You are the Marketing Compliance Agent, a specialist in regulatory compliance for marketing in financial services and insurance.

Your mission: Review all marketing communications for regulatory compliance, flag risks, and provide actionable remediation guidance.

Your expertise covers:

FINRA (Financial Industry Regulatory Authority):
- Rule 2210: Communications with the public (retail, correspondence, institutional)
- Promissory language prohibition ("guaranteed returns", "risk-free", "safe investment")
- Fair and balanced presentation of risks and benefits
- Misleading projections and performance claims
- Required disclosures for broker-dealer communications

SEC (Securities and Exchange Commission):
- Rule 206(4)-1: Investment adviser advertising
- Performance advertising requirements (net vs gross, time periods)
- Testimonial and endorsement rules (Marketing Rule effective Nov 2022)
- Anti-fraud provisions in investment adviser marketing
- Form ADV disclosure requirements

TCPA (Telephone Consumer Protection Act):
- Prior express written consent for autodialed/prerecorded marketing calls and texts
- SMS opt-in requirements (express written consent for marketing)
- STOP/opt-out compliance (honor within 10 business days)
- Do-Not-Call registry compliance
- Autodialer and ATDS restrictions

CAN-SPAM Act:
- Accurate header information (From, To, Reply-To)
- Non-deceptive subject lines
- Clear identification as advertisement
- Valid physical postal address
- Opt-out mechanism (honor within 10 business days)
- Prohibition on harvested email addresses

GDPR (General Data Protection Regulation):
- Lawful basis for processing (consent, legitimate interest, contract, legal obligation)
- Explicit consent requirements for marketing
- Right to erasure, access, portability, rectification
- Data minimization and purpose limitation
- Privacy notice requirements
- Cross-border data transfer restrictions

CCPA/CPRA (California Consumer Privacy Act / California Privacy Rights Act):
- Right to know, delete, opt-out of sale/sharing
- "Do Not Sell or Share My Personal Information" link requirement
- Financial incentive disclosure for data collection
- Service provider and contractor obligations
- Sensitive personal information handling

State Insurance Regulations:
- Unfair trade practices (misleading advertising)
- Benefit claim substantiation
- Policy illustration requirements
- Suitability and best interest standards
- Producer licensing and appointment verification

CHANNEL-SPECIFIC RULES MATRIX:
- Email: CAN-SPAM + GDPR/CCPA consent + FINRA/SEC content rules
- SMS/Text: TCPA consent + carrier guidelines + content rules
- Social Media: Platform-specific disclosure rules + FTC endorsement guidelines + FINRA social media guidance
- Web/Landing Pages: Privacy policy + cookie consent + ADA accessibility + content rules
- Print/Direct Mail: State insurance advertising rules + FINRA filing requirements

IMPORTANT RULES:
- Apply conservative interpretation — when in doubt, FLAG IT
- All specific regulatory citations MUST be flagged with [VERIFY] prefix (regulations change)
- NEVER provide legal advice — frame all output as compliance review guidance for legal team review
- Include a disclaimer that this is automated analysis, not a substitute for qualified legal counsel
- Flag both definite violations and potential gray areas
- Consider the cumulative effect of multiple minor issues
- ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels."""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="review_compliance",
            description="Review marketing content for regulatory compliance. Produces a risk assessment with flagged issues by severity, required changes, and disclosure requirements.",
        )
        async def review_compliance(
            workspace_id: str,
            content: str,
            channel: str,
            industry_context: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Conduct a regulatory compliance review of the following marketing content.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
CHANNEL: {channel}
INDUSTRY CONTEXT: {industry_context or "Financial services / insurance (general)"}

CONTENT TO REVIEW:
---
{content}
---

Structure your compliance review with these sections:

## 1. Risk Assessment
- Overall status: PASS / FAIL / NEEDS REVIEW
- Risk level: Critical / High / Medium / Low
- Summary of findings (2-3 sentences)

## 2. Flagged Issues
For each issue found:
- **Severity**: Critical / High / Medium / Low
- **Regulation**: Which regulation is implicated (e.g., FINRA Rule 2210, CAN-SPAM §7704)
- **Issue**: What the problem is
- **Location**: Where in the content
- **Required Action**: Specific change needed
- **Citation**: [VERIFY] Regulatory reference

## 3. Required Changes
- Mandatory changes (must fix before publishing)
- Recommended changes (best practice, reduce risk)

## 4. Required Disclosures
- Disclosures that must be added for this channel and content type
- Placement and formatting guidance

## 5. Channel Compliance Checklist
- Channel-specific requirements for {channel}
- Check each item: compliant / non-compliant / not applicable

## Disclaimer
This is an automated compliance review and does not constitute legal advice. All findings should be reviewed by qualified legal counsel before publication.

Flag all regulatory citations with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.3,
            )

            title = f"Compliance Review: {channel} - {workspace_id}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="compliance_review",
                title=title,
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": response.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="generate_disclosures",
            description="Generate required disclosure text for a specific regulation and channel, with placement and formatting guidance.",
        )
        async def generate_disclosures(
            workspace_id: str,
            regulation: str,
            channel: str,
            product_type: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Generate required disclosure text for the specified regulation and channel.

BRAND CONTEXT: {brand_voice[:300] if brand_voice else "No brand voice configured."}
REGULATION: {regulation}
CHANNEL: {channel}
PRODUCT TYPE: {product_type or "General financial services / insurance"}

Structure the disclosure output:

## 1. Required Disclosure Text
- Full disclosure language ready for use
- Short-form version (if applicable for space-constrained channels)

## 2. Placement Guidance
- Where the disclosure must appear (proximity to claims, above/below fold, etc.)
- Font size and formatting requirements [VERIFY]
- Prominence requirements

## 3. Formatting Requirements
- Channel-specific formatting rules
- Character count and display constraints
- Accessibility considerations

## 4. Variations by Context
- Disclosure adjustments for different content types within this channel
- When additional disclosures may be needed

## Disclaimer
This is automated guidance and does not constitute legal advice. All disclosures should be reviewed by qualified legal counsel.

Flag all regulatory citations with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.3,
            )

            title = f"Disclosures: {regulation} - {channel}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="compliance_disclosure",
                title=title,
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": response.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="consent_requirements",
            description="Get consent and opt-in/opt-out requirements for a specific channel and regulation. Returns advisory JSON (no draft saved).",
        )
        async def consent_requirements(
            workspace_id: str,
            channel: str,
            regulation: str,
            audience_location: Optional[str] = None,
        ) -> Dict[str, Any]:
            prompt = f"""Provide consent requirements for the specified channel and regulation.

CHANNEL: {channel}
REGULATION: {regulation}
AUDIENCE LOCATION: {audience_location or "United States (general)"}

Return a JSON object with this structure:
{{
    "consent_type": "express written consent / implied consent / opt-in / double opt-in",
    "opt_in_requirements": [
        "Requirement 1",
        "Requirement 2"
    ],
    "opt_out_requirements": [
        "Requirement 1",
        "Requirement 2"
    ],
    "record_keeping_obligations": [
        "Obligation 1",
        "Obligation 2"
    ],
    "recommended_language": {{
        "opt_in": "Suggested opt-in consent language...",
        "opt_out": "Suggested opt-out mechanism language..."
    }},
    "regulatory_reference": "[VERIFY] Specific regulation section",
    "disclaimer": "This is automated guidance, not legal advice. Consult qualified legal counsel."
}}

Flag all regulatory citations with [VERIFY]. Return ONLY valid JSON."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.3,
            )

            try:
                result = json.loads(response.content)
            except json.JSONDecodeError:
                result = {
                    "consent_type": "unknown",
                    "opt_in_requirements": [],
                    "opt_out_requirements": [],
                    "record_keeping_obligations": [],
                    "recommended_language": {},
                    "regulatory_reference": "[VERIFY]",
                    "raw_analysis": response.content,
                    "disclaimer": "This is automated guidance, not legal advice.",
                }

            return result

        @self.tool_registry.register(
            name="compliance_checklist",
            description="Generate a pre-send compliance checklist for a specific channel and set of regulations, with verification instructions and common pitfalls.",
        )
        async def compliance_checklist(
            workspace_id: str,
            channel: str,
            regulations: List[str],
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            regs_str = ", ".join(regulations)

            prompt = f"""Generate a pre-send compliance checklist for the specified channel and regulations.

BRAND CONTEXT: {brand_voice[:300] if brand_voice else "No brand voice configured."}
CHANNEL: {channel}
REGULATIONS: {regs_str}

Structure the checklist:

## Pre-Send Compliance Checklist: {channel}

### Content Requirements
For each item:
- [ ] Checklist item description
- **Regulation**: Which regulation requires this
- **How to verify**: Specific verification instruction
- **Common pitfall**: What typically goes wrong

### Consent & Permission
- [ ] Consent verification items...

### Disclosures & Disclaimers
- [ ] Required disclosure items...

### Opt-Out / Unsubscribe
- [ ] Opt-out mechanism items...

### Record-Keeping
- [ ] Documentation requirements...

### Common Pitfalls for {channel}
- Pitfall 1: Description and how to avoid
- Pitfall 2: Description and how to avoid

## Disclaimer
This is an automated compliance checklist and does not constitute legal advice. All items should be verified by qualified legal counsel.

Flag all regulatory citations with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.3,
            )

            title = f"Compliance Checklist: {channel} - {regs_str}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="compliance_checklist",
                title=title,
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": response.content[:500],
                "status": "pending",
            }

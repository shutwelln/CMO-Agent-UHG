"""Legal Strategy Agent - contract drafting, risk mitigation, and negotiation guidance."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import structlog

from ..db.database import Database
from ..db.repositories import ConfigRepo, DraftRepo
from ..llm.base import BaseLLM, Message
from ..quality import QualityCriterion, RefinementConfig, RefinementLoop
from ..quality.hooks import build_hook_chain, make_em_dash_hook
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

# Legal strategy quality criteria (higher threshold for legal precision)
_LEGAL_CRITERIA = [
    QualityCriterion(
        name="precision",
        description="Precise legal language with no ambiguous terms or vague clauses",
    ),
    QualityCriterion(
        name="completeness", description="All required sections and standard provisions covered"
    ),
    QualityCriterion(
        name="enforceability",
        description="Clauses structured for enforceability in relevant jurisdictions",
    ),
    QualityCriterion(
        name="risk_coverage",
        description="Comprehensive risk mitigation, liability limits, and protective provisions",
    ),
    QualityCriterion(
        name="plain_language_clarity",
        description="Complex legal concepts explained in accessible language alongside formal terms",
    ),
]

FOUR_PART_SUFFIX = """

Structure your response in exactly 4 sections:

## 1. Draft Document
[The actual agreement/document framework]

## 2. Risk Summary
- Key risks identified (with severity: High/Medium/Low)
- Missing protections
- Areas requiring legal review

## 3. Negotiation Notes
- Leverage points
- Common counterparty pushback areas
- Suggested concessions vs. firm positions

## 4. Red Flag Clauses
- Clauses that could be problematic
- One-sided terms to watch for
- Industry-atypical provisions

DISCLAIMER: This is strategic guidance for planning purposes. It does not constitute legal advice. Have all agreements reviewed by qualified legal counsel before execution."""

DISCLAIMER = "This is strategic guidance for planning purposes. It does not constitute legal advice. Have all agreements reviewed by qualified legal counsel before execution."


class LegalStrategyAgent(BaseAgent):
    """Handles contract drafting, risk mitigation, and negotiation strategy."""

    agent_id = "legal_strategy_agent"
    agent_name = "Legal Strategy Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        scanning_llm: Optional[BaseLLM] = None,
        max_iterations: int = 10,
    ) -> None:
        self._drafts = DraftRepo(db)
        self._config = ConfigRepo(db)
        self._workspace_mgr = workspace_manager
        self._scanning_llm = scanning_llm
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        return """You are the Legal Strategy Agent, a specialist in marketing-related legal strategy covering contracts, agreements, risk analysis, and negotiation guidance.

Your mission: Provide strategic legal frameworks and risk mitigation guidance for partnerships, vendors, and marketing initiatives.

Your expertise covers:
- Non-disclosure agreement (NDA) frameworks
- Partnership and collaboration agreements
- Term sheets for deals and investments
- Contract risk analysis and red flag identification
- Negotiation strategy and talking points
- Plain-English clause explanations
- Full contract review with section-by-section analysis

IMPORTANT RULES:
- All specific legal claims MUST be flagged with [VERIFY WITH LEGAL COUNSEL]
- Every response starts with disclaimer: "This is strategic guidance for planning purposes. It does not constitute legal advice. Have all agreements reviewed by qualified legal counsel before execution."
- All draft documents are saved for human review
- You provide contract frameworks, risk analysis, and negotiation strategy — you are NOT a licensed attorney replacement
- ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels.

SCOPE BOUNDARIES:
- You handle: contract frameworks, NDAs, partnership agreements, term sheets, risk flagging, negotiation strategy, clause explanations, contract review
- Writer Agent handles: actual marketing content creation
- Performance Marketer Agent handles: campaign-specific vendor negotiations
- You provide strategic legal guidance and document frameworks for human review"""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="draft_nda",
            description="Draft a non-disclosure agreement framework with preamble, definitions, obligations, exclusions, term/termination, remedies, and jurisdiction.",
        )
        async def draft_nda(
            workspace_id: str,
            parties: str,
            purpose: str,
            duration_months: Optional[int] = 24,
            mutual: bool = True,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            nda_type = "mutual" if mutual else "one-way"

            prompt = f"""Draft a {nda_type} non-disclosure agreement (NDA) framework.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
PARTIES: {parties}
PURPOSE: {purpose}
DURATION: {duration_months} months
TYPE: {nda_type}

Structure the NDA into these sections:
1. Preamble — parties, effective date, recitals
2. Definitions — confidential information, disclosing/receiving party, permitted purpose
3. Obligations — non-disclosure, non-use, standard of care, permitted disclosures
4. Exclusions — publicly available, independently developed, prior knowledge, compelled disclosure
5. Term and Termination — duration, survival of obligations, return/destruction of materials
6. Remedies — injunctive relief, indemnification, limitation of liability
7. Jurisdiction — governing law, dispute resolution, venue

Flag all specific legal claims with [VERIFY WITH LEGAL COUNSEL].{FOUR_PART_SUFFIX}"""

            config = RefinementConfig(
                criteria=_LEGAL_CRITERIA,
                max_iterations=3,
                quality_threshold=8.0,
                log_prefix="legal_nda_refinement",
                extra_revision_instructions="Preserve all [VERIFY WITH LEGAL COUNSEL] flags.",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            title = f"NDA: {parties[:60]}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="nda_draft",
                title=title,
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="draft_partnership_agreement",
            description="Draft a partnership agreement outline covering roles, revenue sharing, IP ownership, exclusivity, and dispute resolution.",
        )
        async def draft_partnership_agreement(
            workspace_id: str,
            partner_name: str,
            partnership_type: str,
            scope: str,
            revenue_model: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Draft a partnership agreement outline.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
PARTNER: {partner_name}
PARTNERSHIP TYPE: {partnership_type}
SCOPE: {scope}
REVENUE MODEL: {revenue_model or "To be determined"}

Structure the agreement into these sections:
1. Roles and Responsibilities — each party's obligations, deliverables, timelines
2. Revenue/Value Sharing — compensation structure, payment terms, reporting
3. IP Ownership — pre-existing IP, jointly created IP, licensing rights
4. Exclusivity — territorial, category, or temporal exclusivity terms
5. Term and Termination — duration, renewal, termination triggers, wind-down
6. Dispute Resolution — escalation path, mediation, arbitration, jurisdiction
7. Governance — decision-making, communication cadence, key contacts

Flag all specific legal claims with [VERIFY WITH LEGAL COUNSEL].{FOUR_PART_SUFFIX}"""

            config = RefinementConfig(
                criteria=_LEGAL_CRITERIA,
                max_iterations=3,
                quality_threshold=8.0,
                log_prefix="legal_partnership_refinement",
                extra_revision_instructions="Preserve all [VERIFY WITH LEGAL COUNSEL] flags.",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            title = f"Partnership Agreement: {partner_name}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="partnership_agreement",
                title=title,
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="outline_term_sheet",
            description="Outline a term sheet for deals or investments covering valuation, conditions, milestones, and governance.",
        )
        async def outline_term_sheet(
            workspace_id: str,
            deal_type: str,
            parties: str,
            key_terms: str,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Outline a term sheet for the following deal.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
DEAL TYPE: {deal_type}
PARTIES: {parties}
KEY TERMS: {key_terms}

Structure the term sheet into these sections:
1. Valuation/Pricing — deal value, pricing structure, payment schedule
2. Conditions Precedent — due diligence, approvals, regulatory requirements
3. Milestones — performance targets, deliverable timelines, go/no-go gates
4. Governance — decision rights, board/advisory structure, reporting requirements
5. Representations and Warranties — key representations from each party
6. Closing Timeline — target close date, key dates, contingencies

Flag all specific legal claims with [VERIFY WITH LEGAL COUNSEL].{FOUR_PART_SUFFIX}"""

            config = RefinementConfig(
                criteria=_LEGAL_CRITERIA,
                max_iterations=3,
                quality_threshold=8.0,
                log_prefix="legal_term_sheet_refinement",
                extra_revision_instructions="Preserve all [VERIFY WITH LEGAL COUNSEL] flags.",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            title = f"Term Sheet: {deal_type} - {parties[:40]}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="term_sheet",
                title=title,
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="flag_risk_areas",
            description="Analyze a contract or agreement and flag risk areas with severity, issues, and recommendations.",
        )
        async def flag_risk_areas(
            workspace_id: str,
            agreement_text: str,
            agreement_type: Optional[str] = None,
        ) -> Dict[str, Any]:
            prompt = f"""Analyze the following agreement and flag all risk areas.

AGREEMENT TYPE: {agreement_type or "Not specified"}
AGREEMENT TEXT:
{agreement_text}

Return your analysis as JSON with this structure:
{{"risks": [{{"clause": "the problematic clause text", "severity": "High/Medium/Low", "issue": "what's wrong", "recommendation": "what to do"}}], "overall_risk_level": "High/Medium/Low", "top_priority": "the most critical issue to address first"}}

DISCLAIMER: {DISCLAIMER}"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.4,
            )

            try:
                result = json.loads(response.content)
            except json.JSONDecodeError:
                result = {
                    "risks": [],
                    "overall_risk_level": "Unknown",
                    "top_priority": response.content[:200],
                    "raw_analysis": response.content,
                }

            return result

        @self.tool_registry.register(
            name="suggest_negotiation_strategy",
            description="Provide negotiation strategy and talking points including BATNA analysis, concession strategy, and walk-away triggers.",
        )
        async def suggest_negotiation_strategy(
            workspace_id: str,
            deal_context: str,
            our_position: str,
            counterparty_position: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Provide a negotiation strategy and talking points.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
DEAL CONTEXT: {deal_context}
OUR POSITION: {our_position}
COUNTERPARTY POSITION: {counterparty_position or "Not specified — anticipate likely positions"}

Cover these areas:
1. Opening Position — recommended starting stance and framing
2. BATNA Analysis — best alternative to negotiated agreement for each side
3. Concession Strategy — what to concede vs. hold firm, trade-off packages
4. Talking Points — key messages, value propositions, persuasion angles
5. Walk-Away Triggers — deal-breakers, minimum acceptable terms
6. Anchor Points — initial offers/demands to set negotiation range

Flag all specific legal claims with [VERIFY WITH LEGAL COUNSEL].{FOUR_PART_SUFFIX}"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.6,
            )

            title = f"Negotiation Strategy: {deal_context[:60]}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="negotiation_strategy",
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
            name="explain_clause",
            description="Explain legal clauses in plain English with implications, common modifications, and pitfalls.",
        )
        async def explain_clause(
            clause_text: str,
            context: Optional[str] = None,
        ) -> Dict[str, Any]:
            prompt = f"""Explain the following legal clause in plain English.

CLAUSE TEXT: {clause_text}
CONTEXT: {context or "General contract clause"}

Provide your explanation with these sections:
1. Plain English — what this clause actually means in simple terms
2. Implications — what this means for each party, practical consequences
3. Common Modifications — typical variations or alternatives to this clause
4. Watch Out For — common pitfalls, hidden risks, or tricky language

Return as JSON: {{"plain_english": "...", "implications": "...", "common_modifications": "...", "watch_out_for": "..."}}

DISCLAIMER: {DISCLAIMER}"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.3,
            )

            try:
                result = json.loads(response.content)
            except json.JSONDecodeError:
                result = {
                    "plain_english": response.content,
                    "implications": "",
                    "common_modifications": "",
                    "watch_out_for": "",
                }

            return result

        @self.tool_registry.register(
            name="analyze_contract",
            description="Full contract review with section-by-section analysis, favorable/unfavorable terms, missing protections, and suggested amendments.",
        )
        async def analyze_contract(
            workspace_id: str,
            contract_text: str,
            our_role: str,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Conduct a full contract review with section-by-section analysis.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
OUR ROLE: {our_role}
CONTRACT TEXT:
{contract_text}

Provide a thorough analysis covering:
1. Section-by-Section Analysis — key provisions, what each section means for us
2. Favorable Terms — clauses that benefit our position
3. Unfavorable Terms — clauses that disadvantage us, with severity
4. Missing Protections — standard clauses that are absent but should be included
5. Suggested Amendments — specific changes to propose, with rationale

Flag all specific legal claims with [VERIFY WITH LEGAL COUNSEL].{FOUR_PART_SUFFIX}"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.4,
            )

            title = f"Contract Analysis: {our_role[:60]}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="contract_analysis",
                title=title,
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": response.content[:500],
                "status": "pending",
            }

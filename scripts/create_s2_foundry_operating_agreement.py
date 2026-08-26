"""Create the S2 Foundry, LLC Operating Agreement as a Google Doc.

Drafts a complete Operating Agreement based on the agreed positions
from the Co-Founder Discussion Guide. Bypasses LLM generation to
ensure exact content fidelity.

Usage:
    python scripts/create_s2_foundry_operating_agreement.py
    python scripts/create_s2_foundry_operating_agreement.py --update ID
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))


def build_document_structure() -> dict:
    """Build the Operating Agreement document structure."""
    return {
        "title": "S2 Foundry, LLC - Operating Agreement",
        "sections": [
            # ── Preamble ────────────────────────────────────────────────
            {
                "heading": "",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "OPERATING AGREEMENT OF S2 FOUNDRY, LLC"
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "This Operating Agreement (\"Agreement\") of "
                            "S2 Foundry, LLC (the \"Company\"), a "
                            "Wisconsin limited liability company, is "
                            "entered into as of [DATE], by and between "
                            "the following Members:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Nick Shutwell (\"Member A\")",
                            "jhaw ventures LLC, a Wyoming limited liability company, acting through its sole member Justin Shaw (\"Member B\")",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "The Members hereby agree to the terms and "
                            "conditions of this Agreement as follows."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "IMPORTANT: This document is a draft "
                            "prepared as a working starting point. It "
                            "should be reviewed, revised, and finalized "
                            "by a licensed attorney before execution."
                        ),
                    },
                ],
            },
            # ── Article I: Formation & Purpose ──────────────────────────
            {
                "heading": "Article I: Formation & Purpose",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "1.1 Formation. The Members have formed "
                            "S2 Foundry, LLC as a Wisconsin limited "
                            "liability company (\"LLC\") by filing "
                            "Articles of Organization with the "
                            "Wisconsin Secretary of State."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "1.2 Name. The name of the Company is "
                            "S2 Foundry, LLC."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "1.3 Purpose. The Company is formed to "
                            "develop, market, and sell technology "
                            "products and to provide technology "
                            "services to third-party clients. The "
                            "Company's first product is Agent Tunnel. "
                            "The Company may engage in any other "
                            "lawful business activity as agreed upon "
                            "by the Members."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "1.4 Term. The Company shall continue "
                            "until dissolved in accordance with "
                            "Article X of this Agreement or as "
                            "required by law."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "1.5 Registered Agent. The registered "
                            "agent and office of the Company shall "
                            "be Resident Agents Inc., 2800 E. "
                            "Enterprise Ave, STE 333, Appleton, "
                            "WI 54913."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "1.6 Principal Office. The principal "
                            "office of the Company shall be at "
                            "2800 E. Enterprise Ave, STE 333, "
                            "Appleton, WI 54913, or such other "
                            "location as the Members may agree."
                        ),
                    },
                ],
            },
            # ── Article II: Members & Membership Interests ──────────────
            {
                "heading": "Article II: Members & Membership Interests",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "2.1 Members. The Members of the Company "
                            "and their respective Membership Interest "
                            "percentages are as follows:"
                        ),
                    },
                    {
                        "type": "table",
                        "headers": [
                            "Member",
                            "Membership Interest",
                        ],
                        "rows": [
                            ["Nick Shutwell (Member A)", "50%"],
                            ["jhaw ventures LLC (Member B)", "50%"],
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "2.2 Membership Certificates. No "
                            "certificates shall be issued for "
                            "Membership Interests. Each Member's "
                            "interest is evidenced solely by this "
                            "Agreement."
                        ),
                    },
                ],
            },
            # ── Article III: Capital Contributions ──────────────────────
            {
                "heading": "Article III: Capital Contributions",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "3.1 Initial Contributions. The Members "
                            "have made the following initial capital "
                            "contributions to the Company:"
                        ),
                    },
                    {
                        "type": "table",
                        "headers": [
                            "Member",
                            "Contribution",
                            "Type",
                        ],
                        "rows": [
                            [
                                "Nick Shutwell",
                                "[DESCRIBE CONTRIBUTION]",
                                "[Cash / Services / Other]",
                            ],
                            [
                                "jhaw ventures LLC",
                                "[DESCRIBE CONTRIBUTION]",
                                "[Cash / IP / Other]",
                            ],
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Agent Tunnel, as the Company's first "
                            "product, is an asset of the Company. "
                            "Its Intellectual Property (IP) is owned "
                            "by the Company as of the date of this "
                            "Agreement."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "3.2 Additional Contributions. No Member "
                            "is required to make additional capital "
                            "contributions. If additional capital is "
                            "needed, the Members shall first attempt "
                            "to contribute on a pro-rata basis. If "
                            "one Member contributes more than the "
                            "other, the excess shall be treated as a "
                            "member loan to the Company (not an "
                            "equity adjustment) with an interest rate "
                            "and repayment schedule agreed upon in "
                            "writing at the time of the loan."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "3.3 No Interest on Contributions. No "
                            "Member shall receive interest on any "
                            "capital contribution."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "3.4 Return of Contributions. No Member "
                            "has the right to demand the return of "
                            "any capital contribution except as "
                            "provided in this Agreement upon "
                            "dissolution."
                        ),
                    },
                ],
            },
            # ── Article IV: Profits, Losses & Distributions ─────────────
            {
                "heading": (
                    "Article IV: Profits, Losses & Distributions"
                ),
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "4.1 Allocation. The net profits and net "
                            "losses of the Company shall be allocated "
                            "50% to each Member."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "4.2 Distributions. Distributions of "
                            "available cash shall be made at such "
                            "times and in such amounts as determined "
                            "by mutual agreement of the Members, "
                            "and shall be divided equally (50/50) "
                            "between the Members. Distributions shall "
                            "only be made after the Company has "
                            "sufficient reserves to meet its "
                            "obligations."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "4.3 Tax Distributions. The Company shall "
                            "distribute to each Member, at least "
                            "quarterly, an amount sufficient to cover "
                            "each Member's estimated tax liability "
                            "arising from the Company's income "
                            "allocated to that Member, to the extent "
                            "the Company has available cash."
                        ),
                    },
                ],
            },
            # ── Article V: Management & Authority ───────────────────────
            {
                "heading": "Article V: Management & Authority",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "5.1 Member-Managed. The Company shall be "
                            "managed by its Members. Both Members "
                            "shall have the authority to bind the "
                            "Company in the ordinary course of "
                            "business within their respective domains "
                            "as described in Section 5.2."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "5.2 Domain Authority. The Members agree "
                            "to the following division of operational "
                            "domains. The domain lead has final say "
                            "on day-to-day decisions within their "
                            "area, subject to the limitations in "
                            "Section 5.3."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": [
                            "Member A: Business & Commercial",
                            "Member B: Technology & Product",
                        ],
                        "rows": [
                            [
                                "Marketing & brand strategy",
                                "Product architecture & engineering",
                            ],
                            [
                                "Go-to-market & distribution",
                                "Technical infrastructure & DevOps",
                            ],
                            [
                                "Partnerships & business development",
                                "Data, security & compliance (technical)",
                            ],
                            [
                                "Sales & revenue operations",
                                "R&D and technical roadmap",
                            ],
                            [
                                "Finance & administration",
                                "Vendor selection (technical tools)",
                            ],
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Administrative and legal coordination "
                            "is handled by Member A by default, with "
                            "both Members involved in any decisions "
                            "that create obligations for the Company."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "5.3 Decisions Requiring Unanimous "
                            "Consent. The following actions require "
                            "the unanimous written or verbal consent "
                            "of both Members:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Any expenditure exceeding $2,500",
                            "Any commitment with a term longer "
                            "than 6 months",
                            "Any client commitment with revenue "
                            "implications exceeding $5,000 per year",
                            "Taking on any debt or financial "
                            "obligation on behalf of the Company",
                            "Entering a new market or line of "
                            "business",
                            "Any legal commitment binding the "
                            "Company",
                            "Product pricing decisions",
                            "Client commitments that involve "
                            "technical delivery",
                            "Winding down or dissolving the Company",
                            "Amending this Agreement",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "5.4 Unilateral Authority. Within their "
                            "respective domains, each Member may "
                            "make the following decisions without "
                            "the other Member's consent:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Day-to-day operational decisions",
                            "Spending below the $2,500 threshold",
                            "Vendor choices within their domain",
                            "Tactical execution decisions",
                            "Approval of recurring costs (hosting, "
                            "tools, subscriptions) below the "
                            "$2,500 threshold",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "5.5 Time-Sensitive Decisions. If a "
                            "decision requires immediate action and "
                            "the other Member is unreachable for "
                            "24 hours, either Member may act "
                            "unilaterally provided there is a "
                            "documented business reason for urgency. "
                            "The acting Member must notify the other "
                            "Member within 24 hours of the action "
                            "taken."
                        ),
                    },
                ],
            },
            # ── Article VI: Deadlock Resolution ─────────────────────────
            {
                "heading": "Article VI: Deadlock Resolution",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "6.1 Acknowledgment. The Members "
                            "acknowledge that the 50/50 ownership "
                            "structure may result in disagreements "
                            "where neither Member holds a deciding "
                            "vote. The Members also acknowledge "
                            "their family relationship and agree "
                            "that preserving the personal "
                            "relationship should take priority over "
                            "any single business decision."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "6.2 Resolution Process. In the event of "
                            "a deadlock on any matter requiring "
                            "unanimous consent, the Members shall "
                            "follow this three-step process:"
                        ),
                    },
                    {
                        "type": "numbered_list",
                        "items": [
                            "Cooling-Off Period. The Members shall "
                            "pause the discussion for seven (7) "
                            "calendar days. Each Member shall prepare "
                            "a written position statement outlining "
                            "their reasoning. The Members shall "
                            "reconvene after the cooling-off period "
                            "and attempt to reach agreement.",
                            "Mediation. If the Members cannot agree "
                            "after the cooling-off period, they shall "
                            "submit the matter to mediation by a "
                            "mutually agreed-upon third-party "
                            "advisor. The mediator's role is "
                            "advisory, not binding.",
                            "Domain Authority. If mediation does not "
                            "resolve the deadlock, the Member whose "
                            "operational domain the decision falls "
                            "within (as defined in Section 5.2) "
                            "shall have the final decision. If the "
                            "decision does not clearly fall within "
                            "either domain, the matter shall remain "
                            "tabled until the Members reach agreement "
                            "or elect to invoke Article IX (Shotgun "
                            "Clause).",
                        ],
                    },
                ],
            },
            # ── Article VII: Intellectual Property ──────────────────────
            {
                "heading": "Article VII: Intellectual Property",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "7.1 Company IP. All products, code, "
                            "designs, documentation, and other "
                            "intellectual property created by either "
                            "Member in the course of Company business "
                            "shall be the exclusive property of the "
                            "Company. This includes Agent Tunnel and "
                            "all subsequent products developed under "
                            "the Company."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "7.2 Individual IP. Work done by either "
                            "Member for other employers, clients, or "
                            "personal side projects that is not "
                            "related to Company business remains the "
                            "individual property of that Member. "
                            "\"Company business\" means any product, "
                            "service, or engagement that the Members "
                            "have mutually agreed to pursue under "
                            "S2 Foundry."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "7.3 Client Engagement IP. For "
                            "engagements where the Company provides "
                            "services to third-party clients, the "
                            "default position is that the Company "
                            "retains ownership of any reusable "
                            "tooling, platform components, or "
                            "methodologies developed during the "
                            "engagement. Client-specific deliverables "
                            "and data are governed by the applicable "
                            "client contract."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "7.4 IP on Dissolution. Upon dissolution "
                            "of the Company, IP shall be handled in "
                            "accordance with Article X, Section 10.3."
                        ),
                    },
                ],
            },
            # ── Article VIII: Commitment & Outside Activities ───────────
            {
                "heading": "Article VIII: Commitment & Outside Activities",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "8.1 Part-Time Commitment. The Members "
                            "acknowledge that S2 Foundry is designed "
                            "to operate alongside each Member's other "
                            "professional commitments. There is no "
                            "requirement that either Member devote "
                            "full-time effort to the Company."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "8.2 Reasonable Commitment. Each Member "
                            "shall devote reasonable time and effort "
                            "to the Company's business as needed to "
                            "fulfill their domain responsibilities "
                            "(Section 5.2). The Members may agree in "
                            "writing to specific minimum commitments "
                            "at any time."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "8.3 Outside Activities. Both Members "
                            "are free to maintain other employment, "
                            "clients, and side projects without "
                            "restriction, provided that no Member "
                            "shall directly compete with an active "
                            "Company product or engagement in the "
                            "same market while that product or "
                            "engagement is ongoing."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "8.4 Duty of Loyalty. Each Member owes "
                            "a duty of loyalty to the Company with "
                            "respect to Company business. No Member "
                            "shall divert Company opportunities, "
                            "misuse Company assets, or take actions "
                            "that materially harm the Company's "
                            "interests."
                        ),
                    },
                ],
            },
            # ── Article IX: Transfer of Membership Interests ───────────
            {
                "heading": (
                    "Article IX: Transfer of Membership Interests"
                ),
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "9.1 Restrictions on Transfer. No Member "
                            "may sell, assign, transfer, pledge, or "
                            "otherwise dispose of any part of their "
                            "Membership Interest except in accordance "
                            "with this Article."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "9.2 Right of First Refusal (ROFR). If "
                            "a Member (the \"Selling Member\") "
                            "receives a bona fide offer from a third "
                            "party to purchase all or part of their "
                            "Membership Interest, the Selling Member "
                            "shall first offer the interest to the "
                            "other Member (the \"Remaining Member\") "
                            "on the same terms. The Remaining Member "
                            "shall have thirty (30) calendar days to "
                            "accept or decline the offer. If the "
                            "Remaining Member declines, the Selling "
                            "Member may proceed with the third-party "
                            "sale on terms no more favorable than "
                            "those offered to the Remaining Member."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "9.3 Shotgun Clause. Either Member may "
                            "invoke this provision at any time by "
                            "delivering written notice to the other "
                            "Member (the \"Receiving Member\") "
                            "specifying a price per percentage point "
                            "of Membership Interest. Within thirty "
                            "(30) calendar days of receiving the "
                            "notice, the Receiving Member must elect "
                            "to either:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "(a) Purchase the initiating Member's "
                            "entire Membership Interest at the "
                            "stated price, or",
                            "(b) Sell their own entire Membership "
                            "Interest to the initiating Member at "
                            "the same stated price.",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "If the Receiving Member fails to elect "
                            "within the thirty (30) day period, they "
                            "shall be deemed to have elected option "
                            "(b). The closing of the transaction "
                            "shall occur within sixty (60) calendar "
                            "days of the election."
                        ),
                    },
                ],
            },
            # ── Article X: Withdrawal, Dissolution & Winding Up ────────
            {
                "heading": (
                    "Article X: Withdrawal, Dissolution & Winding Up"
                ),
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "10.1 Voluntary Withdrawal. A Member may "
                            "withdraw from the Company by providing "
                            "sixty (60) calendar days' written notice "
                            "to the other Member. Because the Company "
                            "depends on both Members being actively "
                            "involved, the default outcome of a "
                            "withdrawal is dissolution unless the "
                            "Remaining Member elects to purchase the "
                            "withdrawing Member's interest within "
                            "thirty (30) days of receiving the "
                            "withdrawal notice."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "10.2 Events of Dissolution. The Company "
                            "shall be dissolved upon the occurrence "
                            "of any of the following:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "(a) The mutual written agreement of "
                            "both Members",
                            "(b) The withdrawal of either Member, "
                            "unless the Remaining Member elects to "
                            "continue per Section 10.1",
                            "(c) Extended inactivity, defined as no "
                            "active Company products or client "
                            "engagements for a period of twelve (12) "
                            "consecutive months",
                            "(d) The entry of a decree of judicial "
                            "dissolution",
                            "(e) Any event that makes it unlawful "
                            "for the Company to continue",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "10.3 Winding Up and Distribution of "
                            "Assets. Upon dissolution, the Company's "
                            "affairs shall be wound up in the "
                            "following order:"
                        ),
                    },
                    {
                        "type": "numbered_list",
                        "items": [
                            "Pay all debts and obligations of the "
                            "Company, including any outstanding "
                            "member loans.",
                            "Set aside reasonable reserves for "
                            "contingent or unforeseen liabilities.",
                            "Dispose of Company IP: all "
                            "entity-owned IP (including Agent Tunnel "
                            "and any subsequent products) shall be "
                            "either (a) sold to a third party or to "
                            "one of the Members, with proceeds "
                            "distributed equally, or (b) if neither "
                            "party wishes to purchase, licensed "
                            "non-exclusively and perpetually to both "
                            "Members at no cost.",
                            "Distribute remaining assets to the "
                            "Members in proportion to their "
                            "Membership Interests (50/50).",
                        ],
                    },
                ],
            },
            # ── Article XI: Tax Matters ─────────────────────────────────
            {
                "heading": "Article XI: Tax Matters",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "11.1 Tax Classification. The Company "
                            "shall be treated as a partnership for "
                            "federal and state income tax purposes. "
                            "The Company shall not elect to be "
                            "treated as a corporation without the "
                            "unanimous consent of the Members."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "11.2 Tax Returns. The Company shall "
                            "prepare and timely file all required "
                            "tax returns. Each Member shall receive "
                            "a Schedule K-1 reflecting their share "
                            "of Company income, deductions, and "
                            "credits."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "11.3 Tax Matters Partner. Member A "
                            "shall serve as the \"Tax Matters "
                            "Partner\" (or \"Partnership "
                            "Representative\" under the Bipartisan "
                            "Budget Act) and shall be responsible "
                            "for interactions with the Internal "
                            "Revenue Service (IRS) and state tax "
                            "authorities on behalf of the Company."
                        ),
                    },
                ],
            },
            # ── Article XII: Indemnification ────────────────────────────
            {
                "heading": "Article XII: Indemnification",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "12.1 Indemnification. The Company shall "
                            "indemnify each Member against any "
                            "losses, claims, damages, liabilities, "
                            "and expenses (including reasonable "
                            "attorney's fees) arising from actions "
                            "taken in good faith on behalf of the "
                            "Company and within the scope of that "
                            "Member's authority under this Agreement."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "12.2 Limitation. No Member shall be "
                            "indemnified for actions taken in bad "
                            "faith, with willful misconduct, or "
                            "outside the scope of authority granted "
                            "by this Agreement."
                        ),
                    },
                ],
            },
            # ── Article XIII: General Provisions ────────────────────────
            {
                "heading": "Article XIII: General Provisions",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "13.1 Amendments. This Agreement may be "
                            "amended only by the unanimous written "
                            "consent of the Members."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "13.2 Governing Law. This Agreement "
                            "shall be governed by and construed in "
                            "accordance with the laws of the State "
                            "of Wisconsin."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "13.3 Severability. If any provision of "
                            "this Agreement is held to be invalid "
                            "or unenforceable, the remaining "
                            "provisions shall continue in full "
                            "force and effect."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "13.4 Entire Agreement. This Agreement "
                            "constitutes the entire agreement among "
                            "the Members with respect to the subject "
                            "matter hereof and supersedes all prior "
                            "agreements and understandings, whether "
                            "oral or written."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "13.5 Notices. All notices required or "
                            "permitted under this Agreement shall be "
                            "in writing and delivered by email to "
                            "the addresses on file for each Member, "
                            "or by any other method that provides "
                            "confirmation of delivery."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "13.6 Waiver. The failure of any Member "
                            "to enforce any provision of this "
                            "Agreement shall not be construed as a "
                            "waiver of that provision or the right "
                            "to enforce it at a later time."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "13.7 Counterparts. This Agreement may "
                            "be executed in counterparts, each of "
                            "which shall be deemed an original."
                        ),
                    },
                ],
            },
            # ── Signature Block ─────────────────────────────────────────
            {
                "heading": "Signatures",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "IN WITNESS WHEREOF, the Members have "
                            "executed this Operating Agreement as of "
                            "the date first written above."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "\n\n"
                            "___________________________________\n"
                            "Nick Shutwell, Member A\n"
                            "Date: _______________"
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "\n\n"
                            "___________________________________\n"
                            "Justin Shaw, sole member of jhaw ventures LLC, Member B\n"
                            "Date: _______________"
                        ),
                    },
                ],
            },
        ],
    }


def _render_content(docs_service, doc_id: str, sections: list) -> None:
    """Render sections into the Google Doc body."""
    requests = []
    cursor = 1

    def _heading_style(level: int) -> str:
        mapping = {
            1: "HEADING_1",
            2: "HEADING_2",
            3: "HEADING_3",
            4: "HEADING_4",
        }
        return mapping.get(level, "HEADING_1")

    for section in sections:
        heading = section.get("heading", "")
        level = section.get("level", 1)
        content_blocks = section.get("content", [])

        if heading:
            heading_text = heading + "\n"
            requests.append(
                {
                    "insertText": {
                        "location": {"index": cursor},
                        "text": heading_text,
                    }
                }
            )
            h_start = cursor
            h_end = cursor + len(heading_text)
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": h_start,
                            "endIndex": h_end,
                        },
                        "paragraphStyle": {
                            "namedStyleType": _heading_style(level),
                            "spaceAbove": {"magnitude": 12, "unit": "PT"},
                            "spaceBelow": {"magnitude": 4, "unit": "PT"},
                        },
                        "fields": "namedStyleType,spaceAbove,spaceBelow",
                    }
                }
            )
            cursor = h_end

        for block in content_blocks:
            block_type = block.get("type", "paragraph")

            if block_type == "paragraph":
                text = block.get("text", "")
                if not text:
                    continue
                para_text = text + "\n"
                requests.append(
                    {
                        "insertText": {
                            "location": {"index": cursor},
                            "text": para_text,
                        }
                    }
                )
                p_start = cursor
                p_end = cursor + len(para_text)
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": {
                                "startIndex": p_start,
                                "endIndex": p_end,
                            },
                            "paragraphStyle": {
                                "namedStyleType": "NORMAL_TEXT",
                                "spaceBelow": {
                                    "magnitude": 6,
                                    "unit": "PT",
                                },
                            },
                            "fields": "namedStyleType,spaceBelow",
                        }
                    }
                )
                cursor = p_end

            elif block_type in ("bullets", "numbered_list"):
                items = block.get("items", [])
                if not items:
                    continue
                list_start = cursor
                for item in items:
                    item_text = str(item) + "\n"
                    requests.append(
                        {
                            "insertText": {
                                "location": {"index": cursor},
                                "text": item_text,
                            }
                        }
                    )
                    cursor += len(item_text)
                list_end = cursor
                preset = (
                    "BULLET_DISC_CIRCLE_SQUARE"
                    if block_type == "bullets"
                    else "NUMBERED_DECIMAL_NESTED"
                )
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": {
                                "startIndex": list_start,
                                "endIndex": list_end,
                            },
                            "bulletPreset": preset,
                        }
                    }
                )

            elif block_type == "nested_bullets":
                items = block.get("items", [])
                if not items:
                    continue
                list_start = cursor
                sub_ranges = []
                for item in items:
                    q_text = item["q"] + "\n"
                    requests.append(
                        {
                            "insertText": {
                                "location": {"index": cursor},
                                "text": q_text,
                            }
                        }
                    )
                    cursor += len(q_text)
                    rec_text = item["rec"] + "\n"
                    rec_start = cursor
                    requests.append(
                        {
                            "insertText": {
                                "location": {"index": cursor},
                                "text": rec_text,
                            }
                        }
                    )
                    cursor += len(rec_text)
                    rec_end = cursor
                    sub_ranges.append((rec_start, rec_end))
                list_end = cursor
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": {
                                "startIndex": list_start,
                                "endIndex": list_end,
                            },
                            "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                        }
                    }
                )
                for rec_start, rec_end in sub_ranges:
                    requests.append(
                        {
                            "updateParagraphStyle": {
                                "range": {
                                    "startIndex": rec_start,
                                    "endIndex": rec_end,
                                },
                                "paragraphStyle": {
                                    "indentStart": {
                                        "magnitude": 72,
                                        "unit": "PT",
                                    },
                                    "indentFirstLine": {
                                        "magnitude": 54,
                                        "unit": "PT",
                                    },
                                },
                                "fields": "indentStart,indentFirstLine",
                            }
                        }
                    )

            elif block_type == "table":
                t_headers = block.get("headers", [])
                t_rows = block.get("rows", [])
                if not t_headers:
                    continue
                num_cols = len(t_headers)
                num_rows = 1 + len(t_rows)

                requests.append(
                    {
                        "insertTable": {
                            "rows": num_rows,
                            "columns": num_cols,
                            "location": {"index": cursor},
                        }
                    }
                )
                if requests:
                    docs_service.documents().batchUpdate(
                        documentId=doc_id, body={"requests": requests}
                    ).execute()
                    requests = []

                doc_state = (
                    docs_service.documents()
                    .get(documentId=doc_id)
                    .execute()
                )
                table_element = None
                for elem in doc_state.get("body", {}).get("content", []):
                    if "table" in elem:
                        table_element = elem

                if table_element:
                    table = table_element["table"]
                    all_table_rows = [t_headers] + t_rows
                    cell_inserts = []
                    for ri, row_data in enumerate(all_table_rows):
                        if ri >= len(table.get("tableRows", [])):
                            break
                        table_row = table["tableRows"][ri]
                        for ci, cell_val in enumerate(row_data):
                            if ci >= len(
                                table_row.get("tableCells", [])
                            ):
                                break
                            cell = table_row["tableCells"][ci]
                            cell_content = cell.get("content", [])
                            if cell_content:
                                cell_idx = cell_content[0].get(
                                    "startIndex", 0
                                )
                                cell_text = str(cell_val)
                                if cell_text:
                                    cell_inserts.append(
                                        (cell_idx, cell_text)
                                    )

                    cell_inserts.sort(
                        key=lambda x: x[0], reverse=True
                    )
                    for cell_idx, cell_text in cell_inserts:
                        requests.append(
                            {
                                "insertText": {
                                    "location": {"index": cell_idx},
                                    "text": cell_text,
                                }
                            }
                        )
                    if requests:
                        docs_service.documents().batchUpdate(
                            documentId=doc_id,
                            body={"requests": requests},
                        ).execute()
                        requests = []

                    doc_state2 = (
                        docs_service.documents()
                        .get(documentId=doc_id)
                        .execute()
                    )
                    table_elem2 = None
                    for elem in doc_state2.get("body", {}).get(
                        "content", []
                    ):
                        if "table" in elem:
                            table_elem2 = elem
                    if table_elem2 and table_elem2["table"].get(
                        "tableRows"
                    ):
                        header_row = table_elem2["table"]["tableRows"][
                            0
                        ]
                        for hcell in header_row.get("tableCells", []):
                            for para in hcell.get("content", []):
                                si = para.get("startIndex", 0)
                                ei = para.get("endIndex", si)
                                if ei > si:
                                    requests.append(
                                        {
                                            "updateTextStyle": {
                                                "range": {
                                                    "startIndex": si,
                                                    "endIndex": ei,
                                                },
                                                "textStyle": {
                                                    "bold": True
                                                },
                                                "fields": "bold",
                                            }
                                        }
                                    )
                    if requests:
                        docs_service.documents().batchUpdate(
                            documentId=doc_id,
                            body={"requests": requests},
                        ).execute()
                        requests = []

                doc_state = (
                    docs_service.documents()
                    .get(documentId=doc_id)
                    .execute()
                )
                body_content = doc_state.get("body", {}).get(
                    "content", []
                )
                if body_content:
                    last_elem = body_content[-1]
                    cursor = last_elem.get("endIndex", cursor) - 1
                requests.append(
                    {
                        "insertText": {
                            "location": {"index": cursor},
                            "text": "\n",
                        }
                    }
                )
                cursor += 1

    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()


def main() -> None:
    """Create or update the Google Doc."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--update",
        metavar="DOC_ID",
        help="Update an existing Google Doc instead of creating new",
    )
    args = parser.parse_args()

    from cmo_agent.agents.docs import _normalize_sections
    from cmo_agent.google_auth import (
        ensure_drive_folder,
        get_google_credentials,
        move_file_to_folder,
        share_file_restricted,
    )

    oauth_path = (
        "/Users/nickshutwell/Desktop/CMO Agent/data/google-token.json"
    )
    SCOPES = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive.file",
    ]
    credentials = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path="",
        scopes=SCOPES,
    )
    if credentials is None:
        print("ERROR: Could not load Google credentials.")
        sys.exit(1)

    from googleapiclient.discovery import build

    docs_service = build("docs", "v1", credentials=credentials)
    drive_service = build("drive", "v3", credentials=credentials)

    structure = build_document_structure()
    title = structure["title"]
    sections = _normalize_sections(structure, skip_toc=False)

    if args.update:
        doc_id = args.update
        print(f"Updating existing Google Doc: {doc_id}")
        print(f"Sections: {len(sections)}")

        doc = docs_service.documents().get(documentId=doc_id).execute()
        body_content = doc.get("body", {}).get("content", [])
        if body_content:
            end_index = body_content[-1].get("endIndex", 2) - 1
            if end_index > 1:
                docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={
                        "requests": [
                            {
                                "deleteContentRange": {
                                    "range": {
                                        "startIndex": 1,
                                        "endIndex": end_index,
                                    }
                                }
                            }
                        ]
                    },
                ).execute()
                print("Cleared existing content")

        _render_content(docs_service, doc_id, sections)

        docs_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        print(f"\nGoogle Doc updated successfully!")
        print(f"URL: {docs_url}")

    else:
        print(f"Building Google Doc: {title}")
        print(f"Sections: {len(sections)}")

        doc = (
            docs_service.documents()
            .create(body={"title": title})
            .execute()
        )
        doc_id = doc["documentId"]
        print(f"Document created: {doc_id}")

        _render_content(docs_service, doc_id, sections)

        share_file_restricted(drive_service, doc_id)

        folder_id = ensure_drive_folder(drive_service)
        if folder_id:
            move_file_to_folder(drive_service, doc_id, folder_id)

        docs_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        print(f"\nGoogle Doc created successfully!")
        print(f"URL: {docs_url}")


if __name__ == "__main__":
    main()

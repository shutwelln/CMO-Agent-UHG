"""Create the Entity Setup Playbook for Saverwell Holdings, LLC & S2 Foundry LLC as a Google Doc.

Constructs the full playbook with 10 sections covering formation, protection,
maturity, operating agreements, privacy policies, terms of service, IP
assignment, tax setup, cost summary, and a 30-day checklist. Bypasses LLM
generation to ensure exact content fidelity.

Usage:
    python scripts/create_entity_setup_playbook.py              # create new
    python scripts/create_entity_setup_playbook.py --update ID  # update existing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

# ---------------------------------------------------------------------------
# Google Doc IDs for linked standalone documents
# ---------------------------------------------------------------------------

_SAVERWELL_PP_DOC_ID = "1Uy9o3hmXvNK36SZs9FMiAUGcLURd09gYoMgbTHwX3OI"
_SAVERWELL_TOS_DOC_ID = "1sLV33ZQwQo77j3kHQBLwD4_l4LBXgZYqjvQjfKtT9sA"
_SAVERWELL_OA_DOC_ID = "1jcreW2YE_G9Qx5R6R1BuIddtiSbgVExQdBowt25I3lM"
_S2_FOUNDRY_OA_DOC_ID = "1YPHG8WAdck3xuRlDbr5GXs3Xy6fRL1sabz-sZM8gGcQ"
_AGENT_TUNNEL_PP_DOC_ID = "11gk2PxdEamI9EE-9HueS2mO-n92uOd8ur5xMYcYdV2U"
_AGENT_TUNNEL_TOS_DOC_ID = "13kaRNqlFyYAFMrVIlmNrw5joEudFoWYrlXq8_fQYgJo"
_IP_ASSIGNMENT_DOC_ID = "1whUTHtyOXiNNUM-nuD_G33MsZU3cPLz3lwhRc7GhFBE"
_PLAYBOOK_DOC_ID = "1deW31Ph61LyKUPe51ehBTH2S4l5vwD4Ezv6UzrMGiDU"

_REGISTERED_AGENT_ADDRESS = (
    "2800 E. Enterprise Ave, STE 333, Appleton, WI 54913 (Resident Agents Inc.)"
)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _section_1_state_of_formation() -> dict:
    """Section 1: State of Formation - Recommendation."""
    return {
        "heading": "Section 1: State of Formation - Recommendation",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "Wisconsin. Here is why.",
            },
            {
                "type": "paragraph",
                "text": (
                    "You live and operate in Wisconsin. Forming in Wyoming "
                    "or Delaware means paying filing fees in BOTH states. "
                    "If you form in another state, you still need to "
                    "register as a foreign LLC in Wisconsin to do business "
                    "here, which costs $100 plus $40 per year on top of "
                    "the other state's fees."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "Wisconsin Articles of Organization cost $130 online. "
                    "The annual report is $25 per year. That is it."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "Wyoming and Delaware advantages (privacy, no state "
                    "income tax) do not help when your operations are in "
                    "Wisconsin anyway. Wisconsin taxes you on income earned "
                    "in Wisconsin regardless of where you form. Delaware's "
                    "business court advantage only matters if you are "
                    "raising venture capital or anticipating complex "
                    "corporate litigation."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "If you ever need to re-domesticate for fundraising or "
                    "acquisition, you can do that later. Do not pay for it "
                    "now."
                ),
            },
            {
                "type": "table",
                "headers": [
                    "Factor",
                    "Wisconsin",
                    "Wyoming",
                    "Delaware",
                ],
                "rows": [
                    [
                        "Formation fee",
                        "$130",
                        "$100 + $100 WI foreign reg",
                        "$90 + $100 WI foreign reg",
                    ],
                    [
                        "Annual report",
                        "$25",
                        "$60 + $40 WI annual",
                        "$300 + $40 WI annual",
                    ],
                    [
                        "State income tax",
                        "Yes (WI rates)",
                        "No state tax, but WI taxes WI income anyway",
                        "No state tax, but WI taxes WI income anyway",
                    ],
                    [
                        "Privacy",
                        "Members listed in annual report",
                        "Members not listed",
                        "Members not listed",
                    ],
                    [
                        "Verdict",
                        "Best choice",
                        "Unnecessary cost",
                        "Unnecessary cost",
                    ],
                ],
            },
        ],
    }


def _section_2_phase_1_foundation() -> list:
    """Section 2: Phase 1 - Foundation (Week 1-2)."""
    return [
        {
            "heading": "Section 2: Phase 1 - Foundation (Week 1-2)",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Everything in this section is a prerequisite for "
                        "operating. Sequenced by dependency. Do not skip "
                        "anything here."
                    ),
                },
            ],
        },
        # Day 1-2: Form both LLCs
        {
            "heading": "Day 1-2: Form Both LLCs",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Nick does this manually. About 15 minutes per entity.",
                },
                {
                    "type": "numbered_list",
                    "items": [
                        (
                            "Check name availability on the Wisconsin "
                            "Department of Financial Institutions (DFI) "
                            "CORPS system: "
                            "https://www.wdfi.org/apps/CorpSearch/Search.aspx"
                        ),
                        (
                            "Sign up for a registered agent service. "
                            "Recommended: wisconsinregisteredagent.net "
                            "($49 per year). This keeps your home address "
                            "off public filings. The registered agent "
                            "address is: " + _REGISTERED_AGENT_ADDRESS + "."
                        ),
                        (
                            "File Articles of Organization online at WI "
                            "OneStop: https://onestop.wi.gov/openmybusiness "
                            " - Cost: $130 per entity."
                        ),
                        (
                            "For Saverwell Holdings, LLC: single-member LLC. "
                            "Nick Shutwell as sole member and organizer. Use "
                            "the registered agent address for principal "
                            "office and organizer address."
                        ),
                        (
                            "For S2 Foundry LLC: multi-member LLC. "
                            "Nick Shutwell and jhaw ventures LLC (Justin "
                            "Shaw's Wyoming LLC) as members. Either can be "
                            "the organizer."
                        ),
                        "Download and save the filed Articles of Organization as PDF.",
                    ],
                },
            ],
        },
        # Day 2-3: Get EINs
        {
            "heading": "Day 2-3: Get EINs",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Nick does this manually. About 10 minutes per entity. "
                        "Free, immediate."
                    ),
                },
                {
                    "type": "numbered_list",
                    "items": [
                        (
                            "Apply at IRS.gov: "
                            "https://www.irs.gov/businesses/small-businesses-self-employed/"
                            "apply-for-an-employer-identification-number-ein-online"
                        ),
                        (
                            "Saverwell Holdings, LLC: Use Nick's SSN as the "
                            "responsible party. Entity type: single-member "
                            "LLC (disregarded entity)."
                        ),
                        (
                            "S2 Foundry LLC: Use Nick's SSN as the "
                            "responsible party (either member works, but "
                            "pick one). Entity type: multi-member LLC "
                            "(partnership)."
                        ),
                        (
                            "The EIN is issued immediately online. Save "
                            "the confirmation letter (CP 575) as PDF."
                        ),
                        (
                            "You need both EINs before opening bank "
                            "accounts."
                        ),
                    ],
                },
            ],
        },
        # Day 3-5: Operating Agreements
        {
            "heading": "Day 3-5: Operating Agreements",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Operating agreements are not filed with the state "
                        "but are essential internal governance documents. "
                        "Wisconsin does not require them, but banks, "
                        "partners, and insurance providers will ask for them."
                    ),
                },
                {
                    "type": "bullets",
                    "items": [
                        (
                            "Saverwell Holdings, LLC: A complete single-member "
                            "Operating Agreement draft is available as a "
                            "standalone Google Doc. Review it, fill in the "
                            "blanks, sign it, and keep it on file.\n"
                            "Link: https://docs.google.com/document/d/"
                            + _SAVERWELL_OA_DOC_ID + "/edit"
                        ),
                        (
                            "S2 Foundry LLC: A draft OA already exists "
                            "as a Google Doc (created from the Co-Founder "
                            "Discussion Guide). Section 6 of this playbook "
                            "lists the specific blanks that need to be "
                            "filled before Nick and Justin sign it.\n"
                            "Link: https://docs.google.com/document/d/"
                            + _S2_FOUNDRY_OA_DOC_ID + "/edit"
                        ),
                    ],
                },
            ],
        },
        # Day 5-7: Bank Accounts
        {
            "heading": "Day 5-7: Bank Accounts",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Nick does this. About 1 hour per account. "
                        "Requires EIN plus Articles of Organization."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "Open a separate business checking account for each "
                        "LLC. Never commingle personal and business funds. "
                        "Never commingle funds between the two LLCs."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": "Recommended banks (all no-fee for business checking):",
                },
                {
                    "type": "bullets",
                    "items": [
                        (
                            "Mercury (https://mercury.com) - Best for "
                            "startups. No fees, excellent UI, integrates "
                            "with QuickBooks. Fully online."
                        ),
                        (
                            "Relay (https://relay.com) - Also no fees, "
                            "good for separating expenses into buckets. "
                            "Fully online."
                        ),
                        (
                            "Local WI credit union - Fine if you prefer "
                            "in-person banking. Summit Credit Union and "
                            "UW Credit Union are solid options."
                        ),
                    ],
                },
                {
                    "type": "paragraph",
                    "text": (
                        "Get a debit card for each account. Consider a "
                        "business credit card for each entity after a few "
                        "months of activity to build business credit."
                    ),
                },
            ],
        },
        # Day 5-7: Privacy Policies & Terms of Service
        {
            "heading": "Day 5-7: Privacy Policies & Terms of Service",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Required before collecting any user data or "
                        "accepting payments. All four documents have been "
                        "produced as standalone Google Docs. Nick and Justin "
                        "copy the text from these docs and paste them onto "
                        "the respective sites."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": "Saverwell Holdings, LLC:",
                },
                {
                    "type": "bullets",
                    "items": [
                        (
                            "Privacy Policy: "
                            "https://docs.google.com/document/d/"
                            + _SAVERWELL_PP_DOC_ID + "/edit"
                        ),
                        (
                            "Terms of Service: "
                            "https://docs.google.com/document/d/"
                            + _SAVERWELL_TOS_DOC_ID + "/edit"
                        ),
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "Agent Tunnel (S2 Foundry LLC):",
                },
                {
                    "type": "bullets",
                    "items": [
                        (
                            "Privacy Policy: "
                            "https://docs.google.com/document/d/"
                            + _AGENT_TUNNEL_PP_DOC_ID + "/edit"
                        ),
                        (
                            "Terms of Service: "
                            "https://docs.google.com/document/d/"
                            + _AGENT_TUNNEL_TOS_DOC_ID + "/edit"
                        ),
                    ],
                },
            ],
        },
    ]


def _section_3_phase_2_protection() -> list:
    """Section 3: Phase 2 - Protection (Month 1-2)."""
    return [
        {
            "heading": "Section 3: Phase 2 - Protection (Month 1-2)",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Important but does not block Day 1 operations. "
                        "Do these within the first 30-60 days."
                    ),
                },
            ],
        },
        # Insurance
        {
            "heading": "Priority 1: Insurance (Do Within 30 Days)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Saverwell Holdings, LLC - Risk Analysis",
                },
                {
                    "type": "table",
                    "headers": ["Risk", "Coverage Needed", "Recommended Limit"],
                    "rows": [
                        [
                            "Senior acts on Medicare/fraud guide advice that goes wrong",
                            "Professional Liability / E&O (Errors & Omissions)",
                            "$1,000,000",
                        ],
                        [
                            "250K email list or user data (ZIPs, emails, UTM, Customer.io) breached",
                            "Cyber Liability",
                            "$1,000,000",
                        ],
                        [
                            "Standard business operations (someone trips at your office, etc.)",
                            "General Liability",
                            "$1,000,000 / $2,000,000",
                        ],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": (
                        "Recommended bundle: Business Owner's Policy (BOP). "
                        "A BOP bundles General Liability, E&O, and Cyber "
                        "into one policy at a discount. Estimated cost: "
                        "$1,500 to $3,000 per year."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": "S2 Foundry LLC / Agent Tunnel - Risk Analysis",
                },
                {
                    "type": "table",
                    "headers": ["Risk", "Coverage Needed", "Recommended Limit"],
                    "rows": [
                        [
                            "Cloudflare tunnel vulnerability exposes customer dev machine",
                            "Cyber Liability + Tech E&O",
                            "$1,000,000 each",
                        ],
                        [
                            "App downtime causes customer to miss a deadline",
                            "Technology Errors & Omissions",
                            "$1,000,000",
                        ],
                        [
                            "Standard business operations",
                            "General Liability",
                            "$1,000,000 / $2,000,000",
                        ],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": (
                        "Recommended bundle: BOP with Tech E&O rider. "
                        "Estimated cost: $2,000 to $4,000 per year."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "Strategy: Use one broker for both entities. "
                        "Bundle discount. Tech-focused brokers to contact:"
                    ),
                },
                {
                    "type": "bullets",
                    "items": [
                        "Embroker (https://embroker.com) - Tech-focused, fast online quotes",
                        "Vouch (https://vouch.us) - Built for startups",
                        "Hartford (https://thehartford.com) - Traditional, solid for small business",
                        "A local WI commercial insurance broker - can shop multiple carriers",
                    ],
                },
            ],
        },
        # Insurance broker talking points
        {
            "heading": "Insurance Broker Talking Points (Ready to Use)",
            "level": 3,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Use these when you call or email a broker. "
                        "Copy/paste or read verbatim."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "\"I have two LLCs and I am looking for insurance "
                        "for both. I would like to get quotes and explore "
                        "any multi-policy discount.\""
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "\"Entity 1: Saverwell Holdings, LLC. It is a consumer "
                        "platform focused on seniors. We publish "
                        "educational content about Medicare, senior "
                        "discounts, and fraud protection. Revenue comes "
                        "from affiliate partnerships, sponsored content, "
                        "and lead generation. We collect personal data "
                        "including email addresses, ZIP codes, and cookies. "
                        "We use Customer.io for email marketing and GA4 "
                        "for analytics. We expect to grow to 250,000 or "
                        "more email subscribers. We need General Liability, "
                        "Professional Liability / E&O (because people act "
                        "on our financial and health content), and Cyber "
                        "Liability. Looking for $1 million limits on each. "
                        "Ideally a BOP bundle.\""
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "\"Entity 2: S2 Foundry LLC. It is a two-member "
                        "LLC that builds software. Our first product is "
                        "Agent Tunnel, a $15 per month Mac app that "
                        "manages Cloudflare tunnels for developers. We "
                        "process payments through LemonSqueezy. The product "
                        "interacts with customers' local dev environments. "
                        "We need General Liability, Tech E&O (software "
                        "errors, downtime), and Cyber Liability. Looking "
                        "for $1 million limits on each. Ideally a BOP "
                        "with Tech E&O.\""
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "\"Do you offer any multi-policy discount for "
                        "insuring both entities with one broker?\""
                    ),
                },
            ],
        },
        # Accounting
        {
            "heading": "Priority 2: Accounting Setup (Do Within 30 Days)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Nick does this. About 30 minutes to set up."
                    ),
                },
                {
                    "type": "numbered_list",
                    "items": [
                        (
                            "Sign up for QuickBooks Simple Start ($30 per "
                            "month) for each entity, or one QuickBooks "
                            "account with two companies. "
                            "https://quickbooks.intuit.com"
                        ),
                        (
                            "Connect each LLC's bank account to its "
                            "QuickBooks company."
                        ),
                        (
                            "Set up a monthly close routine: reconcile "
                            "bank statements, categorize expenses, review "
                            "profit and loss. Block 1 hour on the first "
                            "Monday of each month."
                        ),
                        (
                            "S2 Foundry: Track by product line (Agent "
                            "Tunnel vs. future products) using QuickBooks "
                            "classes or tags."
                        ),
                        (
                            "Saverwell: Track by revenue source (affiliate, "
                            "sponsored, lead-gen) using QuickBooks classes "
                            "or tags."
                        ),
                        (
                            "Alternative: Bench (https://bench.co) or "
                            "Pilot (https://pilot.com) if you want "
                            "hands-off bookkeeping. $200-$400 per month "
                            "per entity, but they do the monthly close "
                            "for you."
                        ),
                    ],
                },
            ],
        },
        # LemonSqueezy Migration
        {
            "heading": "Priority 3: LemonSqueezy Migration (Do Within 30 Days)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Agent Tunnel's LemonSqueezy account is currently under "
                        "Justin (personally or via Justin Shaw Ventures). "
                        "It needs to move to S2 Foundry LLC."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "Important: Until migration is complete, Agent "
                        "Tunnel revenue is Justin's income, not S2 "
                        "Foundry's. Any pre-formation revenue stays with "
                        "Justin regardless."
                    ),
                },
                {
                    "type": "numbered_list",
                    "items": [
                        "Prerequisite: S2 Foundry bank account is open and verified.",
                        (
                            "Create a new LemonSqueezy account under S2 Foundry "
                            "LLC. Use the S2 Foundry EIN, legal name, and "
                            "bank account. https://lemonsqueezy.com"
                        ),
                        (
                            "Recreate product and price objects in the new "
                            "LemonSqueezy account (Agent Tunnel, $15 per month)."
                        ),
                        (
                            "Contact LemonSqueezy Support about bulk subscription "
                            "migration. They may be able to help move "
                            "active subscriptions to the new account. "
                            "If not, you will need to ask existing "
                            "subscribers to re-subscribe."
                        ),
                        (
                            "Update the agenttunnel.app codebase with the "
                            "new LemonSqueezy API keys."
                        ),
                        (
                            "Update any n8n webhook URLs if the LemonSqueezy "
                            "endpoint changes."
                        ),
                        (
                            "Verify all flows work end to end: new signup, "
                            "trial start, trial to paid conversion, "
                            "subscription renewal, cancellation."
                        ),
                        "Deactivate the old LemonSqueezy account once all subscriptions are migrated.",
                    ],
                },
            ],
        },
        # IP Assignment
        {
            "heading": "Priority 4: IP Assignment (Do Within 30 Days)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Justin's pre-existing Agent Tunnel code needs to "
                        "be formally assigned to S2 Foundry LLC. The "
                        "Operating Agreement says Agent Tunnel is a "
                        "Company asset, but an IP Assignment Agreement "
                        "makes it explicit and legally clean."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "A complete IP Assignment Agreement template has been "
                        "produced as a standalone Google Doc. Fill in the "
                        "blanks, both parties sign, keep on file.\n"
                        "Link: https://docs.google.com/document/d/"
                        + _IP_ASSIGNMENT_DOC_ID + "/edit"
                    ),
                },
            ],
        },
    ]


def _section_4_phase_3_maturity() -> list:
    """Section 4: Phase 3 - Maturity (Month 3+)."""
    return [
        {
            "heading": "Section 4: Phase 3 - Maturity (Month 3+)",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Layer these on as revenue grows and complexity "
                        "increases. None of these are urgent at formation."
                    ),
                },
            ],
        },
        {
            "heading": "When Net Profit Exceeds $40K-$50K Per Year (Either Entity)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Evaluate S-Corp election. An S-Corp lets you "
                        "split income into salary (subject to "
                        "self-employment tax) and distributions (not "
                        "subject to SE tax). The savings only make sense "
                        "above roughly $40K-$50K in net profit because "
                        "you need to pay yourself a \"reasonable salary\" "
                        "and the payroll overhead eats into savings below "
                        "that threshold."
                    ),
                },
                {
                    "type": "bullets",
                    "items": [
                        (
                            "Saverwell: File Form 2553 with the IRS. Set a "
                            "reasonable salary. Remaining profit flows as "
                            "distributions. Relatively simple for a "
                            "single-member LLC."
                        ),
                        (
                            "S2 Foundry: More complex with two members. "
                            "Both Nick and Justin would need reasonable "
                            "salaries. Consult a CPA before electing S-Corp "
                            "for a partnership."
                        ),
                    ],
                },
            ],
        },
        {
            "heading": "When Hiring Contractors",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        (
                            "Contractor agreement with IP assignment clause "
                            "(ensures any work they do belongs to the LLC, "
                            "not the contractor). Claude can produce a "
                            "template when needed."
                        ),
                        (
                            "Mutual NDA template for sensitive work. Claude "
                            "can produce when needed."
                        ),
                        "Issue 1099-NEC forms for any contractor paid $600 or more per year.",
                    ],
                },
            ],
        },
        {
            "heading": "When S2 Foundry Reaches $5K+ MRR (Monthly Recurring Revenue)",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        (
                            "Consider Directors & Officers (D&O) insurance. "
                            "Protects both members' personal assets from "
                            "partnership decisions."
                        ),
                        (
                            "Evaluate whether the $2,500 unilateral "
                            "spending threshold in the Operating Agreement "
                            "needs to increase."
                        ),
                        "Review pricing strategy and whether $15 per month is still right.",
                    ],
                },
            ],
        },
        {
            "heading": "When Saverwell Has Enterprise or B2B Partnerships",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        "Affiliate/partner agreement template (Claude can produce)",
                        "More robust data processing terms for enterprise partners",
                        "Consider media liability insurance if publishing sponsored content at scale",
                    ],
                },
            ],
        },
        {
            "heading": "When S2 Foundry Has Enterprise Customers",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        (
                            "Data Processing Agreement (DPA) template for "
                            "enterprise customers"
                        ),
                        (
                            "SaaS Service Level Agreement (SLA) defining "
                            "uptime commitments and support response times"
                        ),
                        (
                            "SOC 2 readiness evaluation. SOC 2 Type II "
                            "certification costs $15K-$50K but enterprise "
                            "customers may require it."
                        ),
                    ],
                },
            ],
        },
    ]


def _section_5_saverwell_oa() -> list:
    """Section 5: Saverwell Holdings, LLC - Single-Member Operating Agreement."""
    return [
        {
            "heading": (
                "Section 5: Saverwell Holdings, LLC - Single-Member Operating Agreement"
            ),
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "The complete Saverwell Holdings, LLC single-member "
                        "Operating Agreement is available as a standalone "
                        "Google Doc. Review it, fill in the blanks, sign it, "
                        "and keep it on file."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "Link: https://docs.google.com/document/d/"
                        + _SAVERWELL_OA_DOC_ID + "/edit"
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "IMPORTANT: This is a draft prepared as a working "
                        "starting point. Consider having an attorney "
                        "review before signing, though a single-member OA "
                        "is relatively low risk."
                    ),
                },
            ],
        },
    ]


def _section_6_s2_foundry_checklist() -> dict:
    """Section 6: S2 Foundry LLC - Key Decisions Checklist."""
    return {
        "heading": "Section 6: S2 Foundry LLC - Key Decisions Checklist",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The S2 Foundry Operating Agreement draft already "
                    "exists as a Google Doc (created from the Co-Founder "
                    "Discussion Guide). Before Nick and Justin sign it, "
                    "the following blanks need to be filled in.\n"
                    "Link: https://docs.google.com/document/d/"
                    + _S2_FOUNDRY_OA_DOC_ID + "/edit"
                ),
            },
            {
                "type": "paragraph",
                "text": "Blanks to Complete Before Signing:",
            },
            {
                "type": "bullets",
                "items": [
                    (
                        "[ ] State name throughout the document (currently "
                        "\"[STATE]\" placeholder) - Replace with \"Wisconsin\""
                    ),
                    (
                        "[ ] Registered agent name and address "
                        "(Article I, Section 1.5)"
                    ),
                    (
                        "[ ] Principal office address "
                        "(Article I, Section 1.6)"
                    ),
                    (
                        "[ ] Nick's capital contribution description "
                        "(Article III) - What is Nick contributing? "
                        "Cash? Services? IP?"
                    ),
                    (
                        "[ ] Justin's capital contribution description "
                        "(Article III) - Agent Tunnel IP plus any cash "
                        "or services. Note: Justin's membership is through "
                        "jhaw ventures LLC (his Wyoming LLC)."
                    ),
                    (
                        "[ ] Date of agreement - Use the same date as "
                        "or after the Articles of Organization filing date"
                    ),
                    (
                        "[ ] Whether to have an attorney review before "
                        "signing - Recommended for a two-member LLC. "
                        "Budget $1,000 to $2,000."
                    ),
                ],
            },
            {
                "type": "paragraph",
                "text": "Additional Considerations:",
            },
            {
                "type": "bullets",
                "items": [
                    (
                        "The IP Assignment Agreement (Section 3, "
                        "Priority 4 of this playbook) should be signed "
                        "on the same day as the Operating Agreement"
                    ),
                    (
                        "Both documents should reference the same "
                        "formation date"
                    ),
                    (
                        "Nick and Justin should each keep a signed copy "
                        "of both documents"
                    ),
                ],
            },
        ],
    }


def _section_7_tax_setup() -> dict:
    """Section 7: Tax Setup."""
    return {
        "heading": "Section 7: Tax Setup",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "Saverwell Holdings, LLC - Tax Treatment",
            },
            {
                "type": "bullets",
                "items": [
                    (
                        "Disregarded entity for tax purposes. This is the "
                        "IRS default for a single-member LLC. No election "
                        "needed."
                    ),
                    (
                        "All income and expenses reported on Schedule C "
                        "of Nick's personal Form 1040."
                    ),
                    (
                        "Self-employment tax (Social Security + Medicare) "
                        "applies to net profit. Pay this via quarterly "
                        "estimated taxes when revenue materializes."
                    ),
                    (
                        "Wisconsin state income tax: file Schedule C "
                        "income on Wisconsin Form 1."
                    ),
                    "No separate federal or state return for the LLC itself.",
                ],
            },
            {
                "type": "paragraph",
                "text": "S2 Foundry LLC - Tax Treatment",
            },
            {
                "type": "bullets",
                "items": [
                    (
                        "Partnership for tax purposes. This is the IRS "
                        "default for a multi-member LLC. No election needed."
                    ),
                    (
                        "File Form 1065 (U.S. Return of Partnership "
                        "Income) annually. Due March 15."
                    ),
                    (
                        "Each member receives a Schedule K-1 showing "
                        "their 50% share of income, deductions, and credits."
                    ),
                    (
                        "Each member reports their K-1 income on their "
                        "personal return."
                    ),
                    (
                        "Nick is the Tax Matters Partner (already in the "
                        "Operating Agreement, Article XI). Nick handles "
                        "IRS correspondence on behalf of the partnership."
                    ),
                    "Self-employment tax applies to each member's share of net profit.",
                    (
                        "Wisconsin: File Form 3, Wisconsin Partnership "
                        "Return, annually."
                    ),
                ],
            },
            {
                "type": "paragraph",
                "text": "Agent Tunnel Pre-Formation Revenue",
            },
            {
                "type": "bullets",
                "items": [
                    (
                        "All revenue generated by Agent Tunnel before S2 "
                        "Foundry's formation date belongs to Justin (or "
                        "Justin Shaw Ventures)."
                    ),
                    (
                        "S2 Foundry's partnership tax reporting starts on "
                        "the formation date. Do not include pre-formation "
                        "revenue."
                    ),
                    (
                        "Justin reports pre-formation Agent Tunnel income "
                        "on his personal return (or his existing entity's "
                        "return)."
                    ),
                ],
            },
            {
                "type": "paragraph",
                "text": "Quarterly Estimated Taxes",
            },
            {
                "type": "bullets",
                "items": [
                    (
                        "Start paying quarterly estimated taxes when "
                        "either entity has revenue. Due dates: April 15, "
                        "June 15, September 15, January 15."
                    ),
                    (
                        "Use IRS Form 1040-ES to calculate and pay "
                        "federal estimates."
                    ),
                    (
                        "Use Wisconsin Form 1-ES for state estimates."
                    ),
                    (
                        "Rule of thumb: set aside 30% of net profit for "
                        "taxes (covers federal income tax + SE tax + "
                        "state income tax)."
                    ),
                ],
            },
            {
                "type": "paragraph",
                "text": "CPA Recommendation",
            },
            {
                "type": "paragraph",
                "text": (
                    "Find one CPA for both entities. You want someone "
                    "familiar with pass-through structures (LLCs, "
                    "partnerships). They will handle the Form 1065 for "
                    "S2 Foundry and can advise on the S-Corp election "
                    "when the time comes."
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "Local WI CPA: Best for state-specific questions. Ask for referrals.",
                    (
                        "Bench (https://bench.co): Handles bookkeeping "
                        "and can connect you with a CPA for tax filing."
                    ),
                    (
                        "Pilot (https://pilot.com): Similar to Bench, "
                        "more tech-focused."
                    ),
                    "Budget: $500 to $1,500 per entity per year for tax prep.",
                ],
            },
        ],
    }


def _section_8_ip_ownership() -> dict:
    """Section 8: IP Ownership Summary."""
    return {
        "heading": "Section 8: IP Ownership Summary",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Clean, non-overlapping boundaries. No shared IP "
                    "between entities."
                ),
            },
            {
                "type": "table",
                "headers": ["Owner", "Assets"],
                "rows": [
                    [
                        "Saverwell Holdings, LLC",
                        (
                            "Saverwell brand, saverwell.com domain, all "
                            "website content, merchant discount database, "
                            "user data (email lists, behavioral data), "
                            "all Saverwell-related IP"
                        ),
                    ],
                    [
                        "S2 Foundry LLC",
                        (
                            "Agent Tunnel (post-assignment from Justin), "
                            "agenttunnel.app domain, all future products "
                            "built under S2 Foundry"
                        ),
                    ],
                    [
                        "Nick (personally)",
                        (
                            "CMO Agent system (this AI marketing "
                            "automation codebase). Not assigned to either "
                            "LLC unless Nick chooses to do so later."
                        ),
                    ],
                    [
                        "Justin (personally)",
                        (
                            "Justin Shaw Ventures and any side projects "
                            "not related to S2 Foundry"
                        ),
                    ],
                ],
            },
            {
                "type": "paragraph",
                "text": "Key Points:",
            },
            {
                "type": "bullets",
                "items": [
                    (
                        "Saverwell and S2 Foundry are completely "
                        "independent. They do not share revenue, "
                        "expenses, IP, or bank accounts."
                    ),
                    (
                        "Nick wears two hats but keeps them separate. "
                        "Saverwell work is Saverwell. S2 Foundry work is "
                        "S2 Foundry."
                    ),
                    (
                        "The CMO Agent codebase stays with Nick "
                        "personally. If Nick uses it for Saverwell "
                        "operations, that is fine, but the IP itself is "
                        "not a Saverwell asset."
                    ),
                    (
                        "If Nick ever wants to assign the CMO Agent to "
                        "an entity, that is a future decision. No need "
                        "to decide now."
                    ),
                ],
            },
        ],
    }


def _section_9_cost_summary() -> dict:
    """Section 9: Total Cost Summary."""
    return {
        "heading": "Section 9: Total Cost Summary",
        "level": 1,
        "content": [
            {
                "type": "table",
                "headers": ["Item", "Saverwell", "S2 Foundry", "Total"],
                "rows": [
                    [
                        "WI Articles of Organization",
                        "$130",
                        "$130",
                        "$260",
                    ],
                    ["EIN", "$0", "$0", "$0"],
                    [
                        "Registered Agent (wisconsinregisteredagent.net)",
                        "$49/yr",
                        "$49/yr",
                        "$98/yr",
                    ],
                    ["Bank Accounts", "$0", "$0", "$0"],
                    [
                        "Insurance (annual, Phase 2)",
                        "$1,500-$3,000",
                        "$2,000-$4,000",
                        "$3,500-$7,000",
                    ],
                    [
                        "QuickBooks (annual, Phase 2)",
                        "$360",
                        "$360",
                        "$720",
                    ],
                    [
                        "Attorney OA Review (optional)",
                        "$500-$1,000",
                        "$1,000-$2,000",
                        "$1,500-$3,000",
                    ],
                    [
                        "WI Annual Report (annual)",
                        "$25",
                        "$25",
                        "$50",
                    ],
                ],
            },
            {
                "type": "paragraph",
                "text": "Summary:",
            },
            {
                "type": "bullets",
                "items": [
                    (
                        "Minimum to start (Phase 1 only): $358 total "
                        "($130 filing + $49 registered agent per entity)"
                    ),
                    (
                        "Year 1 with Phase 2 (insurance + accounting): "
                        "$4,628 to $10,868 total"
                    ),
                    (
                        "The only money you spend today is $358 for two "
                        "LLC filings and two registered agent signups. "
                        "Everything else phases in over 30-90 days."
                    ),
                ],
            },
        ],
    }


def _section_10_checklist() -> list:
    """Section 10: First 30 Days Checklist."""
    return [
        {
            "heading": "Section 10: First 30 Days Checklist",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Week-by-week with owner assignments and time "
                        "estimates. Check off items as you complete them."
                    ),
                },
            ],
        },
        {
            "heading": "Week 1",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        (
                            "[ ] Check name availability for both LLCs on "
                            "WI DFI CORPS (Nick, 10 min)"
                        ),
                        (
                            "[ ] File Saverwell Holdings, LLC Articles of "
                            "Organization online (Nick, 15 min, $130)"
                        ),
                        (
                            "[ ] File S2 Foundry LLC Articles of "
                            "Organization online (Nick, 15 min, $130)"
                        ),
                        (
                            "[ ] Apply for Saverwell Holdings, LLC EIN at IRS.gov "
                            "(Nick, 10 min, free)"
                        ),
                        (
                            "[ ] Apply for S2 Foundry LLC EIN at IRS.gov "
                            "(Nick, 10 min, free)"
                        ),
                        (
                            "[ ] Save Articles of Organization and EIN "
                            "confirmation letters as PDFs (Nick, 5 min)"
                        ),
                    ],
                },
            ],
        },
        {
            "heading": "Week 2",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        (
                            "[ ] Open Saverwell Holdings, LLC business checking "
                            "account (Nick, 1 hour)"
                        ),
                        (
                            "[ ] Open S2 Foundry LLC business checking "
                            "account (Nick, 1 hour)"
                        ),
                        (
                            "[ ] Review and sign Saverwell single-member "
                            "OA (Nick, 30 min)"
                        ),
                        (
                            "[ ] Complete S2 Foundry OA blanks with Justin "
                            "(Nick + Justin, 1 hour)"
                        ),
                        (
                            "[ ] Sign S2 Foundry OA (Nick + Justin, 15 min)"
                        ),
                        (
                            "[ ] Sign IP Assignment Agreement for Agent "
                            "Tunnel (Nick + Justin, 15 min)"
                        ),
                        (
                            "[ ] Post Saverwell Privacy Policy and Terms "
                            "of Service on saverwell.com (Nick, 30 min)"
                        ),
                        (
                            "[ ] Post Agent Tunnel Privacy Policy and "
                            "Terms of Service on agenttunnel.app "
                            "(Justin, 30 min)"
                        ),
                    ],
                },
            ],
        },
        {
            "heading": "Week 3",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        (
                            "[ ] Set up QuickBooks for both entities "
                            "(Nick, 30 min)"
                        ),
                        (
                            "[ ] Connect bank accounts to QuickBooks "
                            "(Nick, 15 min)"
                        ),
                        (
                            "[ ] Contact insurance broker with talking "
                            "points (Nick, 1 phone call, 30 min)"
                        ),
                        (
                            "[ ] Create new LemonSqueezy account under S2 "
                            "Foundry LLC (Nick + Justin, 30 min)"
                        ),
                        (
                            "[ ] Begin LemonSqueezy subscription migration "
                            "process (Justin, 1-2 hours)"
                        ),
                    ],
                },
            ],
        },
        {
            "heading": "Week 4",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        (
                            "[ ] Review and select insurance quotes "
                            "(Nick, 30 min)"
                        ),
                        (
                            "[ ] Complete LemonSqueezy migration and verify "
                            "all flows (Justin, 1 hour)"
                        ),
                        (
                            "[ ] Update agenttunnel.app LemonSqueezy API keys "
                            "(Justin, 30 min)"
                        ),
                        (
                            "[ ] Deactivate old LemonSqueezy account "
                            "(Justin, 15 min)"
                        ),
                        (
                            "[ ] Find and contact a CPA for both entities "
                            "(Nick, 1 hour)"
                        ),
                        (
                            "[ ] First monthly bookkeeping close in "
                            "QuickBooks (Nick, 1 hour)"
                        ),
                    ],
                },
            ],
        },
        {
            "heading": "Ongoing (Monthly)",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        "[ ] Monthly QuickBooks reconciliation for both entities (1 hour)",
                        "[ ] Review and categorize expenses",
                        "[ ] Pay quarterly estimated taxes when revenue materializes",
                        (
                            "[ ] File WI annual reports when due ($25 each, "
                            "due by the quarter anniversary of formation)"
                        ),
                    ],
                },
            ],
        },
    ]


# ---------------------------------------------------------------------------
# Main document builder
# ---------------------------------------------------------------------------


def build_document_structure() -> dict:
    """Build the complete Entity Setup Playbook document structure."""
    sections = []

    # Intro
    sections.append(
        {
            "heading": "",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "ENTITY SETUP PLAYBOOK\n"
                        "Saverwell Holdings, LLC & S2 Foundry LLC"
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "This playbook covers everything needed to form "
                        "and operate two independent Wisconsin LLCs. It "
                        "is organized into three phases so you only do "
                        "what is necessary right now and layer on "
                        "protections as the businesses grow."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "Phase 1 (Foundation): Must-haves before "
                        "operating. Total cost: $358. Total time: a few "
                        "hours of manual work.\n"
                        "Phase 2 (Protection): Insurance, accounting, "
                        "legal basics. Do within 30-60 days.\n"
                        "Phase 3 (Maturity): Optimization as revenue "
                        "grows."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "Saverwell Holdings, LLC: Single-member (Nick). Consumer "
                        "platform for seniors - discounts, fraud "
                        "protection, educational guides. Revenue: "
                        "affiliate, sponsored, lead-gen. Pre-launch.\n\n"
                        "S2 Foundry LLC: Two-member 50/50 (Nick Shutwell "
                        "+ jhaw ventures LLC). AI tools and software. First product: "
                        "Agent Tunnel (Mac app, $15/mo SaaS, live at "
                        "agenttunnel.app)."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "These are completely independent entities. No "
                        "shared revenue, expenses, IP, or bank accounts."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "This playbook is also available as a Google Doc: "
                        "https://docs.google.com/document/d/"
                        + _PLAYBOOK_DOC_ID + "/edit"
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "DISCLAIMER: This playbook is for informational "
                        "and planning purposes. It is not legal or tax "
                        "advice. Consult a licensed attorney and CPA for "
                        "advice specific to your situation."
                    ),
                },
            ],
        }
    )

    # Section 1
    sections.append(_section_1_state_of_formation())

    # Section 2
    sections.extend(_section_2_phase_1_foundation())

    # Section 3
    sections.extend(_section_3_phase_2_protection())

    # Section 4
    sections.extend(_section_4_phase_3_maturity())

    # Section 5
    sections.extend(_section_5_saverwell_oa())

    # Section 6
    sections.append(_section_6_s2_foundry_checklist())

    # Section 7
    sections.append(_section_7_tax_setup())

    # Section 8
    sections.append(_section_8_ip_ownership())

    # Section 9
    sections.append(_section_9_cost_summary())

    # Section 10
    sections.extend(_section_10_checklist())

    return {
        "title": (
            "Entity Setup Playbook - Saverwell Holdings, LLC & S2 Foundry LLC"
        ),
        "sections": sections,
    }


# ---------------------------------------------------------------------------
# Google Doc renderer (reused pattern from other scripts)
# ---------------------------------------------------------------------------


def _render_content(docs_service, doc_id: str, sections: list) -> None:
    """Render sections into the Google Doc body."""
    requests: list = []
    cursor = 1

    def _heading_style(level: int) -> str:
        return {
            1: "HEADING_1",
            2: "HEADING_2",
            3: "HEADING_3",
            4: "HEADING_4",
        }.get(level, "HEADING_1")

    for section in sections:
        heading = section.get("heading", "")
        level = section.get("level", 1)
        content_blocks = section.get("content", [])

        # Insert heading
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

        # Insert content blocks
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
                for rs, re in sub_ranges:
                    requests.append(
                        {
                            "updateParagraphStyle": {
                                "range": {
                                    "startIndex": rs,
                                    "endIndex": re,
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
                # Flush pending requests before table
                if requests:
                    docs_service.documents().batchUpdate(
                        documentId=doc_id,
                        body={"requests": requests},
                    ).execute()
                    requests = []

                # Read doc state to find table cell indices
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

                    # Bold header row
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
                        header_row = table_elem2["table"]["tableRows"][0]
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

                # Update cursor after table
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

    # Flush remaining requests
    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Create or update the Google Doc."""
    parser = argparse.ArgumentParser(
        description="Create the Entity Setup Playbook Google Doc"
    )
    parser.add_argument(
        "--update",
        metavar="DOC_ID",
        help="Update an existing Google Doc instead of creating a new one",
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
        # -- Update existing document --------------------------------------
        doc_id = args.update
        print(f"Updating existing Google Doc: {doc_id}")
        print(f"Sections: {len(sections)}")

        # Clear existing body content
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
        # -- Create new document -------------------------------------------
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

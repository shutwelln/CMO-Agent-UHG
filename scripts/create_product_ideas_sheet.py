"""Create a Google Sheet with all 30 Saverwell product ideas for tracking.

Columns: Idea Name, Idea Description, Status, Category
Two tabs: "Product Ideas" (all 30 rows) and "Priority Matrix" (summary reference).
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

OAUTH_TOKEN_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'google-token.json'
)
SHARE_EMAIL = 'nick@saverwell.com'


# ── The 30 Product Ideas ─────────────────────────────────────────────────────

STATUS_NOT_STARTED = "Not Started"
STATUS_IN_PROGRESS = "In Progress"
STATUS_BUILT = "Built"

IDEAS = [
    # --- Original 10 (from product_roadmap_ideas.md) ---
    {
        "name": '"Senior Day" SMS/Push Reminder System',
        "desc": (
            "Users opt into weekly SMS reminders for day-specific senior discounts "
            "near them. 8,762 discounts include day-of-week data (Senior Tuesdays at "
            "Kroger, 55+ Wednesdays at Ross). Nobody else offers this. High stickiness, "
            "habitual weekly engagement, and real word-of-mouth driver."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Email/Retention",
    },
    {
        "name": "Affiliate Revenue Layer",
        "desc": (
            "Add affiliate links to 156 merchant pages and 48 guide articles. "
            "Medical alert systems, hearing aids, and cell phone plans are highest-commission "
            "verticals ($75-$300 per conversion). GA4 affiliateClick event is defined but "
            "not yet wired. Fastest path to revenue with content already indexed."
        ),
        "status": STATUS_IN_PROGRESS,
        "category": "Revenue",
    },
    {
        "name": '"Money Left on the Table" Interactive Calculator',
        "desc": (
            "User enters 5 most-shopped stores and ZIP code. Calculator cross-references "
            "the database and shows estimated annual savings. Generates a shareable savings "
            "report card. Strong viral mechanics, email capture hook, and validates "
            "Saverwell's value prop in actual dollars."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Tools",
    },
    {
        "name": "Scam Alert Real-Time Feed + Push Notifications",
        "desc": (
            "Upgrade static protection articles to a live, continuously-updated scam alert "
            "feed. Users subscribe to area-specific alerts. Sourced from Reddit monitoring, "
            "FTC complaint data, and Google Alerts. Creates a reason to return even when "
            "users are not shopping."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Community",
    },
    {
        "name": "Medicare Open Enrollment Hub (Seasonal)",
        "desc": (
            "Time-boxed hub for Oct 15 - Dec 7 Medicare AEP. Enrollment checklist, deadline "
            "countdown, plan comparison frameworks, and 48 guides surfaced as a structured "
            "walkthrough. Medicare keywords drive 100K+ monthly searches at peak. Insurance "
            "lead gen potential is $20-$200 per lead. Build once, activate annually."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Seasonal",
    },
    {
        "name": 'Weekly Geo-Personalized Newsletter ("Your Savings Digest")',
        "desc": (
            "Automated weekly email built from user's ZIP: new/updated discounts nearby, "
            "seasonal tip, protection alert, featured guide. All infrastructure exists "
            "(Customer.io, 46 templates, geo data). Converts one-time visitors into weekly "
            "engaged users who actually use the discounts."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Email/Retention",
    },
    {
        "name": "Merchant Verification Partnership Program",
        "desc": (
            'Approach top 50 merchants with a "Verified Senior Discount" badge for their '
            "websites and in-store signage. In exchange: verified discount data, co-marketing, "
            "affiliate relationship. Solves data accuracy and creates a relationship moat "
            "competitors cannot replicate by scraping."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Distribution",
    },
    {
        "name": "Community Discount Submissions",
        "desc": (
            "Let users submit discounts at local businesses (the long tail the database "
            "does not cover). Submission goes through LLM pre-screen + team review using "
            "the existing claim/accept workflow pattern. Expands the database into local "
            "businesses, the hardest data to replicate."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Community",
    },
    {
        "name": "Embeddable Discount Widget for Distribution Partners",
        "desc": (
            "Lightweight JS widget that senior centers, libraries, financial advisors, and "
            "Medicare brokers embed on their sites. Shows local Saverwell discounts. Each "
            "embed drives backlinks (SEO), awareness, and partner trust. Cloudflare Worker "
            "routes, embed.js, and test page are already built."
        ),
        "status": STATUS_BUILT,
        "category": "Distribution",
    },
    {
        "name": "Savings Tracker with Monthly Impact Reports",
        "desc": (
            "Users self-report when they use a discount (or track via affiliate clicks). "
            'Shows cumulative savings: "You\'ve saved $47 this month across 6 stores." '
            "Monthly recap email with annual total. Closes the discovery-to-action loop "
            "and produces shareable proof that drives word-of-mouth."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Tools",
    },
    # --- New 20 ---
    {
        "name": '"Does [Store] Have a Senior Discount?" Page Expansion',
        "desc": (
            "Publish 1,000+ remaining merchant page drafts already generated and cached "
            "in merchant_page_drafts/. Each targets the exact query 'does [store] have a "
            "senior discount' with direct answer boxes and FAQ schema. Content is ready to push."
        ),
        "status": STATUS_IN_PROGRESS,
        "category": "SEO/Content",
    },
    {
        "name": '"Senior Discount Day" Calendar Pages',
        "desc": (
            'Build 7 day-of-week pages ("Senior Discount Tuesday," etc.) listing every '
            "merchant with a discount on that day, extracted from 8,762 day-specific records. "
            "Add DMA-scoped variants for long-tail coverage. No competitor has this."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "SEO/Content",
    },
    {
        "name": "Category Landing Pages",
        "desc": (
            'Programmatic pages like "Senior Discounts at Grocery Stores," "Senior Discounts '
            'at Restaurants." Uses existing category_id on merchants. Targets commercial-intent '
            "searches that currently lead to thin listicle articles from competitors."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "SEO/Content",
    },
    {
        "name": "Seasonal Savings Hub Pages",
        "desc": (
            'Calendar-driven content hubs: "Senior Black Friday Deals" (Nov), "Senior Tax '
            'Season Savings" (Feb-Apr), "Back-to-School Senior Discounts" (Aug). Publish '
            "4-6 weeks before peak search volume, refresh annually."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Seasonal",
    },
    {
        "name": "Senior Property Tax Exemptions by State",
        "desc": (
            "51 programmatic pages (50 states + DC) detailing each state's senior property "
            "tax exemptions and homestead programs. Extends existing state page infrastructure. "
            "High-intent, intensely local searches spike Jan-Mar."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "SEO/Content",
    },
    {
        "name": "Library & Senior Center Content Kit",
        "desc": (
            'Monthly print-ready "Senior Savings Digest" PDFs with QR code to local DMA page. '
            "Libraries enter ZIP at /partners/library to auto-receive monthly updates. Generates "
            "backlinks from library websites and puts Saverwell URL in trusted physical settings."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Distribution",
    },
    {
        "name": "Financial Advisor Resource Hub",
        "desc": (
            "/partners/advisors landing page with downloadable one-pagers, client checklists, "
            "and widget embed code. Getting 50-100 advisors to embed the widget or link creates "
            "an unreplicable backlink profile. Widget infrastructure is already built."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Distribution",
    },
    {
        "name": "Local Newspaper Syndication",
        "desc": (
            'Offer community newspapers a free "Senior Savings Column" for digital editions. '
            "Saverwell generates local DMA content, newspaper publishes with attribution link. "
            "Small-market papers need free content. Creates high-authority local backlinks."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Distribution",
    },
    {
        "name": '"Share a Deal" Social Cards',
        "desc": (
            '"Share This Deal" button on merchant pages generates a social card image with '
            "discount details and Saverwell branding. Seniors share savings tips via Facebook, "
            "email, and text. OG meta tags can be generated dynamically from discount data."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Social/Viral",
    },
    {
        "name": "Senior Savings Map",
        "desc": (
            "Interactive map at /map where users enter ZIP and see all senior discounts "
            "plotted nearby. Database has 56,778 store locations. Maps are inherently "
            "shareable, increase time-on-site, and create an experience text competitors "
            "cannot match."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Tools",
    },
    {
        "name": '"Print My Savings Card" Pocket Reference',
        "desc": (
            "Generate a printable wallet-sized card listing a user's top 5-10 merchants "
            "organized by day of the week. Seniors who are not digitally native value physical "
            "references. Every printed card has the Saverwell URL, turning users into offline "
            "distribution."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Tools",
    },
    {
        "name": '"Did It Work?" Discount Verification',
        "desc": (
            'Thumbs-up/down system on merchant pages: "Did you get this discount?" Shows '
            '"92% confirmed" trust badges. Creates return visits, crowd-sourced data quality, '
            "and UGC freshness signals Google values."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Community",
    },
    {
        "name": "Local Champion Ambassador Program",
        "desc": (
            "Recruit volunteer ambassadors per DMA who submit local discounts, verify existing "
            "ones, and promote in their community. Custom referral links with UTM tracking. "
            "Creates ground-level distribution network impossible to replicate via SEO alone."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Community",
    },
    {
        "name": '"Am I Overpaying?" Subscription Audit Tool',
        "desc": (
            "Interactive tool walking users through common recurring overcharges: phone plans, "
            "cable, insurance, prescriptions. Generates personalized savings PDF (email capture). "
            "Cross-links to existing affiliate guides."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Tools",
    },
    {
        "name": "Government Benefit Finder",
        "desc": (
            "Questionnaire tool helping seniors discover unclaimed benefits: property tax "
            "exemptions, LIHEAP, Medicare Extra Help, SNAP, Lifeline phone. 5-10 questions "
            "produce a personalized program list. Targets 'benefits for seniors' searches."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Tools",
    },
    {
        "name": "ZIP Code Landing Pages",
        "desc": (
            'Programmatic pages for top 500 ZIP codes by senior population: "Senior Discounts '
            'Near [ZIP] - [City]." Uses 56,778 location records and existing zcta_centroids.csv '
            "mapping. Captures hyper-local long-tail queries."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "SEO/Content",
    },
    {
        "name": "Retirement Destination Shopping Guides",
        "desc": (
            "Editorial pages for top 25 retirement cities (The Villages FL, Sun City AZ). "
            '"Senior-Friendly Shopping in [City]" covering local discounts, best days, '
            "accessibility. Targets relocation-research queries with high lifetime user value."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "SEO/Content",
    },
    {
        "name": '"Forward to a Friend" Email Referral Mechanism',
        "desc": (
            "Add forwarding CTA to all 46 email templates with tracked forward links. Both "
            "forwarder and friend get bonus content. Email forwarding is seniors' primary "
            "sharing method. UTM infrastructure already supports tracking."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Email/Retention",
    },
    {
        "name": '"Savings Streak" Email Gamification',
        "desc": (
            "Users who open 4 consecutive weekly emails earn a streak badge and access to a "
            '"Hidden Deals" bonus section. Track via Customer.io profile attributes. Increases '
            "open rates (improves deliverability) and creates habit loop."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Email/Retention",
    },
    {
        "name": '"Tax Season Savings" Hub',
        "desc": (
            "Seasonal hub bundling existing tax/SS/IRMAA guides into a structured walkthrough "
            "for Jan-Apr tax season. Add VITA locator, tax software discounts, and filing tips "
            "for retirees. Second annual traffic spike alongside Medicare AEP."
        ),
        "status": STATUS_NOT_STARTED,
        "category": "Seasonal",
    },
]

# Categories for dropdown validation
CATEGORIES = [
    "SEO/Content",
    "Distribution",
    "Social/Viral",
    "Community",
    "Tools",
    "Local/Geo",
    "Email/Retention",
    "Seasonal",
    "Revenue",
]

STATUSES = ["Not Started", "In Progress", "Built", "Shipped", "Parked"]


# ── Priority Matrix data (Tab 2) ─────────────────────────────────────────────

PRIORITY_HEADERS = [
    "Idea #",
    "Idea Name",
    "Traffic Impact",
    "Build Effort",
    "Competitive Moat",
    "Category",
]

PRIORITY_ROWS = [
    ["1", '"Senior Day" SMS/Push Reminder System', "Low", "Low", "High", "Email/Retention"],
    ["2", "Affiliate Revenue Layer", "Low", "Low", "Low", "Revenue"],
    ["3", '"Money Left on the Table" Calculator', "Medium", "Medium", "Medium", "Tools"],
    ["4", "Scam Alert Real-Time Feed", "Medium", "Medium", "High", "Community"],
    ["5", "Medicare Open Enrollment Hub", "High", "Medium", "Medium", "Seasonal"],
    ["6", "Geo-Personalized Newsletter", "Medium", "Medium", "Medium", "Email/Retention"],
    ["7", "Merchant Verification Partnerships", "Low", "Low (biz dev)", "Very High", "Distribution"],
    ["8", "Community Discount Submissions", "Low", "Medium", "Very High", "Community"],
    ["9", "Embeddable Discount Widget", "Medium", "Low", "Medium", "Distribution"],
    ["10", "Savings Tracker", "Low", "Medium", "High", "Tools"],
    ["11", "Merchant Page Expansion (1,000+)", "Very High", "Low", "High", "SEO/Content"],
    ["12", '"Senior Discount Day" Calendar Pages', "High", "Medium", "Very High", "SEO/Content"],
    ["13", "Category Landing Pages", "High", "Low", "Medium", "SEO/Content"],
    ["14", "Seasonal Savings Hub Pages", "High", "Medium", "Medium", "Seasonal"],
    ["15", "Property Tax Exemptions by State", "High", "Medium", "High", "SEO/Content"],
    ["16", "Library & Senior Center Content Kit", "Low", "Medium", "High", "Distribution"],
    ["17", "Financial Advisor Resource Hub", "Medium", "Low", "High", "Distribution"],
    ["18", "Local Newspaper Syndication", "Medium", "Low (biz dev)", "High", "Distribution"],
    ["19", '"Share a Deal" Social Cards', "Medium", "Low", "Low", "Social/Viral"],
    ["20", "Senior Savings Map", "High", "Medium", "High", "Tools"],
    ["21", '"Print My Savings Card"', "Low", "Low", "Medium", "Tools"],
    ["22", '"Did It Work?" Verification', "Medium", "Medium", "High", "Community"],
    ["23", "Local Champion Ambassadors", "Medium", "Medium", "Very High", "Community"],
    ["24", '"Am I Overpaying?" Subscription Audit', "High", "Medium", "Medium", "Tools"],
    ["25", "Government Benefit Finder", "High", "High", "Medium", "Tools"],
    ["26", "ZIP Code Landing Pages", "Very High", "Low", "Medium", "SEO/Content"],
    ["27", "Retirement Destination Guides", "Medium", "Medium", "Medium", "SEO/Content"],
    ["28", '"Forward to a Friend" Referral', "Low", "Low", "Low", "Email/Retention"],
    ["29", '"Savings Streak" Gamification', "Low", "Low", "Medium", "Email/Retention"],
    ["30", '"Tax Season Savings" Hub', "High", "Medium", "Medium", "Seasonal"],
]


# ── Google Sheets creation ────────────────────────────────────────────────────

print("Creating Google Sheet for Saverwell Product Ideas...")

from cmo_agent.google_auth import get_google_credentials, share_file_restricted
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file',
]
creds = get_google_credentials(
    oauth_token_path=OAUTH_TOKEN_PATH, service_account_path="", scopes=SCOPES
)
if creds is None:
    print("ERROR: Could not load Google credentials.")
    sys.exit(1)

sheets_service = build('sheets', 'v4', credentials=creds)
drive_service = build('drive', 'v3', credentials=creds)


# ── Create spreadsheet with two tabs ──────────────────────────────────────────

spreadsheet_body = {
    'properties': {'title': 'Saverwell Product Ideas Tracker'},
    'sheets': [
        {'properties': {'title': 'Product Ideas', 'sheetId': 0}},
        {'properties': {'title': 'Priority Matrix', 'sheetId': 1}},
    ],
}
spreadsheet = sheets_service.spreadsheets().create(body=spreadsheet_body).execute()
spreadsheet_id = spreadsheet['spreadsheetId']
sheet_url = spreadsheet['spreadsheetUrl']
print(f"  Created spreadsheet: {spreadsheet_id}")

# Share
share_file_restricted(drive_service, spreadsheet_id)
print("  Shared with authorized users")


# ── Tab 1: Product Ideas ─────────────────────────────────────────────────────

print("Writing Product Ideas tab...")

HEADERS = ["Idea Name", "Idea Description", "Status", "Category"]
idea_rows = []
for idea in IDEAS:
    idea_rows.append([
        idea["name"],
        idea["desc"],
        idea["status"],
        idea["category"],
    ])

all_values = [HEADERS] + idea_rows
sheets_service.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id,
    range='Product Ideas!A1',
    valueInputOption='RAW',
    body={'values': all_values},
).execute()
print(f"  Wrote {len(idea_rows)} ideas + header")


# ── Tab 2: Priority Matrix ───────────────────────────────────────────────────

print("Writing Priority Matrix tab...")

priority_values = [PRIORITY_HEADERS] + PRIORITY_ROWS
sheets_service.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id,
    range='Priority Matrix!A1',
    valueInputOption='RAW',
    body={'values': priority_values},
).execute()
print(f"  Wrote {len(PRIORITY_ROWS)} rows + header")


# ── Formatting + Data Validation ──────────────────────────────────────────────

print("Applying formatting and data validation...")

num_ideas = len(IDEAS)
num_priority = len(PRIORITY_ROWS)
num_idea_cols = len(HEADERS)
num_priority_cols = len(PRIORITY_HEADERS)

# Navy header color matching existing sheets
NAVY = {'red': 0.16, 'green': 0.22, 'blue': 0.43}
WHITE = {'red': 1, 'green': 1, 'blue': 1}
LIGHT_GRAY = {'red': 0.95, 'green': 0.95, 'blue': 0.97}

requests = []

# --- Product Ideas tab formatting ---

# Bold white-on-navy header row
requests.append({
    'repeatCell': {
        'range': {
            'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 1,
            'startColumnIndex': 0, 'endColumnIndex': num_idea_cols,
        },
        'cell': {
            'userEnteredFormat': {
                'textFormat': {'bold': True, 'foregroundColorStyle': {
                    'rgbColor': WHITE,
                }},
                'backgroundColor': NAVY,
            }
        },
        'fields': 'userEnteredFormat(textFormat,backgroundColor)',
    }
})

# Freeze header row
requests.append({
    'updateSheetProperties': {
        'properties': {'sheetId': 0, 'gridProperties': {'frozenRowCount': 1}},
        'fields': 'gridProperties.frozenRowCount',
    }
})

# Alternating row colors for data rows
for row_idx in range(1, num_ideas + 1):
    if row_idx % 2 == 0:
        requests.append({
            'repeatCell': {
                'range': {
                    'sheetId': 0,
                    'startRowIndex': row_idx,
                    'endRowIndex': row_idx + 1,
                    'startColumnIndex': 0,
                    'endColumnIndex': num_idea_cols,
                },
                'cell': {
                    'userEnteredFormat': {'backgroundColor': LIGHT_GRAY}
                },
                'fields': 'userEnteredFormat.backgroundColor',
            }
        })

# Wrap text on description column (col B, index 1)
requests.append({
    'repeatCell': {
        'range': {
            'sheetId': 0, 'startRowIndex': 1, 'endRowIndex': num_ideas + 1,
            'startColumnIndex': 1, 'endColumnIndex': 2,
        },
        'cell': {
            'userEnteredFormat': {'wrapStrategy': 'WRAP'}
        },
        'fields': 'userEnteredFormat.wrapStrategy',
    }
})

# Set column widths: A=250, B=500, C=120, D=140
for col_idx, width in [(0, 250), (1, 500), (2, 120), (3, 140)]:
    requests.append({
        'updateDimensionProperties': {
            'range': {
                'sheetId': 0,
                'dimension': 'COLUMNS',
                'startIndex': col_idx,
                'endIndex': col_idx + 1,
            },
            'properties': {'pixelSize': width},
            'fields': 'pixelSize',
        }
    })

# Data validation: Status dropdown (column C, index 2)
requests.append({
    'setDataValidation': {
        'range': {
            'sheetId': 0,
            'startRowIndex': 1,
            'endRowIndex': num_ideas + 1,
            'startColumnIndex': 2,
            'endColumnIndex': 3,
        },
        'rule': {
            'condition': {
                'type': 'ONE_OF_LIST',
                'values': [{'userEnteredValue': s} for s in STATUSES],
            },
            'showCustomUi': True,
            'strict': True,
        },
    }
})

# Data validation: Category dropdown (column D, index 3)
requests.append({
    'setDataValidation': {
        'range': {
            'sheetId': 0,
            'startRowIndex': 1,
            'endRowIndex': num_ideas + 1,
            'startColumnIndex': 3,
            'endColumnIndex': 4,
        },
        'rule': {
            'condition': {
                'type': 'ONE_OF_LIST',
                'values': [{'userEnteredValue': c} for c in CATEGORIES],
            },
            'showCustomUi': True,
            'strict': True,
        },
    }
})

# --- Priority Matrix tab formatting ---

# Bold white-on-navy header row
requests.append({
    'repeatCell': {
        'range': {
            'sheetId': 1, 'startRowIndex': 0, 'endRowIndex': 1,
            'startColumnIndex': 0, 'endColumnIndex': num_priority_cols,
        },
        'cell': {
            'userEnteredFormat': {
                'textFormat': {'bold': True, 'foregroundColorStyle': {
                    'rgbColor': WHITE,
                }},
                'backgroundColor': NAVY,
            }
        },
        'fields': 'userEnteredFormat(textFormat,backgroundColor)',
    }
})

# Freeze header row
requests.append({
    'updateSheetProperties': {
        'properties': {'sheetId': 1, 'gridProperties': {'frozenRowCount': 1}},
        'fields': 'gridProperties.frozenRowCount',
    }
})

# Auto-resize priority matrix columns
requests.append({
    'autoResizeDimensions': {
        'dimensions': {
            'sheetId': 1,
            'dimension': 'COLUMNS',
            'startIndex': 0,
            'endIndex': num_priority_cols,
        }
    }
})

# Alternating row colors for priority matrix
for row_idx in range(1, num_priority + 1):
    if row_idx % 2 == 0:
        requests.append({
            'repeatCell': {
                'range': {
                    'sheetId': 1,
                    'startRowIndex': row_idx,
                    'endRowIndex': row_idx + 1,
                    'startColumnIndex': 0,
                    'endColumnIndex': num_priority_cols,
                },
                'cell': {
                    'userEnteredFormat': {'backgroundColor': LIGHT_GRAY}
                },
                'fields': 'userEnteredFormat.backgroundColor',
            }
        })

# Execute all formatting
sheets_service.spreadsheets().batchUpdate(
    spreadsheetId=spreadsheet_id,
    body={'requests': requests},
).execute()

print("  Formatting and data validation applied")


# ── Done ──────────────────────────────────────────────────────────────────────

print(f"\n{'=' * 60}")
print(f"  Google Sheet URL: {sheet_url}")
print(f"{'=' * 60}")
print(f"\nSummary:")
print(f"  Product Ideas tab: {len(idea_rows)} ideas")
print(f"  Priority Matrix tab: {len(PRIORITY_ROWS)} rows")
print(f"  Status dropdowns: {', '.join(STATUSES)}")
print(f"  Category dropdowns: {', '.join(CATEGORIES)}")

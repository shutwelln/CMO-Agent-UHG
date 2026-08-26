"""Generate protection drip (8) and guide drip (12) HTML email templates.

Uses pre-built email variant fields from article JSON files and the same
responsive HTML structure as the welcome campaign templates.
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "data" / "saverwell" / "email_templates"
PROTECTION_DIR = BASE_DIR / "data" / "saverwell" / "protection_drafts"
GUIDE_DIR = BASE_DIR / "data" / "saverwell" / "guide_drafts"

# Ordered article sequences from the lifecycle marketing plan
PROTECTION_SEQUENCE = [
    "safe-online-shopping-tips",
    "password-safety-guide",
    "bank-impostor-calls",
    "subscription-traps-unauthorized-charges",
    "email-account-hacked",
    "what-to-do-after-a-data-breach",
    "two-factor-authentication-guide",
    "tax-identity-theft",
]

GUIDE_SEQUENCE = [
    "medicare-explained-simple-guide",
    "medicare-parts-a-b-c-d-explained",
    "save-money-medicare-premiums",
    "medicare-enrollment-deadlines",
    "medicare-advantage-vs-original",
    "does-medicare-cover-prescriptions",
    "medicare-vs-medicaid-difference",
    "does-medicare-cover-dental",
    "does-medicare-cover-vision",
    "does-medicare-cover-hearing-aids",
    "irmaa-avoid-higher-medicare-premiums",
    "medicare-extra-help-prescription-savings",
]

SITE_URL = "https://saverwell.com"
LOGO_URL = "https://lmtrgkmgfermqatopkfp.supabase.co/storage/v1/object/public/Saverwell/saverwell-logo.png"


def clean_text(text: str) -> str:
    """Remove em dashes and en dashes (anti-AI writing rule)."""
    text = text.replace("\u2014", " - ")  # em dash
    text = text.replace("\u2013", " - ")  # en dash
    return text


def md_to_html_simple(md: str) -> str:
    """Convert simple markdown to HTML paragraphs. No bold mid-sentence."""
    md = clean_text(md)
    # Split into paragraphs
    paragraphs = [p.strip() for p in md.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [md.strip()]
    return paragraphs


def make_cta_button(label: str, url: str) -> str:
    """Outlook-safe CTA button."""
    return f"""          <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin: 0 auto;">
            <tr>
              <td style="border-radius: 6px; background-color: #2A9D8F;">
                <a href="{url}" target="_blank" style="display: inline-block; background-color: #2A9D8F; color: #ffffff; font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif; font-size: 16px; font-weight: bold; padding: 14px 32px; text-decoration: none; border-radius: 6px; border: 1px solid #228176;">
                  {label}
                </a>
              </td>
            </tr>
          </table>"""


def wrap_email(
    subject: str,
    preheader: str,
    headline: str,
    body_paragraphs: list[str],
    cta_label: str,
    cta_url: str,
    footer_note: str,
) -> str:
    """Wrap content in the standard Saverwell responsive email template."""
    # Build body paragraphs HTML
    body_html = ""
    for p in body_paragraphs:
        body_html += f"""
          <p style="margin: 0 0 16px;">{p}</p>
"""

    cta = make_cta_button(cta_label, cta_url)

    return f"""<!-- Subject: {subject} -->
<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>Saverwell</title>
  <!--[if mso]>
  <style type="text/css">
    table {{border-collapse: collapse; border: 0; border-spacing: 0; margin: 0;}}
    div, td {{padding: 0;}}
    div {{margin: 0 !important;}}
  </style>
  <noscript>
    <xml>
      <o:OfficeDocumentSettings>
        <o:PixelsPerInch>96</o:PixelsPerInch>
      </o:OfficeDocumentSettings>
    </xml>
  </noscript>
  <![endif]-->
  <style type="text/css">
    body {{ margin: 0; padding: 0; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
    table {{ border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
    img {{ border: 0; line-height: 100%; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; }}
    a {{ color: #2A9D8F; text-decoration: underline; }}
    @media only screen and (max-width: 620px) {{
      .email-container {{ width: 100% !important; max-width: 100% !important; }}
      .fluid {{ max-width: 100% !important; height: auto !important; }}
      .stack-column {{ display: block !important; width: 100% !important; max-width: 100% !important; }}
      .mobile-pad {{ padding-left: 20px !important; padding-right: 20px !important; }}
    }}
  </style>
</head>
<body style="margin: 0; padding: 0; background-color: #ffffff; font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif;">
  <!-- Preheader (hidden preview text) -->
  <div style="display: none; max-height: 0; overflow: hidden; mso-hide: all;">
    {preheader}
  </div>
  <!-- Prevent Gmail from using preheader as snippet -->
  <div style="display: none; max-height: 0; overflow: hidden; mso-hide: all;">
    &nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;
  </div>

  <center style="width: 100%; background-color: #ffffff;">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" align="center" class="email-container" style="margin: auto; background-color: #ffffff;">

      <!-- LOGO HEADER -->
      <tr>
        <td style="padding: 32px 40px 16px; text-align: center;" class="mobile-pad">
          <img src="{LOGO_URL}" alt="Saverwell" width="180" style="display: block; margin: 0 auto; max-width: 180px; height: auto;">
          <br>
          <span style="font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif; font-size: 13px; color: #6B7B8D;">Save more. Stay protected.</span>
        </td>
      </tr>

      <!-- DIVIDER -->
      <tr>
        <td style="padding: 0 40px;" class="mobile-pad">
          <hr style="border: none; border-top: 2px solid #2A9D8F; margin: 0;">
        </td>
      </tr>

      <!-- BODY CONTENT -->
      <tr>
        <td style="padding: 24px 40px 32px; font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif; font-size: 16px; line-height: 1.65; color: #3D4F5F;" class="mobile-pad">

          <p style="margin: 0 0 16px; font-size: 20px; font-weight: bold; color: #3D4F5F;">
            {headline}
          </p>
{body_html}
{cta}

          <p style="margin: 24px 0 0; font-size: 16px; color: #3D4F5F;">
            {footer_note}
          </p>
        </td>
      </tr>

      <!-- FOOTER -->
      <tr>
        <td style="padding: 24px 40px; background-color: #ffffff; border-top: 1px solid #E8EAEC; font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif; font-size: 13px; color: #8A96A3; text-align: center;" class="mobile-pad">
          <p style="margin: 0 0 8px;">Saverwell - Save more. Stay protected.</p>
          <p style="margin: 0 0 8px;">
            <a href="{{{{ unsubscribe_url }}}}" style="color: #6B7B8D; text-decoration: underline;">Manage your email preferences</a>
            &nbsp;|&nbsp;
            <a href="{{{{ unsubscribe_url }}}}" style="color: #6B7B8D; text-decoration: underline;">Unsubscribe from all</a>
          </p>
          <p style="margin: 0;">Saverwell Holdings, LLC</p>
        </td>
      </tr>

    </table>
  </center>
</body>
</html>"""


def load_article(path: Path) -> dict:
    """Load article JSON and extract email variant fields."""
    with open(path) as f:
        data = json.load(f)
    return data


def build_headline_from_title(title: str) -> str:
    """Create a headline from the article title, cleaned of AI patterns."""
    return clean_text(title)


def generate_protection_drip():
    """Generate 8 protection drip email templates."""
    print("Generating protection drip emails...")
    for i, slug in enumerate(PROTECTION_SEQUENCE, 1):
        path = PROTECTION_DIR / f"{slug}.json"
        if not path.exists():
            print(f"  WARNING: {path} not found, skipping")
            continue

        article = load_article(path)
        subject = clean_text(article["email_subject"])
        preheader = clean_text(article["email_preheader"])
        intro_md = article["email_intro_md"]
        cta_label = article.get("email_cta_label", "Read full guide")
        cta_url_path = article["email_cta_url"]
        cta_url = f"{SITE_URL}{cta_url_path}"
        title = article.get("title", slug.replace("-", " ").title())

        paragraphs = md_to_html_simple(intro_md)
        headline = build_headline_from_title(title)

        # Position-aware footer note
        if i == 1:
            footer_note = (
                "This is your first protection tip from Saverwell. "
                "Every Tuesday, we send a new guide to help you stay ahead of financial threats."
            )
        elif i == len(PROTECTION_SEQUENCE):
            footer_note = (
                "This is the final article in your protection series. "
                "Keep an eye out for new protection content in your weekly digest."
            )
        else:
            footer_note = (
                f"This is article {i} of {len(PROTECTION_SEQUENCE)} in your protection series. "
                "New tips arrive every Tuesday."
            )

        html = wrap_email(
            subject=subject,
            preheader=preheader,
            headline=headline,
            body_paragraphs=paragraphs,
            cta_label=cta_label,
            cta_url=cta_url,
            footer_note=footer_note,
        )

        out_path = TEMPLATES_DIR / f"drip_protection_{i:02d}_{slug}.html"
        out_path.write_text(html)
        print(f"  {i}/{len(PROTECTION_SEQUENCE)}: {out_path.name} ({len(html):,} bytes)")


def generate_guide_drip():
    """Generate 12 guide drip email templates."""
    print("\nGenerating guide drip emails...")
    for i, slug in enumerate(GUIDE_SEQUENCE, 1):
        path = GUIDE_DIR / f"{slug}.json"
        if not path.exists():
            print(f"  WARNING: {path} not found, skipping")
            continue

        article = load_article(path)
        subject = clean_text(article["email_subject"])
        preheader = clean_text(article["email_preheader"])
        intro_md = article["email_intro_md"]
        cta_label = article.get("email_cta_label", "Read the full guide")
        cta_url_path = article["email_cta_url"]
        cta_url = f"{SITE_URL}{cta_url_path}"
        title = article.get("title", slug.replace("-", " ").title())

        paragraphs = md_to_html_simple(intro_md)
        headline = build_headline_from_title(title)

        # Position-aware footer note
        if i == 1:
            footer_note = (
                "This is your first Medicare guide from Saverwell. "
                "Every Thursday, we send a new guide to help you navigate Medicare with confidence."
            )
        elif i == len(GUIDE_SEQUENCE):
            footer_note = (
                "This is the final guide in your Medicare series. "
                "Keep an eye out for new guides in your weekly digest."
            )
        else:
            footer_note = (
                f"This is guide {i} of {len(GUIDE_SEQUENCE)} in your Medicare series. "
                "New guides arrive every Thursday."
            )

        html = wrap_email(
            subject=subject,
            preheader=preheader,
            headline=headline,
            body_paragraphs=paragraphs,
            cta_label=cta_label,
            cta_url=cta_url,
            footer_note=footer_note,
        )

        out_path = TEMPLATES_DIR / f"drip_guide_{i:02d}_{slug}.html"
        out_path.write_text(html)
        print(f"  {i}/{len(GUIDE_SEQUENCE)}: {out_path.name} ({len(html):,} bytes)")


def main():
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    generate_protection_drip()
    generate_guide_drip()
    print(f"\nDone! {len(PROTECTION_SEQUENCE) + len(GUIDE_SEQUENCE)} drip templates generated.")
    print(f"Output directory: {TEMPLATES_DIR}")


if __name__ == "__main__":
    main()

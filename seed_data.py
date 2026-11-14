"""The GAPHS Library as first published: the Atelier Series guides, their video versions, and the
Home Staging for Real Estate Agents course with its twelve downloads.

Files come from the GAPHS content folder in Google Drive (drive_id). Admin > Content >
"Import files from Google Drive" copies them into the site. Covers are in seed/,
made by tools/make_cards.py.
"""

GUIDES = [
    {
        "slug": "pricing-models", "no": "01", "title": "Pricing Models for your Home Staging Business",
        "subtitle": "How to price your staging services with confidence",
        "pdf": "1ZLpuXgSVRqszXtZXgowQfEC18xnJyeLb", "video": "1XjaZPwhWSXCgE99HuvXMFoMQjSI2JPMA",
        "description": "Setting your fees is one of the hardest parts of running a staging business. This guide "
                       "walks through the pricing models professional stagers use and how to choose and present "
                       "yours with confidence.",
    },
    {
        "slug": "staging-an-occupied-property", "no": "02", "title": "Staging an Occupied Property",
        "subtitle": "A professional guide to preparing a lived-in home for sale",
        "pdf": "1n3TcqfemaN2dMEDbYNCBnj8QpXu24eTr", "video": "1QacNoAo5FAy5u8aKnVwsYQqbZTI8jpHb",
        "description": "Most homes are sold while the owners still live in them. This guide covers how to prepare "
                       "a lived-in home for sale: decluttering, depersonalising and styling with what is already there.",
    },
    {
        "slug": "staging-a-vacant-property", "no": "03", "title": "Staging a Vacant Property",
        "subtitle": "A professional guide to bringing an empty home to life for sale",
        "pdf": "17wPz2FkECqhTdCMBr3cMlM5T8yOeIOUw", "video": "1KprvQ0bVINk1B0XREjwrQdvYGrCX-OYd",
        "description": "Empty rooms are hard for buyers to read. This guide shows how to bring a vacant property to "
                       "life, so buyers understand the scale and purpose of every room.",
    },
    {
        "slug": "your-staging-business-plan", "no": "04", "title": "Your Staging Business Plan",
        "subtitle": "How to plan, start and grow a successful Home Staging business",
        "pdf": "1Dp5Yi9XaYm0ochS0lBoZ0y_ZFD2GIkWG", "video": "1YqM4jNCQ4uRPK6WWR5W7ZiqntMI3o1gD",
        "description": "For professionals and future professionals: how to plan, start and grow a Home Staging "
                       "business, step by step.",
    },
    {
        "slug": "the-agents-guide-to-home-staging", "no": "05", "title": "The Agent’s Guide to Home Staging",
        "subtitle": "Protect your commission, sell better and faster, and turn every listing into a marketing asset",
        "pdf": "1kXnvhSBXyQBvkcslP79RWbI4BTApuBgR", "video": "",
        "description": "Written for real estate professionals: what staging is, why buyers respond to it and how "
                       "agents can use it to win listings and sell them well.",
    },
    {
        "slug": "ai-quotes-and-proposals", "no": "06", "title": "From Walkthrough to Signed Proposal",
        "subtitle": "Using AI to build quotes and proposals for your Home Staging business",
        "pdf": "16IsfKkoXPxB4wxuGn8_jti3HIKuQYRW2", "video": "17ayQnREXS4nVfvhN0_fwCHDJCQyHpgO6",
        "description": "How to use AI tools to turn a property walkthrough into a clear quote and a professional "
                       "proposal, faster and without losing your own voice.",
    },
]

COURSE = {
    "slug": "home-staging-for-real-estate-agents",
    "title": "Home Staging for Real Estate Agents",
    "subtitle": "Understand staging, use it in your marketing and partner with professional stagers",
    "description": (
        "Written for estate agents, real estate agents and brokers. The course explains how staging works and "
        "why buyers respond to it, how to use it as a marketing tool in your listings, and how to build a strong "
        "working partnership with a professional stager.\n\n"
        "**Three modules:** Understanding Home Staging, Using Staging as a Marketing Tool, and Partnering with "
        "Stagers.\n\n"
        "**Twelve tools** to use with real listings, from the Agent Workbook and a seller readiness checklist to "
        "a results tracker and a first 90 days plan."
    ),
    "slides_pdf": "1i_m7ugIi0QFbyhrHyOqoudwY9liE_Kmd",
    "slides_html": "1_gnLz7FLRyFwqaUykf-RpKOWhnZ-8enz",
    # (title, summary, first slide, last slide)
    "lessons": [
        ("Welcome to the course", "Who the course is for, who GAPHS is, how the three modules work and the twelve tools in your pack.", 1, 5),
        ("Module 1 · Understanding Home Staging", "What staging is and is not, the four types, how buyers look at a home, what agents report and the process from start to finish.", 6, 18),
        ("Module 2 · Using Staging as a Marketing Tool", "Where staging fits in your sales process, how to raise it with a seller, objections, photography and viewings, and what staging gives your business.", 19, 39),
        ("Module 3 · Partnering with Stagers", "Finding and vetting a professional, briefing, roles, putting arrangements in writing, tracking results and building a network.", 40, 58),
        ("Putting it into practice", "Your staging approach in four steps, your first 90 days and where to go next.", 59, 63),
    ],
}

DOWNLOADS = [
    ("01", "Agent Workbook", "Reflection questions for each module. Complete them as you watch to make the most of the course.", "1D3zV5L3uCVvcW8cjJ8ylMi_mW5-DOLpb"),
    ("02", "Staging Conversation Guide", "What to say, step by step, when you raise staging with an owner.", "1YOwtrRLDMT-8xzSYfWiBH9-oQ_eR0-Ja"),
    ("03", "Seller Readiness Checklist", "A handout to give owners before you list.", "1SY9DqMcL9V3MV3HN0VbMA7HnnxBDhyl_"),
    ("04", "Objection Handling Cards", "Short, respectful answers to the worries owners raise.", "1cyWGE0CQyUIN2qYl8N3EV7gRRE3ovngt"),
    ("05", "Listing Presentation Page", "A staging page you can adapt for your own listing presentation.", "1zHr4sIhEeAyq8EKoAFjerm8_WvaiZ635"),
    ("06", "Stager Vetting Questions", "What to ask before you refer a stager to an owner.", "1YTvpB6ozpCnxLPEs5e_jRr4evIq1ksh_"),
    ("07", "Staging Brief Template", "Brief a stager on one page.", "1tcHQSSJNdvJVWcQcQdv9M60HuxbQX08e"),
    ("08", "Stager Partnership Outline", "The points to agree in writing when you work with a stager. A briefing for your local legal adviser, not legal advice.", "1CWAj_kbqbZW9S2g6cg4eXnPAm1a0TaW_"),
    ("09", "Photography and Viewing Checklist", "Get every listing ready on time.", "1TGMCWh55h-35NE7gozlQRNzNqevLupps"),
    ("10", "Results Tracker", "Measure what staging does for your listings.", "19jwmOItUgFg8o4UpsIO-tac2nw_XAcAg"),
    ("11", "Case Study Template", "Turn every project into proof.", "1ZNQterNCmjwBmPcmV9qkTCsDgazbqcpO"),
    ("12", "First 90 Days Plan", "Put staging into your business.", "1rXci9EbXD-8zIhd-jhsotm_5ucDcT_N3"),
]


def download_slug(no, title):
    import re
    return "agents-course-" + no + "-" + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def narration_by_slide(path):
    """{slide_no: (title, text)} from the course narration script."""
    import re

    out = {}
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for m in re.finditer(r"Slide (\d+): ([^\n]+)\n\n(.*?)(?=\n\nSlide \d+:|\Z)", text, re.S):
        out[int(m.group(1))] = (m.group(2).strip(), m.group(3).strip())
    return out


def lesson_body(slides, first, last):
    parts = []
    for n in range(first, last + 1):
        if n in slides:
            title, text = slides[n]
            parts.append(f"### {title}\n\n{text}")
    return "\n\n".join(parts)


# Videos from GAPHS-approved schools (Drive folder "school videos"). Free for members.
SCHOOL_VIDEOS = [
    {"slug": "entre2portes-presentation", "title": "Entre2portes: Presentation", "drive": "1GPUx43dCnI_0qqS3TFaQW4Ec4qDHPLTL",
     "eyebrow": "Approved school · Entre2portes", "subtitle": "Why home staging works",
     "description": "This video introduces the concept of home staging and explains why it is such an effective strategy for "
                    "enhancing a property's appeal and supporting a successful sale. It explores the key principle that home "
                    "stagers must master to achieve effective property presentation, and shows how changing the way a property "
                    "is presented can transform the selling process.\n\nAn excerpt from Module 1, The Fundamentals of Home Staging, "
                    "of the Entre2portes training programme by Irène Sorolla. Subtitled in English exclusively for GAPHS; the rest "
                    "of the programme is taught in French: https://www.entre2portes.fr/formation-home-staging/programme"},
    {"slug": "entre2portes-basic-principles", "title": "Entre2portes: Basic Principles", "drive": "1bo0VYuPRCQGgJuBsTxut-LP55id52NAh",
     "eyebrow": "Approved school · Entre2portes", "subtitle": "Vacant and occupied staging, step by step",
     "description": "The fundamental principles of home staging, including minimalist design and why it is particularly relevant to "
                    "property presentation. The video challenges common misconceptions about home staging, introduces the two "
                    "main approaches, vacant and occupied staging, and the considerations involved in each, and outlines the key "
                    "steps of a successful project and the scope and limits of a home stager's work.\n\nAn excerpt from Module 1, "
                    "The Fundamentals of Home Staging, of the Entre2portes training programme by Irène Sorolla. Subtitled in "
                    "English exclusively for GAPHS; the rest of the programme is taught in French: "
                    "https://www.entre2portes.fr/formation-home-staging/programme"},
]

"""Public sales-page copy for GAPHS courses (/courses).
A course page shows a Buy button once a published Library course with the same title exists;
its price is set in Admin > Content. Leave price None here for 'get notified'."""

COMMON_FAQ = [
    ("Do I need staging experience?", "No. The course starts from the beginning and explains every term and step."),
    ("Will this work in my country?", "Yes. The method works worldwide, and the lessons show how to apply it in your own market, including with international buyers."),
    ("How are the lessons delivered?", "Online, at your own pace on any device, with downloadable workbooks and templates."),
    ("Do you offer refunds?", "Courses are digital and open as soon as you buy, so we do not offer refunds."),
    ("What if I need help?", "Write to us at info@gaphs.org and we will help."),
]

COURSES = [
    dict(slug="home-staging-for-real-estate-agents", price=None, img="course_agents.jpg", title="Home Staging for Real Estate Agents",
         label="Professional course · 3 modules", sub="List with more confidence. Sell with more impact.",
         meta="Staging is one of the most effective marketing tools an agent has. Learn how to use it, and how to partner with professional stagers.",
         overview="Written for estate agents, real estate agents and brokers. The course explains how staging works and why buyers respond to it, "
                  "how to use it as a marketing tool in your listings, and how to build a strong working partnership with a professional stager. "
                  "You will leave with clear language for sellers, ready-to-use checklists and a simple way to measure results. The method works "
                  "worldwide, for local buyers, overseas buyers and nationals buying abroad.",
         learn=["What staging is and is not, the four types, and how buyers look at a home",
                "Using the evidence honestly: what agents report, and how to word it",
                "Where staging fits in your sales process, and how to raise it with a seller",
                "Handling objections, and preparing a property for photography and viewings",
                "How to find, vet, brief and partner with professional stagers",
                "Tracking results, building case studies and your first 90 days"],
         who=["Real estate agents, brokers and sales negotiators",
              "Property developers and marketing teams",
              "Agencies that want a consistent presentation standard"],
         included=["Three modules, from understanding staging to partnering with stagers",
                   "Agent workbook, conversation guide and objection handling cards",
                   "Seller readiness checklist, stager vetting questions and staging brief template",
                   "Results tracker, case study template and first 90 days plan"],
         cta="Boost your listings", faq_extra=[("Is the course free for GAPHS members?", "Yes. Every course in the Library is included in GAPHS membership.")],
         featured=True),
]

# Courses offered by the Home Staging Education Centre (not by GAPHS). Their pages show the Education Centre as the
# provider, and the Buy button opens the course on the Education Centre's own site, where it is sold in pounds.
HSEC_NAME = "Home Staging Education Centre"
HSEC_FAQ = [("Who runs this course?", "The Home Staging Education Centre. You buy it and take it on the Education Centre's own website."),
            ("Do you offer refunds?", "Refunds are handled by the Home Staging Education Centre under its own terms.")]
EXTERNAL = [{'slug': 'introduction-to-home-staging',
  'price': 7700,
  'img': 'course_intro.jpg',
  'title': 'Introduction to Home Staging',
  'label': 'Beginner course · 8 modules',
  'sub': 'Start here. Find out if home staging is for you.',
  'meta': 'A clear, motivating first step into home staging: what it is, why it works and where it can take you.',
  'overview': 'Home staging is the professional preparation of a property for the market, and it is one of the most '
              'rewarding creative careers you can build. This short course gives you the foundations: what staging is '
              'and is not, why buyers respond to it, the different types of staging, and how a project runs from first '
              'enquiry to final photograph. You will also see how staging businesses earn, how they find clients, and '
              'what to do in your first 30 days.',
  'learn': ['What home staging is, and how it differs from interior design and decorating',
            'Why staging works: first impressions, buyer psychology and online viewing',
            'The types of staging: occupied, vacant, partial, developments, luxury, rentals and virtual',
            'How staging helps overseas buyers buying locally and nationals buying abroad',
            'The six stages of a staging project',
            'The business basics: how to earn, price and stay protected',
            'How to build a portfolio and win your first clients'],
  'who': ['Curious beginners wondering if staging is for them',
          'Homeowners and investors preparing to sell or rent',
          'Interior designers, decorators and property professionals adding a new service'],
  'included': ['8 narrated modules',
               'Workbook, self-check, room challenge, viewing-day checklist and glossary',
               'A clear next step into the full Journey'],
  'cta': 'Start the Introduction',
  'external': 'https://homestagingeducationcentre.co.uk/courses/introduction-to-home-staging',
  'currency': '€'},
 {'slug': 'home-staging-business-course',
  'price': 24700,
  'was': 29700,
  'img': 'course_business.jpg',
  'title': 'The Home Staging Business Course',
  'label': 'Business course · 3 modules · 9 lessons',
  'sub': 'Build a staging business that pays.',
  'meta': 'Turn your staging skills into a profitable, well-run business with clear goals, prices and systems.',
  'overview': 'Knowing how to stage is one thing. Running a business that earns well is another. In three practical '
              'modules you will price with confidence, win the right clients and plan your numbers. You will explore '
              'your revenue streams, your market and your goals, build a pricing structure, choose your routes to '
              'market and partners, plan your marketing, set up your business properly, create your terms of business '
              'and forecast your finances. A full toolkit of business templates and a financial spreadsheet is '
              'included. The business works the same way wherever you are in the world.',
  'learn': ['Price with confidence: revenue streams, goals, value, costs and profit',
            'Choose your market, your services and your ideal client',
            'Win clients through routes to market, partnerships and marketing',
            'Building your brand and planning your marketing',
            'Business planning: your plan, set-up, contracts and hiring',
            'Financial modelling: start-up costs, profit plan and cashflow',
            'Your first 90 days as a business owner'],
  'who': ['Home stagers who want to grow or professionalise their business',
          'Designers and decorators launching staging as a service',
          'Anyone who has completed The Staging Journey and wants to go deeper'],
  'included': ['Business workbook and planners',
               'Pricing and quote worksheet, client agreement outline, intake and project templates',
               'Spreadsheet with pricing calculator, start-up costs, profit plan and cashflow tracker',
               '12 downloads in total'],
  'cta': 'Grow your business',
  'external': 'https://homestagingeducationcentre.co.uk/courses/home-staging-business-course',
  'currency': '£'},
 {'slug': 'design-elements-and-styling',
  'price': 11700,
  'was': 14700,
  'img': 'course_design.jpg',
  'title': 'Design Elements & Styling',
  'label': 'Specialist course · 7 modules',
  'sub': 'Make every room look right, with animated lessons.',
  'meta': 'The craft beneath great staging: proportion, layout, rugs, art, light, colour and the finishing touches.',
  'overview': 'Good staging rests on a handful of design rules, and this course teaches them clearly. In seven short '
              'modules you will learn how to judge proportion and scale, plan a layout and walkways, size and place '
              'rugs and coffee tables, hang art at the right height, light a room in three layers, choose a simple '
              'colour palette, dress a bed and finish a room with confident final styling. Key measurements are shown '
              'as animated diagrams, so you can see exactly where each piece goes. Every module ends with a real '
              'project photograph that shows the rules at work. All measurements are given in centimetres.',
  'learn': ['Proportion, scale and visual weight',
            "Layout and flow, with a bird's-eye floor plan animation",
            'Rug and coffee table sizes and distances',
            'Where to hang art, and how to build a gallery wall',
            'Three layers of light and a simple colour palette',
            'How to dress a bed, layer by layer'],
  'who': ['Home stagers who want to sharpen their eye and their measurements',
          'Interior designers and decorators who want a clear staging checklist',
          'Homeowners and property investors preparing a home for sale or rent'],
  'included': ['7 narrated modules with animated diagrams',
               'Measurements cheat sheet and room layout planner',
               'Rug and table worksheet and art-hanging worksheet',
               'Bed and styling checklist and a student workbook'],
  'cta': 'Start Design Elements & Styling',
  'external': 'https://homestagingeducationcentre.co.uk/courses/design-elements-and-styling',
  'currency': '£'}]
for _c in EXTERNAL:
    _c["provider"] = HSEC_NAME
    _c["faq_extra"] = HSEC_FAQ
COURSES = COURSES + EXTERNAL
BY_SLUG = {c["slug"]: c for c in COURSES}

ABOUT = ("GAPHS, the Global Association of Professional Home Stagers, unites professionals, key partners and affiliates across continents "
         "to elevate the Home Staging industry through advocacy, education and collaboration. GAPHS is a non-profit association registered "
         "in Switzerland and a direct member of FIABCI, the International Real Estate Federation.")

ABOUT_HSEC = ("The Home Staging Education Centre teaches home staging online, from a first introduction to running a profitable "
              "business. It was founded by Paloma Harrington, an award-winning interior designer and home staging master, "
              "and Vice President of GAPHS.")

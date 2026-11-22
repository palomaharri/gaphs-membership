"""The wording and layout of the emails members receive."""
from html import escape

BROWN, CREAM, INK, GOLD = "#1A1A1A", "#F5F1E8", "#2A2A2A", "#B8963E"

INCLUDED = ["The Library: courses, video guides, the Atelier Series guides and templates",
            "The members' forum, to swap ideas with professionals across countries",
            "Webinars and continuing professional development",
            "Connection with local chapters and our real estate partners"]
PRO_EXTRA = ["A page in the GAPHS member directory, so clients and agents can find you",
             "Use of GAPHS member logo"]


def _first(user):
    return (user["name"] or "").strip().split(" ")[0] or "there"


def _layout(subject, inner):
    return ('<!doctype html><html><body style="margin:0;padding:0;background:%s">'
            '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" style="background:%s;padding:32px 12px"><tr><td align="center">'
            '<table role="presentation" width="580" cellpadding="0" cellspacing="0" style="max-width:580px;width:100%%;background:#FFFFFF;border-radius:8px;overflow:hidden;font-family:Helvetica,Arial,sans-serif">'
            '<tr><td style="background:#1A1A1A;padding:26px 36px;color:#B8963E;font-size:12px;letter-spacing:0.22em;text-transform:uppercase">Global Association of Professional Home Stagers</td></tr>'
            '<tr><td style="padding:36px 36px 8px"><h1 style="margin:0 0 24px;font-family:Georgia,serif;font-weight:400;font-size:27px;line-height:1.25;color:%s">%s</h1>%s</td></tr>'
            '<tr><td style="padding:20px 36px 30px;font-size:13px;line-height:1.5;color:#888888;border-top:1px solid #E8E2D4">'
            'Global Association of Professional Home Stagers &middot; info@gaphs.org</td></tr></table></td></tr></table></body></html>'
            % (CREAM, CREAM, BROWN, escape(subject), inner))


def _p(text):
    return '<p style="margin:0 0 18px;font-size:16px;line-height:1.65;color:%s">%s</p>' % (INK, escape(text))


def _list(items):
    lis = "".join('<li style="margin:0 0 8px">%s</li>' % escape(i) for i in items)
    return '<ul style="margin:0 0 20px;padding-left:20px;font-size:16px;line-height:1.55;color:%s">%s</ul>' % (INK, lis)


def _h(text):
    return ('<p style="margin:26px 0 10px;font-size:12px;letter-spacing:0.14em;text-transform:uppercase;color:%s;font-weight:700">%s</p>'
            % (BROWN, escape(text)))


def _button(label, url):
    return ('<a href="%s" style="background:%s;color:%s;text-decoration:none;padding:12px 22px;border-radius:2px;font-size:13px;'
            'letter-spacing:1px;text-transform:uppercase;font-weight:600;display:inline-block;margin:0 10px 10px 0">%s</a>' % (escape(url), GOLD, BROWN, escape(label)))


SIGN_NAME = "The GAPHS Board"
SIGN_LINE = "Global Association of Professional Home Stagers"


def _signature(site):
    return ('<p style="margin:26px 0 0;font-size:16px;color:%s">Kind regards,</p>'
            '<p style="margin:8px 0 2px;font-family:Georgia,\'Times New Roman\',serif;font-style:italic;font-size:26px;color:%s">%s</p>'
            '<p style="margin:0 0 22px;font-size:13px;letter-spacing:1px;color:#888888">%s</p>' % (INK, BROWN, SIGN_NAME, SIGN_LINE))


def _plan_items(user):
    if user["plan"] == "professional":
        return INCLUDED + PRO_EXTRA
    return INCLUDED + (PRO_EXTRA[:1] if user["founding"] else [])


def welcome(user, site):
    first = _first(user)
    subject = "Welcome to the Global Association of Professional Home Stagers"
    pro = user["plan"] == "professional" or bool(user["founding"])
    inner = (_p("Dear %s," % first)
             + _p("On behalf of the Board, it is a pleasure to welcome you to the Global Association of Professional Home Stagers. "
                  "You join a global network of professionals, educators and partners committed to upholding and advancing "
                  "the standards of Home Staging worldwide.")
             + _h("What your membership includes") + _list(_plan_items(user))
             + _h("Recommended first steps")
             + _p("1. Complete your business page. " + ("This is the page clients and real estate professionals see in the directory; we recommend adding your logo, a short profile and photographs of your work."
                   if pro else "Please ensure your details are complete and up to date."))
             + _p("2. Explore the Library. All courses and resources are available to you for the duration of your membership.")
             + _p("3. Introduce yourself in the members&rsquo; forum and connect with colleagues around the world.")
             + '<p style="margin:8px 0 6px">' + _button("Update my profile page", site + "/dashboard/profile")
             + _button("Courses and resources", site + "/library") + _button("Visit the forum", site + "/forum") + "</p>"
             + _p("For any questions, please contact the Association at info@gaphs.org.")
             + _signature(site))
    text = ("Dear %s,\n\nOn behalf of the Board, it is a pleasure to welcome you to the Global Association of Professional Home Stagers. "
            "You join a global network of professionals, educators and partners committed to upholding and advancing the standards of Home Staging worldwide.\n\n"
            "WHAT YOUR MEMBERSHIP INCLUDES\n%s\n\n"
            "RECOMMENDED FIRST STEPS\n1. Complete your profile page: %s/dashboard/profile\n2. Explore the Library: %s/library\n"
            "3. Introduce yourself in the members' forum: %s/forum\n\n"
            "For any questions, please contact the Association at info@gaphs.org.\n\nKind regards,\nThe GAPHS Board\nGlobal Association of Professional Home Stagers\n"
            % (first, "\n".join("- " + i for i in _plan_items(user)), site, site, site))
    return subject, text, _layout("Welcome to GAPHS", inner)


def renewal(user, end, site):
    first = _first(user)
    when = end.strftime("%d %B %Y").lstrip("0")
    plan = "Member" if user["plan"] == "professional" else "Associate"
    subject = "Your GAPHS membership renews on %s" % when
    keep = ["All courses in the Library, together with new content as it is published",
            "The members' forum, for professional exchange with colleagues",
            "Webinars and the resources library"]
    if user["plan"] == "professional":
        keep.insert(3, "Your listing in the GAPHS global directory")
    inner = (_p("Dear %s," % first)
             + _p("Your %s membership renews automatically on %s, using the card you have on file. No action is required." % (plan, when))
             + _p("We invite you to make full use of the benefits of your membership in the meantime.")
             + _h("Your membership includes") + _list(keep)
             + _h("Member resources") + _p("The Library, the members' forum and the GAPHS webinars remain available to you throughout your membership.")
             + '<p style="margin:8px 0 6px">' + _button("Courses and resources", site + "/library") + _button("Visit the forum", site + "/forum") + "</p>"
             + _p("To update your card or manage your membership, visit your account page: %s/dashboard" % site)
             + _p("Thank you for your continued membership of GAPHS.")
             + _signature(site))
    text = ("Dear %s,\n\nYour %s membership renews automatically on %s, using the card you have on file. No action is required.\n\n"
            "We invite you to make full use of the benefits of your membership in the meantime.\n\n"
            "YOUR MEMBERSHIP INCLUDES\n%s\n\nMEMBER RESOURCES\nLibrary: %s/library\nThe forum: %s/forum\n\n"
            "To update your card or manage your membership: %s/dashboard\n\nThank you for your continued membership of GAPHS.\n\n"
            "Kind regards,\nThe GAPHS Board\nGlobal Association of Professional Home Stagers\n"
            % (first, plan, when, "\n".join("- " + i for i in keep), site, site, site))
    return subject, text, _layout("Your membership renews on %s" % when, inner)

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
    return ('<p style="margin:26px 0 0;font-size:16px;color:%s">With warm regards,</p>'
            '<p style="margin:8px 0 2px;font-family:Georgia,\'Times New Roman\',serif;font-style:italic;font-size:26px;color:%s">%s</p>'
            '<p style="margin:0 0 22px;font-size:13px;letter-spacing:1px;color:#888888">%s</p>' % (INK, BROWN, SIGN_NAME, SIGN_LINE))


def _plan_items(user):
    if user["plan"] == "professional":
        return INCLUDED + PRO_EXTRA
    return INCLUDED + (PRO_EXTRA[:1] if user["founding"] else [])


def welcome(user, site):
    first = _first(user)
    subject = "Welcome to GAPHS, %s" % first
    pro = user["plan"] == "professional" or bool(user["founding"])
    inner = (_p("Dear %s," % first)
             + _p("Welcome to the Global Association of Professional Home Stagers. You are now part of a global movement of "
                  "professionals, educators and partners committed to raising the standard of Home Staging across continents, "
                  "cultures and markets.")
             + _h("What your membership includes") + _list(_plan_items(user))
             + _h("Three things to do first")
             + _p("1. Complete your business page. " + ("It is what clients and agents see in the directory, so add your logo, a short bio and photos of your work."
                   if pro else "Keep your details up to date so we know who you are."))
             + _p("2. Explore the courses and resources. Start wherever suits you best, and come back to them whenever you like.")
             + _p("3. Say hello in the forum. Introduce yourself and tell us about your business. Members love meeting new faces.")
             + '<p style="margin:8px 0 6px">' + _button("Update my profile page", site + "/dashboard/profile")
             + _button("Courses and resources", site + "/library") + _button("Visit the forum", site + "/forum") + "</p>"
             + _p("If you need anything at all, write to us at info@gaphs.org. We are always happy to help.")
             + _signature(site))
    text = ("Dear %s,\n\nWelcome to the Global Association of Professional Home Stagers. You are now part of a global movement of "
            "professionals, educators and partners committed to raising the standard of Home Staging across continents, cultures and markets.\n\n"
            "WHAT YOUR MEMBERSHIP INCLUDES\n%s\n\n"
            "THREE THINGS TO DO FIRST\n1. Update your profile page: %s/dashboard/profile\n2. Explore the courses and resources: %s/library\n"
            "3. Say hello in the forum: %s/forum\n\n"
            "If you need anything, write to us at info@gaphs.org.\n\nWith warm regards,\nThe GAPHS Board\nGlobal Association of Professional Home Stagers\n"
            % (first, "\n".join("- " + i for i in _plan_items(user)), site, site, site))
    return subject, text, _layout("A warm welcome, %s" % first, inner)


def renewal(user, end, site):
    first = _first(user)
    when = end.strftime("%d %B %Y").lstrip("0")
    plan = "Member" if user["plan"] == "professional" else "Associate"
    subject = "Your membership renews on %s. Here is what you keep." % when
    keep = ["Every course in the library, plus new content as it is added",
            "The forum, where fellow members share projects, ideas and advice",
            "Webinars and the resources library"]
    if user["plan"] == "professional":
        keep.insert(3, "Your directory listing, putting your business in front of clients looking for a stager")
    inner = (_p("Dear %s," % first)
             + _p("Your %s membership renews automatically on %s, using the card you have on file. There is nothing you need to do." % (plan, when))
             + _p("Before then, we would love you to get the most from your membership. Home staging is a stronger business when you are "
                  "learning, sharing and connecting with others who do the same work.")
             + _h("What stays yours") + _list(keep)
             + _h("Make the most of it") + _p("Pick up a course you have not finished, browse the latest resources, or drop into the forum and "
                                              "start a conversation with fellow members. It is the best way to get new ideas and referrals.")
             + '<p style="margin:8px 0 6px">' + _button("Courses and resources", site + "/library") + _button("Visit the forum", site + "/forum") + "</p>"
             + _p("To update your card or manage your membership, visit your account page: %s/dashboard" % site)
             + _p("Thank you for being part of GAPHS. We are glad to have you.")
             + _signature(site))
    text = ("Dear %s,\n\nYour %s membership renews automatically on %s, using the card you have on file. There is nothing you need to do.\n\n"
            "Before then, get the most from it. Home staging is a stronger business when you are learning, sharing and connecting with others who do the same work.\n\n"
            "WHAT STAYS YOURS\n%s\n\nMAKE THE MOST OF IT\nCourses and resources: %s/library\nThe forum: %s/forum\n\n"
            "To update your card or manage your membership: %s/dashboard\n\nThank you for being part of GAPHS.\n\n"
            "With warm regards,\nThe GAPHS Board\nGlobal Association of Professional Home Stagers\n"
            % (first, plan, when, "\n".join("- " + i for i in keep), site, site, site))
    return subject, text, _layout("Your membership renews on %s" % when, inner)

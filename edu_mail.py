"""Access email sent to buyers: clear wording, one labelled button per link."""
import db


def send_access_email(email, title, tk, site=None):
    import helpers
    import edu as E
    user, set_token = E._ensure_account(email)
    if user:
        db.run("UPDATE purchases SET user_id = ? WHERE token = ? AND user_id IS NULL", (user["id"], tk))
    if not site:
        site = ("https://" + E.edu_host()) if E.is_edu() else helpers.site_url()
    on_edu = E.edu_host() in site
    name = E.EDU_NAME if on_edu else E.HSA_NAME
    courses_url = site + "/my-courses"
    subject = "Your access: " + title
    if set_token:
        set_url = site + "/reset/" + set_token
        text = ("Thank you for your purchase of %s.\n\n"
                "To watch it, first choose your password. This link works for 7 days: %s\n\n"
                "After that, log in any time with this email address and open My courses: %s\n\n"
                "If the password link has expired, open the login page and choose Forgot your password.\n\n%s"
                % (title, set_url, courses_url, name))
        labels = ["Choose my password", "Go to my courses"]
    else:
        text = ("Thank you for your purchase of %s.\n\n"
                "It is ready to watch. Log in with the email address you used to buy and open My courses: %s\n\n%s"
                % (title, courses_url, name))
        labels = ["Go to my courses"]
    html = helpers.email_html(subject, text)
    if on_edu:
        html = (html.replace(E.HSA_NAME, E.EDU_NAME).replace("#1A1A1A", "#3F4A3C")
                .replace("#1A1A1A", "#9C7D2F").replace("#F5F1E8", "#F6F1E9"))
    for lab in labels:
        html = html.replace(">Open my account<", ">%s<" % lab, 1)
    helpers.send_mail(email, subject, text, html)

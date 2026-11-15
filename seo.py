"""robots.txt, sitemap.xml and favicon. Registered from app.py with seo.init(app)."""
from flask import Response, redirect, request, url_for

import courses_data
import db


def _base():
    u = request.url_root.rstrip("/")
    return u if "localhost" in u or "127.0.0.1" in u else u.replace("http://", "https://", 1)


def init(app):
    @app.route("/robots.txt")
    def robots_txt():
        base = _base()
        body = ("User-agent: *\nDisallow: /admin\nDisallow: /dashboard\nDisallow: /purchase/\nDisallow: /simulate/\n"
                "Disallow: /files/\nDisallow: /login\nDisallow: /forum\nSitemap: %s/sitemap.xml\n" % base)
        return Response(body, mimetype="text/plain")

    @app.route("/sitemap.xml")
    def sitemap_xml():
        base = _base()
        paths = ["/", "/courses", "/library", "/directory", "/join", "/contact", "/terms", "/privacy", "/blog"]
        paths += ["/courses/" + c["slug"] for c in courses_data.COURSES]
        try:
            for r in db.q("SELECT id FROM content WHERE published = 1 ORDER BY id"):
                paths.append("/shop/%d" % r["id"])
            for r in db.q("SELECT slug FROM blog_posts WHERE status = 'published'"):
                paths.append("/blog/" + r["slug"])
            for r in db.q("SELECT slug FROM profiles WHERE slug != '' AND published = 1 AND approved = 1"):
                paths.append("/directory/" + r["slug"])
        except Exception:
            pass
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        xml += "".join("<url><loc>%s%s</loc></url>\n" % (base, p) for p in paths) + "</urlset>\n"
        return Response(xml, mimetype="application/xml")

    @app.route("/favicon.ico")
    def favicon_ico():
        return redirect(url_for("static", filename="icons/icon-192.png"), code=302)

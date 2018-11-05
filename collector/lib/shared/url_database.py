# URL database management.  Shared among all the sources and the
# scraper controller.
#
# Copyright © 2014 Zack Weinberg
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# There is NO WARRANTY.

import psycopg2
import psycopg2.extras
import re
import urllib.parse

from shared.util import canon_url_syntax

def ensure_database(args):
    """Ensure that the database specified by args.database exists and has
       an up-to-date schema.  `args` would normally be an
       argparse.Namespace object, but we don't care as long as
       "database" and "schema" are attributes (nor do we care how the
       argument actually shows up on the command line).

       args.database is expected to be a "libpq connection string" or
       postgres:// URL.  If it appears to be neither of those, it is
       taken as just the name of the database.
    """

    dbstr = args.database
    if '=' not in dbstr and '://' not in dbstr:
        dbstr = "dbname="+dbstr

    db = psycopg2.connect(dbstr,
                          cursor_factory=psycopg2.extras.NamedTupleCursor)

    # Select the appropriate schema.
    with db, db.cursor() as c:
        c.execute("SET search_path TO " + args.schema)

    return db

def add_url_string(db, url):
    """Add an URL to the url_strings table for DB, if it is not already there.
       Returns a pair (id, url) where ID is the table identifier, and URL
       is the URL as returned by canon_url_syntax()."""

    url = canon_url_syntax(url)

    # Accept either a database connection or a cursor.
    if hasattr(db, 'cursor'):
        cur = db.cursor()
    elif hasattr(db, 'execute'):
        cur = db
    else:
        raise TypeError("'db' argument must be a connection or cursor, not "
                        + type(db))

    # Wrap the operation below in a savepoint, so that if it aborts
    # (for instance, if the URL is too long) any outer transaction is
    # not ruined.
    try:
        cur.execute("SAVEPOINT url_string_insertion")

        # Theoretically this could be done in one query with WITH and
        # INSERT ... RETURNING, but it is convoluted enough that I don't
        # believe it will be faster.  Alas.
        cur.execute("SELECT id FROM url_strings WHERE url = %s", (url,))
        row = cur.fetchone()
        if row is not None:
            id = row[0]
        else:
            cur.execute("INSERT INTO url_strings(id, url) VALUES(DEFAULT, %s) "
                        "RETURNING id", (url,))
            id = cur.fetchone()[0]
        return (id, url)

    except:
        cur.execute("ROLLBACK TO SAVEPOINT url_string_insertion")
        raise

    finally:
        cur.execute("RELEASE SAVEPOINT url_string_insertion")

# Subroutines and REs for add_site:

def to_https(spliturl):
    return urllib.parse.SplitResult("https",
                                    spliturl.netloc,
                                    spliturl.path,
                                    spliturl.query,
                                    spliturl.fragment)

def to_siteroot(spliturl):
    return urllib.parse.SplitResult(spliturl.scheme,
                                    spliturl.netloc,
                                    "/",
                                    spliturl.query,
                                    spliturl.fragment)

def add_www(spliturl):
    if "@" in spliturl.netloc:
        (auth, rest) = spliturl.netloc.split("@", 1)
        netloc = auth + "@www." + rest
    else:
        netloc = "www." + spliturl.netloc

    return urllib.parse.SplitResult(spliturl.scheme,
                                    netloc,
                                    spliturl.path,
                                    spliturl.query,
                                    spliturl.fragment)

no_www_re = re.compile(r"^(?:\d+\.\d+\.\d+\.\d+$|\[[\dA-Fa-f:]+\]$|www\.)")

def add_site(db, site, http_only=False, www_only=False):
    """Add a site to the url_strings table for DB, if it is not already
       there.  Returns a list of pairs [(id1, url1), (id2, url2), ...]
       comprising all URLs chosen to represent the site.

       A "site" is a partial URL, from which the scheme and possibly a
       leading "www." have been stripped.  There may or may not be a
       path component. We reconstruct up to eight possible URLs from
       this partial URL:

         http://       site (/path)
         https://      site (/path)
         http://  www. site (/path)
         https:// www. site (/path)

       If there was a path component, we consider URLs both with and
       without that path.  If 'site' already starts with 'www.', or if
       it is an IP address, we do not prepend 'www.'

       This scheme won't do us any good if the actual content people
       are loading is neither at the name in the list nor at www. the
       name in the list; for instance, akamaihd.net appears highly in
       Alexa's site ranking, but neither akamaihd.net nor www.akamaihd.net
       has any A records, because, being a CDN, all of the actual
       content is on servers named SOMETHINGELSE.akamaihd.net, and
       you're not expected to notice that the domain even exists.
       But there's nothing we can do about that.

       If http_only is True, https urls are not added.
       If www_only is true, urls without 'www.' are not added.
    """

    parsed = canon_url_syntax("http://" + site, want_splitresult=True)

    assert parsed.path != ""
    if parsed.path != "/":
        root = to_siteroot(parsed)
        need_path = True
        with_path = parsed
    else:
        root = parsed
        need_path = False

    host = root.hostname
    if no_www_re.match(host):
        need_www = False
        with_www = root
        if need_path:
            with_www_path = with_path
    else:
        need_www = True
        with_www = add_www(root)
        if need_path:
            with_www_path = add_www(with_path)

    urls = [with_www.geturl()]
    if not http_only:
        urls.append(to_https(with_www).geturl())

    if need_www and not www_only:
        urls.append(root.geturl())
        if not http_only:
            urls.append(to_https(root).geturl())

    if need_path:
        urls.append(with_www_path.geturl())
        if not http_only:
            urls.append(to_https(with_www_path).geturl())

        if need_www and not www_only:
            urls.append(with_path.geturl())
            if not http_only:
                urls.append(to_https(with_path).geturl())

    return [ add_url_string(db, url) for url in urls ]

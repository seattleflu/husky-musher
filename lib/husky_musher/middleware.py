"""
WSGI middleware.
"""


class ForwardedRemoteUser:
    """
    WSGI middleware to set ``REMOTE_USER`` from the ``Forwarded-Remote-User`` HTTP
    header.

    This is useful in a reverse proxy situation, but you *must* make sure that:

      1. No one except localhost can make requests directly to your backend (i.e.
         your WSGI app).  Currently this middleware also checks that
         ``REMOTE_ADDR`` is ``127.0.0.1``.

      2. Your reverse proxy doesn't let requests specify their own value for
         ``Forwarded-Remote-User``.

    An example of applying this middleware to a Flask app:

    .. code-block: python

        app = Flask(__name__)
        app.wsgi_app = ForwardedRemoteUser(app.wsgi_app)

    The remote user will then be provided (if available) in Flask's
    ``request.remote_user`` request object property.
    """
    header_name = "Forwarded-Remote-User"
    trusted_remote_addrs = frozenset({"127.0.0.1"})

    def __init__(self, app):
        self.app = app

    @property
    def _header_environ_key(self):
        return "HTTP_" + self.header_name.upper().replace("-", "_")

    def __call__(self, environ, start_response):
        if environ.get("REMOTE_ADDR") in self.trusted_remote_addrs:
            environ["REMOTE_USER"] = environ.pop(self._header_environ_key, None)

        return self.app(environ, start_response)


# If running this module as a script, start a little Flask dev server for
# manual testing with the middleware applied.
if __name__ == "__main__":
    from flask import Flask, request, json

    app = Flask(__name__)
    app.wsgi_app = ForwardedRemoteUser(app.wsgi_app)

    @app.route("/")
    def info():
        return json.jsonify(
            remote_user = request.remote_user,
            remote_addr = request.remote_addr,
            headers     = list(request.headers.items()))

    app.run()

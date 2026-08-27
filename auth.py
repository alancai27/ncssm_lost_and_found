"""
Sign in with Google.

Only @ncssm.edu accounts can post items or mark them returned. Browsing stays
open (set REQUIRE_LOGIN_TO_VIEW=1 to close that too).

This is the OpenID Connect authorization-code flow with PKCE against Google,
which is what NCSSM accounts run on. The domain restriction is enforced
server-side against the verified email Google returns -- the `hd` parameter
below only pre-filters Google's own account chooser and is not a security
control, so nothing here relies on it.
"""

import base64
import functools
import hashlib
import os
import secrets
from urllib.parse import urlencode, urlparse

import requests
from flask import flash, redirect, request, session, url_for

ALLOWED_DOMAIN = os.environ.get("ALLOWED_EMAIL_DOMAIN", "ncssm.edu").strip().lower()
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
REQUIRE_LOGIN_TO_VIEW = os.environ.get("REQUIRE_LOGIN_TO_VIEW") == "1"

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPE = "openid email profile"
TIMEOUT = 20


class AuthError(RuntimeError):
    pass


def configured():
    """True once a Google OAuth client is wired up."""
    return bool(CLIENT_ID and CLIENT_SECRET)


# Kept as a separate name so templates read clearly; there is only one method.
enabled = configured


def current_user():
    return session.get("user")


def is_allowed_email(email):
    email = (email or "").strip().lower()
    if email.count("@") != 1:
        return False
    local, _, domain = email.partition("@")
    return bool(local) and domain == ALLOWED_DOMAIN


# --------------------------------------------------------------------------
# Decorators
# --------------------------------------------------------------------------

def login_required(view):
    """Gate a route on a verified @ALLOWED_DOMAIN Google session."""

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if current_user():
            return view(*args, **kwargs)
        if not configured():
            flash(
                "Google sign-in is not set up on this server, so posting is "
                "disabled. See the README section on Google sign-in.",
                "error",
            )
            return redirect(url_for("index"))
        return redirect(url_for("login", next=safe_next(request.full_path)))

    return wrapped


def view_login_required(view):
    """Only gates browsing if REQUIRE_LOGIN_TO_VIEW is on."""

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not REQUIRE_LOGIN_TO_VIEW or current_user():
            return view(*args, **kwargs)
        return login_required(view)(*args, **kwargs)

    return wrapped


# --------------------------------------------------------------------------
# Flow
# --------------------------------------------------------------------------

def safe_next(target):
    """Only ever redirect back to a path on this site, never an absolute URL."""
    if not target:
        return None
    target = target.rstrip("?")
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/"):
        return None
    return target


def _pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def begin(redirect_uri, next_url=None):
    """Return the Google URL to send the browser to."""
    if not configured():
        raise AuthError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are not set.")

    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()

    session["oauth_state"] = state
    session["oauth_verifier"] = verifier
    session["oauth_next"] = safe_next(next_url)

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        # Pre-filters the account chooser to school accounts. A convenience,
        # not a restriction -- the real check is on the email below.
        "hd": ALLOWED_DOMAIN,
        "prompt": "select_account",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def complete(redirect_uri):
    """
    Validate the callback, exchange the code, and return the user dict.
    Raises AuthError with a message safe to show the user.
    """
    if request.args.get("error"):
        raise AuthError(request.args.get("error_description") or request.args["error"])

    expected = session.pop("oauth_state", None)
    verifier = session.pop("oauth_verifier", None)
    if not expected or not secrets.compare_digest(expected, request.args.get("state", "")):
        raise AuthError("That sign-in link expired or was tampered with. Try again.")

    code = request.args.get("code")
    if not code:
        raise AuthError("Google did not return an authorization code.")

    token_resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code_verifier": verifier or "",
        },
        headers={"Accept": "application/json"},
        timeout=TIMEOUT,
    )
    if token_resp.status_code != 200:
        detail = ""
        try:
            detail = token_resp.json().get("error_description") or token_resp.json().get("error", "")
        except ValueError:
            pass
        raise AuthError(
            f"Google rejected the token exchange ({token_resp.status_code}"
            f"{': ' + detail if detail else ''}). "
            f"Usually the client secret is wrong, or the redirect URI here does "
            f"not exactly match the one registered in Google Cloud Console."
        )

    access_token = token_resp.json().get("access_token")
    if not access_token:
        raise AuthError("Google did not return an access token.")

    info_resp = requests.get(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=TIMEOUT,
    )
    if info_resp.status_code != 200:
        raise AuthError(f"Could not read your Google profile ({info_resp.status_code}).")

    info = info_resp.json()
    email = (info.get("email") or "").strip().lower()

    if not info.get("email_verified", False):
        raise AuthError("That Google account's email address is not verified.")

    if not is_allowed_email(email):
        raise AuthError(
            f"{email or 'That account'} is not an @{ALLOWED_DOMAIN} address. "
            f"Sign in with your school Google account."
        )

    return {
        "email": email,
        "name": (info.get("name") or email.split("@")[0]).strip(),
    }


def sign_in(user):
    session["user"] = user
    session.permanent = True


def sign_out():
    for key in ("user", "oauth_state", "oauth_verifier", "oauth_next"):
        session.pop(key, None)


def pop_next():
    return session.pop("oauth_next", None)


def warn_if_insecure():
    """Called at boot so a misconfigured deployment is loud, not silent."""
    if not configured():
        return [
            "Google sign-in is not configured: posting and claiming are "
            "disabled. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
        ]
    return []

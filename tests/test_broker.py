"""token_mint's broker layer: name the failure instead of dumping an opaque blob.

The 2026-08-03 outage took ten days to notice and a dozen probes to diagnose
because a failed mint said nothing useful. The broker usually states the reason;
these tests pin that we read it, and that we don't over-claim when we can't.
"""
import contextlib
import json

import pytest

import token_mint


def _session(replies):
    """Replace broker_session with one that returns scripted replies in order."""
    @contextlib.contextmanager
    def fake():
        it = iter(replies)

        def call(command, **params):
            return next(it)
        yield call
    return fake


# --- refusal classification ------------------------------------------------

@pytest.mark.parametrize("code", ["interaction_required", "interactive_required",
                                  "token_expired", "invalid_grant"])
def test_needs_reenroll_codes_say_so(code):
    """These four are the broker's way of saying a human must sign in. Anything
    that maps to them must point at the runbook, not leave the reader guessing."""
    reason = token_mint.refusal({"error": {"context": f"AAD said {code} here"}})
    assert reason is not None
    assert "re-enroll" in reason
    assert "RUNBOOK-token-recovery" in reason


def test_unknown_error_is_reported_but_not_diagnosed():
    """An unfamiliar code must not claim a remedy it doesn't have — it gets
    reported verbatim so the next reader has the broker's own words."""
    reason = token_mint.refusal({"error": {"context": "Code: 'invalid_request'"}})
    assert reason is not None
    assert "invalid_request" in reason
    assert "re-enroll" not in reason


def test_success_is_not_a_refusal():
    assert token_mint.refusal({"cookieItems": [{"cookieContent": "abc"}]}) is None


def test_nested_broker_token_response_error_is_found():
    """Real refusals arrive wrapped in brokerTokenResponse, not at the top."""
    reason = token_mint.refusal(
        {"brokerTokenResponse": {"error": {"context": "token_expired"}}})
    assert reason is not None and "re-enroll" in reason


# --- prt_cookie ------------------------------------------------------------

def test_prt_cookie_reads_the_brokers_key_name(monkeypatch):
    """The broker sends `cookieName`. Reading `name` worked only by accident of
    the fallback matching; a different cookie name would have injected the wrong
    header and looked exactly like a compliance lapse."""
    monkeypatch.setattr(token_mint, "broker_session", _session([
        {"accounts": [{"username": "u@example.com"}]},
        {"cookieItems": [{"cookieName": "x-ms-SomethingElse",
                          "cookieContent": "COOKIE"}]},
    ]))
    name, val = token_mint.prt_cookie()
    assert name == "x-ms-SomethingElse"
    assert val == "COOKIE"


def test_prt_cookie_falls_back_when_name_absent(monkeypatch):
    monkeypatch.setattr(token_mint, "broker_session", _session([
        {"accounts": [{"username": "u@example.com"}]},
        {"cookieItems": [{"cookieContent": "COOKIE"}]},
    ]))
    name, _ = token_mint.prt_cookie()
    assert name == "x-ms-RefreshTokenCredential"


def test_prt_cookie_failure_explains_itself(monkeypatch):
    """No cookie + a known refusal code => the message says re-enroll, rather
    than printing the raw envelope the log used to end up full of."""
    monkeypatch.setattr(token_mint, "broker_session", _session([
        {"accounts": [{"username": "u@example.com"}]},
        {"error": {"context": "token_expired"}},
    ]))
    with pytest.raises(SystemExit) as e:
        token_mint.prt_cookie()
    assert "re-enroll" in str(e.value)


# --- broker graph token (used only by the compliance probe) -----------------

def test_broker_graph_token_returns_the_access_token(monkeypatch):
    monkeypatch.setattr(token_mint, "broker_session", _session([
        {"accounts": [{"username": "u@example.com"}]},
        {"brokerTokenResponse": {"accessToken": "header.payload.sig"}},
    ]))
    assert token_mint.broker_graph_token() == "header.payload.sig"


def test_broker_graph_token_raises_with_the_reason(monkeypatch):
    monkeypatch.setattr(token_mint, "broker_session", _session([
        {"accounts": [{"username": "u@example.com"}]},
        {"brokerTokenResponse": {"error": {"context": "invalid_grant"}}},
    ]))
    with pytest.raises(RuntimeError, match="re-enroll"):
        token_mint.broker_graph_token()


# --- jwt ------------------------------------------------------------------

def test_jwt_claims_roundtrip():
    import base64
    payload = base64.urlsafe_b64encode(
        json.dumps({"aud": "https://ic3.teams.office.com",
                    "deviceid": "abc"}).encode()).decode().rstrip("=")
    claims = token_mint.jwt_claims(f"h.{payload}.s")
    assert claims["aud"] == "https://ic3.teams.office.com"
    assert claims["deviceid"] == "abc"


def test_jwt_claims_never_raises():
    """Called on scraped localStorage values that may not be JWTs at all."""
    assert token_mint.jwt_claims("not-a-jwt") == {}
    assert token_mint.jwt_claims("") == {}

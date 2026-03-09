import json
import os
import uuid

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from pylti1p3.cookie import CookieService
from pylti1p3.message_launch import MessageLaunch
from pylti1p3.oidc_login import OIDCLogin
from pylti1p3.request import Request as LTIRequest
from pylti1p3.tool_config import ToolConfDict

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AGLMS API",
    description="Adaptive Gamified Learning Management System - CS6460 Spring 2026",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=True)


# ── pylti1p3 FastAPI adapters ─────────────────────────────────────────────────

class FastAPILTIRequest(LTIRequest):
    def __init__(self, request: Request, session: dict, body: dict = None):
        super().__init__()
        self._request = request
        self._session = session
        self._body = body or {}

    @property
    def session(self):
        return self._session

    def get_param(self, key: str):
        if self._request.method == "GET":
            return self._request.query_params.get(key)
        return self._body.get(key)

    def is_secure(self) -> bool:
        return self._request.url.scheme == "https"


class FastAPICookieService(CookieService):
    def __init__(self, session: dict):
        self._session = session

    def get_cookie(self, name: str):
        return self._session.get(name)

    def set_cookie(self, name: str, value, exp=3600):
        self._session[name] = value


class FastAPIMessageLaunch(MessageLaunch):
    pass


class FastAPIOIDCLogin(OIDCLogin):
    def get_redirect(self, url: str):
        return RedirectResponse(url=url, status_code=302)

    def set_redirect_url_cookie(self, cookie_name: str, val: str):
        pass


# ── Tool config loader ────────────────────────────────────────────────────────

def get_tool_conf() -> ToolConfDict:
    """Load LTI config from lti_config.json and build a ToolConfDict with inline keys."""
    path = os.path.join(os.path.dirname(__file__), "lti_config.json")
    with open(path) as f:
        raw = json.load(f)

    # Build config dict for ToolConfDict (no file paths needed)
    config = {}
    for iss, entries in raw.items():
        config[iss] = []
        for entry in entries:
            config[iss].append({
                "default":        entry.get("default", True),
                "client_id":      entry["client_id"],
                "auth_login_url": entry["auth_login_url"],
                "auth_token_url": entry["auth_token_url"],
                "auth_audience":  entry.get("auth_audience"),
                "key_set_url":    entry.get("key_set_url"),
                "key_set":        entry.get("key_set"),
                "deployment_ids": entry.get("deployment_ids", []),
            })

    tool_conf = ToolConfDict(config)

    # Inject keys directly — no file paths required
    for iss, entries in raw.items():
        for entry in entries:
            client_id   = entry["client_id"]
            private_key = entry.get("private_key", "")
            public_key  = entry.get("public_key", "")
            if private_key:
                tool_conf.set_private_key(iss, private_key, client_id=client_id)
            if public_key:
                tool_conf.set_public_key(iss, public_key, client_id=client_id)

    return tool_conf


# ── Health & Root ─────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "AGLMS API", "version": "0.1.0"}


@app.get("/")
def root():
    return {"message": "AGLMS API is running", "docs": "/docs", "health": "/health"}


# ── LTI 1.3 Endpoints ─────────────────────────────────────────────────────────

@app.get("/lti/jwks")
def jwks():
    return JSONResponse(get_tool_conf().get_jwks())


@app.get("/lti/login")
@app.post("/lti/login")
async def lti_login(request: Request):
    session = request.session
    body = {}
    if request.method == "POST":
        form = await request.form()
        body = dict(form)

    lti_request = FastAPILTIRequest(request, session, body)
    cookie_service = FastAPICookieService(session)

    try:
        oidc = FastAPIOIDCLogin(lti_request, get_tool_conf(), cookie_service=cookie_service)
        return oidc.enable_check_cookies().redirect("https://api.compcode.cloud/lti/launch")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OIDC login error: {str(e)}")


@app.post("/lti/launch")
async def lti_launch(request: Request):
    session = request.session
    form = await request.form()
    body = dict(form)

    lti_request = FastAPILTIRequest(request, session, body)
    cookie_service = FastAPICookieService(session)

    try:
        launch = FastAPIMessageLaunch(lti_request, get_tool_conf(), cookie_service=cookie_service)
        launch_data = launch.get_launch_data()

        user_name = launch_data.get("name", "Student")
        user_email = launch_data.get("email", "")
        user_id = launch_data.get("sub", str(uuid.uuid4()))
        course = launch_data.get(
            "https://purl.imsglobal.org/spec/lti/claim/context", {}
        ).get("title", "Course")
        roles = launch_data.get("https://purl.imsglobal.org/spec/lti/claim/roles", [])
        is_instructor = any("Instructor" in r or "Administrator" in r for r in roles)

        role_label = "👩‍🏫 Instructor" if is_instructor else "🎓 Student"
        role_bg    = "#dcfce7" if is_instructor else "#fef3c7"
        role_color = "#166534" if is_instructor else "#92400e"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>AGLMS – {course}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f4ff;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:2rem}}
    .card{{background:white;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,0.08);max-width:640px;width:100%;overflow:hidden}}
    .header{{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:white;padding:2rem}}
    .header h1{{font-size:1.5rem;font-weight:700;margin-bottom:0.25rem}}
    .header p{{opacity:.85;font-size:.95rem}}
    .body{{padding:2rem}}
    .welcome{{font-size:1.1rem;color:#1e293b;margin-bottom:1.25rem}}
    .welcome strong{{color:#4f46e5}}
    .role-tag{{background:{role_bg};color:{role_color};border-radius:999px;padding:.25rem .75rem;font-size:.78rem;font-weight:600;display:inline-block;margin-bottom:1.5rem}}
    .points-box{{background:#f8faff;border:2px solid #e0e7ff;border-radius:12px;padding:1.5rem;text-align:center;margin-bottom:1.5rem}}
    .points-box .label{{font-size:.85rem;color:#64748b;text-transform:uppercase;letter-spacing:.05em}}
    .points-box .value{{font-size:3rem;font-weight:800;color:#4f46e5;line-height:1.1}}
    .points-box .sublabel{{font-size:.9rem;color:#94a3b8;margin-top:.25rem}}
    .badge-row{{display:flex;gap:.75rem;flex-wrap:wrap;margin-bottom:1.5rem}}
    .badge{{background:#ede9fe;color:#5b21b6;border-radius:999px;padding:.35rem .85rem;font-size:.8rem;font-weight:600}}
    .info-grid{{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1.5rem}}
    .info-item{{background:#f8faff;border-radius:10px;padding:1rem}}
    .info-item .label{{font-size:.75rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:.25rem}}
    .info-item .value{{font-size:.95rem;font-weight:600;color:#1e293b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .success-banner{{background:#f0fdf4;border:1px solid #86efac;border-radius:10px;padding:1rem 1.25rem;font-size:.88rem;color:#166534}}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1>🎮 AGLMS</h1>
      <p>Adaptive Gamified Learning Management System</p>
    </div>
    <div class="body">
      <p class="welcome">Welcome back, <strong>{user_name}</strong>!</p>
      <span class="role-tag">{role_label}</span>
      <div class="points-box">
        <div class="label">Total XP</div>
        <div class="value">0</div>
        <div class="sublabel">Points earned in {course}</div>
      </div>
      <div class="badge-row">
        <span class="badge">⭐ New Member</span>
        <span class="badge">🔓 First Launch</span>
      </div>
      <div class="info-grid">
        <div class="info-item"><div class="label">Course</div><div class="value">{course}</div></div>
        <div class="info-item"><div class="label">LTI Version</div><div class="value">1.3 ✓</div></div>
        <div class="info-item"><div class="label">User ID</div><div class="value">{user_id[:12]}…</div></div>
        <div class="info-item"><div class="label">Email</div><div class="value">{user_email or "—"}</div></div>
      </div>
      <div class="success-banner">✅ LTI 1.3 launch verified — AGLMS is connected to Canvas</div>
    </div>
  </div>
</body>
</html>"""
        return HTMLResponse(content=html)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"LTI launch error: {str(e)}")
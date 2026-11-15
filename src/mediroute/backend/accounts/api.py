"""Account and saved-history API (docs/design/user_history.md).

Login keeps a random session token in an HttpOnly cookie. Calls that change data must send
JSON with the header ``X-MediRoute: 1`` (a cross-site form cannot set it), which, with
SameSite=Lax, protects the cookie against cross-site requests.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from mediroute.backend.accounts.store import SESSION_DAYS, AccountError, get_store

router = APIRouter(tags=["Accounts and saved history"])

COOKIE = "mediroute_session"


class SignupIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)
    country: str = Field(max_length=80)
    consent: bool = False
    name: str | None = Field(default=None, max_length=120)
    language: str | None = Field(default=None, max_length=60)


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


class ThreadItem(BaseModel):
    question: str | None = Field(default=None, max_length=2000)
    answer: str | None = Field(default=None, max_length=2000)


class SaveIn(BaseModel):
    hospital_id: str = Field(max_length=40)
    related_specialty: str | None = Field(default=None, max_length=120)
    workflow_id: str | None = Field(default=None, max_length=64)
    trace_request_id: str | None = Field(default=None, max_length=64)
    save_description: bool = True
    request_text: str | None = Field(default=None, max_length=8000)
    city: str | None = Field(default=None, max_length=120)
    language: str | None = Field(default=None, max_length=60)
    specialty: str | None = Field(default=None, max_length=120)
    specialty_reason: str | None = Field(default=None, max_length=2000)
    thread: list[ThreadItem] = Field(default_factory=list, max_length=20)


def require_header(x_mediroute: str | None = Header(default=None)) -> None:
    if x_mediroute != "1":
        raise HTTPException(status_code=403, detail="Missing X-MediRoute header.")


def current_user(request: Request) -> dict:
    user = get_store().user_for_token(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(status_code=401, detail="Please log in.")
    return user


def _error(exc: AccountError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


def _https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"


def _logged_in(request: Request, user: dict) -> JSONResponse:
    token = get_store().create_session(user["id"])
    response = JSONResponse(content={"user": user})
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 24 * 3600, httponly=True, samesite="lax",
                        secure=_https(request), path="/")
    return response


# ------------------------------------------------------------------ auth
@router.post("/api/auth/signup", dependencies=[Depends(require_header)])
def signup(body: SignupIn, request: Request):
    try:
        user = get_store().signup(body.email, body.password, body.country, body.consent, body.name, body.language)
    except AccountError as exc:
        return _error(exc)
    return _logged_in(request, user)


@router.post("/api/auth/login", dependencies=[Depends(require_header)])
def login(body: LoginIn, request: Request):
    try:
        user = get_store().login(body.email, body.password)
    except AccountError as exc:
        return _error(exc)
    return _logged_in(request, user)


@router.post("/api/auth/logout", dependencies=[Depends(require_header)])
def logout(request: Request, response: Response):
    get_store().end_session(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return {"user": user}


@router.delete("/api/auth/me", dependencies=[Depends(require_header)])
def delete_account(request: Request, response: Response, user: dict = Depends(current_user)):
    get_store().delete_user(user["id"])
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


# ------------------------------------------------------------------ history
@router.post("/api/history", dependencies=[Depends(require_header)])
def save_entry(body: SaveIn, user: dict = Depends(current_user)):
    store = get_store()
    store.purge_old()
    try:
        return {"entry": store.save(user["id"], body.model_dump())}
    except AccountError as exc:
        return _error(exc)


@router.get("/api/history")
def list_entries(user: dict = Depends(current_user)):
    store = get_store()
    store.purge_old()
    return {"entries": store.list_entries(user["id"])}


@router.get("/api/history/{entry_id}")
def get_entry(entry_id: int, user: dict = Depends(current_user)):
    try:
        return {"entry": get_store().get(user["id"], entry_id)}
    except AccountError as exc:
        return _error(exc)


@router.delete("/api/history/{entry_id}", dependencies=[Depends(require_header)])
def delete_entry(entry_id: int, user: dict = Depends(current_user)):
    try:
        get_store().delete(user["id"], entry_id)
    except AccountError as exc:
        return _error(exc)
    return {"ok": True}


@router.delete("/api/history/{entry_id}/hospitals/{hospital_id}", dependencies=[Depends(require_header)])
def remove_hospital(entry_id: int, hospital_id: str, user: dict = Depends(current_user)):
    try:
        return {"entry": get_store().remove_hospital(user["id"], entry_id, hospital_id) or None}
    except AccountError as exc:
        return _error(exc)

from dataclasses import dataclass
from typing import Any, Dict

import requests

from app.config.settings import settings


@dataclass
class AuthSession:
    user: Dict[str, Any]
    access_token: str
    refresh_token: str


@dataclass
class SignUpResult:
    user: Dict[str, Any]
    session: AuthSession | None
    confirmation_required: bool


class SupabaseAuthClient:
    """Small Supabase Auth REST client for Streamlit."""

    def __init__(self, url: str = None, anon_key: str = None):
        self.url = (url or settings.SUPABASE_URL).rstrip("/")
        self.anon_key = anon_key or settings.SUPABASE_ANON_KEY

        if not self.url or not self.anon_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY are required for authentication.")

        self.auth_url = f"{self.url}/auth/v1"

    def sign_up(self, email: str, password: str, redirect_to: str = "") -> SignUpResult:
        params = {"redirect_to": redirect_to} if redirect_to else None
        response = requests.post(
            f"{self.auth_url}/signup",
            headers=self._headers(),
            params=params,
            json={"email": email, "password": password},
            timeout=20,
        )
        data = self._handle_response(response)
        user = data.get("user")
        access_token = data.get("access_token")

        if access_token:
            return SignUpResult(
                user=user,
                session=self._session_from_response(data),
                confirmation_required=False,
            )

        if user:
            return SignUpResult(user=user, session=None, confirmation_required=True)

        raise RuntimeError("Supabase did not return a user. Check your Auth settings.")

    def sign_in(self, email: str, password: str) -> AuthSession:
        response = requests.post(
            f"{self.auth_url}/token?grant_type=password",
            headers=self._headers(),
            json={"email": email, "password": password},
            timeout=20,
        )
        data = self._handle_response(response)
        return self._session_from_response(data)

    def get_user(self, access_token: str) -> Dict[str, Any]:
        response = requests.get(
            f"{self.auth_url}/user",
            headers=self._headers(access_token),
            timeout=20,
        )
        return self._handle_response(response)

    def refresh(self, refresh_token: str) -> AuthSession:
        response = requests.post(
            f"{self.auth_url}/token?grant_type=refresh_token",
            headers=self._headers(),
            json={"refresh_token": refresh_token},
            timeout=20,
        )
        data = self._handle_response(response)
        return self._session_from_response(data)

    def sign_out(self, access_token: str) -> None:
        response = requests.post(
            f"{self.auth_url}/logout",
            headers=self._headers(access_token),
            timeout=20,
        )
        self._handle_response(response)

    def _headers(self, access_token: str = None) -> Dict[str, str]:
        return {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {access_token or self.anon_key}",
            "Content-Type": "application/json",
        }

    def _session_from_response(self, data: Dict[str, Any]) -> AuthSession:
        user = data.get("user")
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")

        if not user:
            raise RuntimeError("Supabase did not return a user. Check whether email confirmation is required.")
        if not access_token:
            raise RuntimeError("Supabase did not return an access token.")

        return AuthSession(
            user=user,
            access_token=access_token,
            refresh_token=refresh_token or "",
        )

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        if response.ok:
            return response.json() if response.content else {}

        try:
            data = response.json()
            message = data.get("msg") or data.get("message") or data.get("error_description") or data.get("error")
        except Exception:
            message = response.text

        raise RuntimeError(message or f"Supabase auth request failed with status {response.status_code}")


def get_auth_client() -> SupabaseAuthClient:
    return SupabaseAuthClient()

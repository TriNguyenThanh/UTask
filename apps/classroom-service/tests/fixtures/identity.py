"""Identity fixtures and provisioning results shared by Classroom tests."""

import json

import jwt
import pytest


@pytest.fixture
def identity(monkeypatch, signing_key):
    from infrastructure.identity import IdentityClient

    state = {
        "active": True,
        "roles": {},
        "profiles": {},
        "calls": [],
        "provision": None,
        "keys": [json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))],
    }

    def current_user(self, access):
        claims = jwt.decode(access, options={"verify_signature": False})
        user_id = claims["sub"]
        return {"id": user_id, "roles": state["roles"].get(user_id, ["STUDENT"])}

    def users(self, access, ids):
        state["calls"].append(("users", list(ids)))
        return [
            state["profiles"].get(
                str(pk),
                {
                    "id": str(pk),
                    "full_name": "Sinh viên",
                    "roles": ["STUDENT"],
                    "account_status": "ACTIVE",
                },
            )
            for pk in ids
        ]

    def provision(self, access, rows, key):
        state["calls"].append(("provision", rows, key))
        assert state["provision"] is not None, "Configure provisioning for this test"
        return state["provision"](rows, key)

    monkeypatch.setattr(IdentityClient, "jwks", lambda self: {"keys": state["keys"]})
    monkeypatch.setattr(IdentityClient, "session_active", lambda self, access: state["active"])
    monkeypatch.setattr(IdentityClient, "current_user", current_user)
    monkeypatch.setattr(IdentityClient, "users", users)
    monkeypatch.setattr(IdentityClient, "provision", provision)
    return state


def student_rows(count=1):
    return [
        {
            "row_number": i + 1,
            "email": f"student{i}@example.test",
            "first_name": f"Sinh viên {i}",
            "last_name": "Nguyễn",
        }
        for i in range(count)
    ]


def provision_result(rows, ids):
    return {
        "results": [
            {
                **row,
                "user_id": str(pk) if pk else None,
                "account_status": "PENDING_ACTIVATION" if pk else None,
                "account_result": "CREATED" if pk else "FAILED",
                "reason": None if pk else "INVALID_EMAIL",
            }
            for row, pk in zip(rows, ids, strict=True)
        ]
    }

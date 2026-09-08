"""
test_dashboard_heartbeat.py
===========================
Tests for real-time user learning hours heartbeat tracking and stats.
"""
import pytest
from app.core.database import DBContext, new_id
from app.core.models import User
from app.api.auth import hash_password, create_access_token


def test_heartbeat_accumulates_learning_hours(sync_client):
    username = f"heartbeat_{new_id()[:8]}"
    email = f"{username}@test.com"
    user_id = new_id()

    with DBContext() as db:
        u = User(
            id=user_id,
            username=username,
            email=email,
            password_hash=hash_password("Pass123!"),
            total_learning_hours=0.0,
            current_streak=0,
            longest_streak=0,
        )
        db.add(u)
        db.commit()

    token = create_access_token({"sub": user_id, "id": user_id, "email": email, "role": "student"})
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Send first heartbeat of 30 seconds
    res1 = sync_client.post("/api/dashboard/heartbeat", json={"active_seconds": 30}, headers=headers)
    assert res1.status_code == 200, res1.text
    data1 = res1.json()
    assert data1["status"] == "ok"
    assert data1["active_seconds"] == 30
    assert data1["current_streak"] >= 1

    # 2. Send second heartbeat of 30 seconds (total 60s)
    res2 = sync_client.post("/api/dashboard/heartbeat", json={"active_seconds": 30}, headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["total_learning_hours"] == round(60 / 3600.0, 2)

    # 3. Check /dashboard/stats
    stats_res = sync_client.get("/api/dashboard/stats", headers=headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert "total_learning_hours" in stats
    assert stats["current_streak"] >= 1

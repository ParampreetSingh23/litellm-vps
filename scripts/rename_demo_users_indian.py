"""Rename demo users from @northfield-university.edu to Indian names at @rabbitt.ai via the proxy API.

Usage:
    LITELLM_URL=http://localhost:4000 LITELLM_MASTER_KEY=sk-... python3 scripts/rename_demo_users_indian.py
"""

import json
import os
import urllib.request
from collections.abc import Iterator
from typing import Final

URL: Final = os.environ.get("LITELLM_URL", "http://localhost:4000").rstrip("/")
KEY: Final = os.environ["LITELLM_MASTER_KEY"]
OLD_DOMAIN: Final = "@northfield-university.edu"
NEW_DOMAIN: Final = "@rabbitt.ai"

NAMES: Final = (
    "Aarav Sharma", "Priya Iyer", "Rohan Mehta", "Ananya Reddy", "Vikram Nair",
    "Kavya Menon", "Arjun Patel", "Sneha Kulkarni", "Aditya Joshi", "Isha Gupta",
    "Karthik Subramanian", "Meera Pillai", "Rahul Verma", "Divya Rao", "Siddharth Bose",
    "Neha Kapoor", "Varun Chatterjee", "Pooja Deshpande", "Nikhil Agarwal", "Riya Banerjee",
    "Harsh Malhotra", "Tanvi Shetty", "Manish Tiwari", "Shreya Krishnan", "Abhishek Singh",
    "Aishwarya Hegde", "Kunal Saxena", "Nandini Das", "Pranav Bhatt", "Lakshmi Venkatesh",
    "Gaurav Chauhan", "Swati Mishra", "Yash Thakur", "Deepika Naidu", "Ravi Shankar",
    "Anjali Mukherjee", "Suresh Kumar", "Pallavi Jain", "Amit Pandey", "Sanya Arora",
)


def call(method: str, path: str, body: dict[str, str] | None = None) -> dict[str, object]:
    req: Final = urllib.request.Request(
        f"{URL}{path}",
        method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def all_users() -> Iterator[dict[str, str]]:
    page = 1
    while True:
        data: Final = call("GET", f"/user/list?page={page}&page_size=100")
        yield from data["users"]  # pyright: ignore[reportGeneralTypeIssues]  # untyped proxy JSON
        if page >= int(data.get("total_pages") or 1):  # pyright: ignore[reportArgumentType]  # untyped proxy JSON
            return
        page += 1  # rebind-ok: pagination cursor


def main() -> None:
    targets: Final = sorted(
        (u for u in all_users() if (u.get("user_email") or "").endswith(OLD_DOMAIN)),
        key=lambda u: u["user_email"],
    )
    if len(targets) > len(NAMES):
        raise SystemExit(f"{len(targets)} users but only {len(NAMES)} names, add more to NAMES")

    for user, name in zip(targets, NAMES):
        email: Final = name.lower().replace(" ", ".") + NEW_DOMAIN
        call("POST", "/user/update", {"user_id": user["user_id"], "user_email": email, "user_alias": name})
        print(f"{user['user_email']:45} -> {email:40} {name}")

    print(f"done, {len(targets)} users renamed")


if __name__ == "__main__":
    main()

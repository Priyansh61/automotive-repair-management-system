"""
Local dev seed script — creates test users and a tenant.
Run once after setting up your local DB:

    python3 seed_local.py

Credentials:
    owner@local.dev     / password123   (owner)
    admin@local.dev     / password123   (admin)
    tech@local.dev      / password123   (technician)
"""
import os
from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.tenant import Tenant
from app.models.tenant_membership import TenantMembership
from app.models.subscription import Subscription
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

TEST_USERS = [
    {"email": "owner@local.dev",  "username": "owner",  "role": "owner"},
    {"email": "admin@local.dev",  "username": "admin",  "role": "admin"},
    {"email": "tech@local.dev",   "username": "tech",   "role": "technician"},
]
PASSWORD = "password123"
TENANT_SLUG = "local-garage"


def seed():
    app = create_app()
    with app.app_context():
        # Create tenant if it doesn't exist
        tenant = db.session.execute(
            db.select(Tenant).where(Tenant.slug == TENANT_SLUG)
        ).scalar_one_or_none()

        if not tenant:
            tenant = Tenant(
                name="Local Garage",
                slug=TENANT_SLUG,
                business_type="auto_repair",
                email="garage@local.dev",
                status="active",
                trial_ends_at=datetime.utcnow() + timedelta(days=365),
            )
            db.session.add(tenant)
            db.session.flush()

            sub = Subscription(
                tenant_id=tenant.tenant_id,
                plan="professional",
                status="active",
                current_period_start=datetime.utcnow(),
                current_period_end=datetime.utcnow() + timedelta(days=365),
            )
            db.session.add(sub)
            print(f"Created tenant: {tenant.name} (slug={TENANT_SLUG})")
        else:
            print(f"Tenant already exists: {tenant.name}")

        # Create users
        for u in TEST_USERS:
            user = db.session.execute(
                db.select(User).where(User.email == u["email"])
            ).scalar_one_or_none()

            if not user:
                user = User(
                    username=u["username"],
                    email=u["email"],
                    password_hash=generate_password_hash(PASSWORD),
                    is_active=True,
                    email_verified=True,
                )
                db.session.add(user)
                db.session.flush()
                print(f"Created user: {u['email']} ({u['role']})")
            else:
                # Ensure password is set
                user.password_hash = generate_password_hash(PASSWORD)
                user.is_active = True
                print(f"Updated user: {u['email']} ({u['role']})")

            # Create membership if missing
            membership = db.session.execute(
                db.select(TenantMembership).where(
                    TenantMembership.user_id == user.user_id,
                    TenantMembership.tenant_id == tenant.tenant_id,
                )
            ).scalar_one_or_none()

            if not membership:
                membership = TenantMembership(
                    user_id=user.user_id,
                    tenant_id=tenant.tenant_id,
                    role=u["role"],
                    status="active",
                    is_default=True,
                )
                db.session.add(membership)

        db.session.commit()
        print("\nDone. Test credentials:")
        print(f"  Tenant slug : {TENANT_SLUG}")
        for u in TEST_USERS:
            print(f"  {u['email']:25s}  /  {PASSWORD}  ({u['role']})")


if __name__ == "__main__":
    seed()

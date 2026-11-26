from app.core.database import SessionLocal
from app.models.entities import User
from app.core.security import hash_password

PASSWORD = "Naksha@Test2026"

db = SessionLocal()

users = (
    db.query(User)
    .filter(User.is_active == True)
    .all()
)

print("Total active users:", len(users))

hashed = hash_password(PASSWORD)

for user in users:
    user.password_hash = hashed
    user.token_version = (user.token_version or 0) + 1

db.commit()

print("Updated users:", len(users))

db.close()
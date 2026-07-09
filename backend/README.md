# Dashboard Backend

FastAPI backend providing self-managed authentication (no Supabase Auth) and
a protected dashboard API, backed directly by Postgres via Supabase's direct
connection string. OneDrive, pipeline execution, and controller integration
are not implemented yet.

**Auth model:** this backend does not use Supabase Auth, Supabase API keys,
or the Supabase client library at all. It only needs a direct Postgres
connection string. Passwords are hashed with bcrypt and stored in the
backend's own `user_profiles` table; access tokens are JWTs minted and
verified by this backend using `JWT_SECRET`.

## 1. Setup

```bash
cd Backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

## 2. Environment variables

```bash
copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux
```

Fill in `Backend/.env`:

| Variable | Where to get it |
|---|---|
| `DATABASE_URL` | Supabase → Project Settings → Database → Connection string → URI (**direct** connection, port `5432`) |
| `JWT_SECRET` | Any long random string you generate yourself, e.g. `openssl rand -hex 32`. Does not need to come from Supabase. |
| `JWT_ALGORITHM` | `HS256` (default, leave as-is) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | How long login tokens stay valid (default 1440 = 24h) |
| `FRONTEND_URL` | Your Vite dev server, default `http://localhost:5173` |
| `AUTO_CREATE_TABLES` | `true` to create tables automatically on startup, otherwise run the command below manually |

⚠️ **IPv6 note:** Supabase's direct connection host is IPv6-only unless your
project has the IPv4 add-on enabled. If `python -m app.database.init_db`
times out, either enable the IPv4 add-on in Supabase, or use the session
pooler connection string instead (works the same with this backend).

## 3. Create database tables

Tables are created directly from backend code via SQLAlchemy — a real
migration step, not a placeholder. Safe to run multiple times; never drops
or overwrites existing data.

```bash
python -m app.database.init_db
```

Creates, if not already present:
- `user_profiles` (includes `hashed_password` — this is where accounts live)
- `dashboard_sessions`
- `dashboard_activity_logs`
- `system_settings`

plus supporting indexes.

Alternatively, set `AUTO_CREATE_TABLES=true` in `.env` and tables are created
automatically each time the backend starts.

## 4. Run the backend

```bash
uvicorn app.main:app --reload
```

Backend runs at: `http://localhost:8000`

## 5. API docs

Swagger UI: `http://localhost:8000/docs`

## 6. Auth API endpoints

| Method | Path | Auth required | Description |
|---|---|---|---|
| POST | `/auth/register` | No | Hashes password, creates row in `user_profiles` |
| POST | `/auth/login` | No | Verifies password, mints JWT, returns access token + profile |
| POST | `/auth/logout` | Yes (Bearer) | Ends dashboard session, logs activity |
| GET | `/auth/me` | Yes (Bearer) | Returns current user profile |

## 7. Dashboard API endpoints

| Method | Path | Auth required | Description |
|---|---|---|---|
| GET | `/dashboard/health` | No | Backend/DB status |
| GET | `/dashboard/stats` | Yes (Bearer) | Placeholder stats (files/pipelines) |
| GET | `/dashboard/profile` | Yes (Bearer) | Current user profile |
| GET | `/dashboard/activity` | Yes (Bearer) | Current user's recent activity logs |

## 8. Testing in Swagger / Postman

1. `POST /auth/register` with:
   ```json
   { "email": "user@example.com", "password": "password123", "full_name": "User Name" }
   ```
2. `POST /auth/login` with the same email/password. Copy `data.session.access_token`
   from the response.
3. In Swagger, click **Authorize** and paste the token (or in Postman, set
   header `Authorization: Bearer <token>`).
4. Call `GET /auth/me`, `GET /dashboard/profile`, `GET /dashboard/stats`,
   `GET /dashboard/activity` — all should succeed.
5. Call any protected route without a token — should return `401`.
6. `POST /auth/logout` — should succeed and mark the session inactive.

## Not implemented in this phase

- OneDrive integration
- Pipeline start/pause/status
- Controller connection
- Frontend changes
- Supabase Auth (intentionally not used — see Auth model above)

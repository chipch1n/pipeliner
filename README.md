# Pipeliner MVP

Minimal web‑based image processing pipeline prototype with user authentication.

## Stack
- **Frontend:** React + TypeScript + Vite
- **Backend:** FastAPI + Pillow + NumPy
- **Database:** PostgreSQL (via SQLAlchemy async + asyncpg)
- **Migrations:** Liquibase
- **Authentication:** SHA‑256 hashed passwords (fixed salt), cookie‑based sessions
- **Email:** aiosmtplib (lockout alerts)

## Features
### Image processing
- Upload an image
- Add/remove/reorder linear processing nodes
- Blur node (radius parameter)
- Noise node (intensity parameter)
- Process image through pipeline order
- Side‑by‑side original/processed preview
- Download processed image

### User management
- Registration (`POST /register`) – stores username + hashed password
- Login (`POST /login`) – validates credentials, sets secure session cookie
- Session‑based protected endpoints (e.g., `GET /me`)
- Logout (`POST /logout`) – clears session
- Account lockout after 3 failed login attempts (10‑minute lock)
- Email notification on lockout to a fixed address

## Prerequisites
- Docker & Docker Compose (for containerised run)
- Or Python 3.11+ and Node.js 18+ (for local development)
- PostgreSQL instance (provided by Docker Compose or external)

## Environment variables
All variables have sensible defaults for development. Adjust in `docker-compose.yml` or export before running locally.

| Variable             | Default             | Description                                      |
|----------------------|---------------------|--------------------------------------------------|
| `DB_HOST`            | `db`                | PostgreSQL host                                  |
| `DB_PORT`            | `5432`              | PostgreSQL port                                  |
| `DB_NAME`            | `pipeliner`         | Database name                                    |
| `DB_USER`            | `postgres`          | Database user                                    |
| `DB_PASSWORD`        | `postgres`          | Database password                                |
| `SMTP_HOST`          | `smtp.example.com`  | SMTP server for lockout alerts                   |
| `SMTP_PORT`          | `587`               | SMTP port                                        |
| `SMTP_USER`          | (empty)             | SMTP authentication user                         |
| `SMTP_PASSWORD`      | (empty)             | SMTP authentication password                     |
| `SMTP_USE_TLS`       | `true`              | Enable TLS for SMTP                              |
| `LOCKOUT_ALERT_EMAIL`| `admin@example.com` | Recipient of lockout alert emails                |
| `PASSWORD_SALT`      | (empty)             | Fixed salt for SHA‑256 (change for production!)  |

## Run with Docker
```bash
docker compose up --build
```

Frontend: [http://localhost:5173](http://localhost:5173)  
Backend: [http://localhost:8000](http://localhost:8000)

Default DB credentials (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB) are listed in docker compose file

## Testing

### Backend

To run tests, first pip install everything from requirements.txt, then run the following from project root:
```bash
python -m pytest ./backend/tests/
```

## API
`POST /process-image`

Multipart fields:
- `image`: image file
- `preview_node_id` (optional): specified final node 
- `pipeline`: JSON string like:

```json
{
  "nodes": [
    { "id": "blur-1", "type": "blur", "params": { "radius": 6 } },
    { "id": "noise-1", "type": "noise", "params": { "intensity": 25 } }
  ]
}
```

`POST /register`

Request:
- `username`: string, 3–255 characters
- `password`: string, 6–128 characters

Ok (201): user registered successfully.\
Error (400): username already exists.

`POST /login`

Request:
- `username`: string
- `password`: string

Response:
`{"username": "username"}`

Ok (200): login successful, set session cookie.\
Error (401): invalid credentials.\
Error (423): user locked out.

`POST /logout`

Ok (200): clears session cookie and deletes session from db.
Error (400): no session.

`GET /user-info`

Response:
`{"user_id": "user_id"}`

Ok (200): returns user id from current session.
Error (401): invalid or no session.

`POST /pipelines`

Requires authentication cookie.

Request body (JSON):

- `name`: string, 1–255 characters (pipeline name)
- `nodes`: array of node objects (same structure as /process-image)

Created (201): \
{ "id": 123 }

If a pipeline with the same name exists, it is updated: \
{ "message": "Pipeline updated successfully", "id": 123 }

`GET /pipelines/{name}`

Requires authentication cookie.

Ok (200): \
`{
  "id": 123,
  "name": "my-pipeline",
  "pipeline_data": { "nodes": [...], "branch_sources": {"main": "original", "side": "main"} }
}`

Error (404): pipeline not found.

`GET /pipelines`

Requires authentication cookie. Lists all user's pipelines ordered by last update.

Ok (200): \
`[
  { "id": 2, "name": "recent-pipeline" },
  { "id": 1, "name": "my-pipeline" }
]`

`DELETE /pipelines/{name}`

Requires authentication cookie.

Ok (200): { "message": "Pipeline deleted successfully" }

Error (404): pipeline not found.
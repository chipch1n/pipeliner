# Pipeliner MVP

Minimal web‑based image processing pipeline prototype with user authentication.

## Stack
- **Frontend:** React + TypeScript + Vite
- **Backend:** FastAPI + Pillow + NumPy
- **Database:** PostgreSQL (via SQLAlchemy async + asyncpg)
- **Migrations:** Liquibase
- **Authentication:** SHA‑256 hashed passwords (fixed salt), cookie‑based sessions
- **Email:** aiosmtplib

## Features
### Image processing
- Upload an image
- Add/remove/reorder linear processing nodes
- Blur node (radius parameter)
- Noise node (intensity parameter)
- Hugging Face image-to-image node (model id, prompt, provider)
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

### Pipeline presets
- Authenticated users can save multiple named pipeline presets
- Presets are private to the current user and persisted in PostgreSQL
- Saved presets can be loaded, overwritten, or deleted from the frontend

## Prerequisites
- Docker & Docker Compose (for containerised run)
- Or Python 3.11+ and Node.js 18+ (for local development)
- PostgreSQL instance (provided by Docker Compose or external)

## Environment variables
Copy `.env.example` to `.env` in the project root and set your values (`.env` is gitignored). The backend loads it automatically on startup.

For Docker, set the same variables in `docker-compose.yml` or pass a `.env` file to Compose.

Other defaults apply when a variable is omitted.

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
| `FIXED_SALT`         | (required)          | Fixed salt for SHA‑256 (set in `.env`; change for production!) |
| `HF_TOKEN`           | (empty)             | Hugging Face token for `hf_image_to_image` node (also reads `HUGGINGFACE_HUB_TOKEN`) |

## Run with Docker
```bash
docker compose up --build
```

Frontend: [http://localhost:5173](http://localhost:5173)  
Backend: [http://localhost:8000](http://localhost:8000)

Default DB credentials (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB) are listed in docker compose file

## Testing

### Backend

#### Unit tests
To run unit tests, first pip install everything from requirements.txt, then run the following from project root:
```bash
python -m pytest ./backend/tests/unit
```

#### Integration tests
To run integration tests, first pip install everything from requirements.txt, turn on docker daemon,
fill pytest.ini file with correct configuration if it was changed in docker compose and run integration_test.sh from project root.

In order to run tests in IDE, you need to manually run the app with docker:
```bash
docker compose up -d --build
```

Then call from project root:
```bash
python -m pytest ./backend/tests/integration
```

After that you need to remove the container:
```bash
docker compose rm -sf
```

### Frontend

```bash
cd frontend
npm install
npm test
npm run build
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
    { "id": "noise-1", "type": "noise", "params": { "intensity": 25 } },
    {
      "id": "hf-1",
      "type": "hf_image_to_image",
      "params": {
        "model": "timbrooks/instruct-pix2pix",
        "prompt": "turn it into a watercolor",
        "provider": "replicate"
      }
    }
  ]
}
```

`hf_image_to_image` calls [Hugging Face Inference Providers](https://huggingface.co/docs/huggingface_hub/en/guides/inference) (`image_to_image`). Supported providers: `replicate`, `fal-ai`, `hf-inference`. Not every Hub model is available on every provider.

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
`{"user_id": 123, "username": "username"}`

Ok (200): returns the user id and username from the current session.
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

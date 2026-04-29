# Pipeliner MVP

Minimal web-based image processing pipeline prototype.

## Stack
- Frontend: React + TypeScript + Vite
- Backend: FastAPI + Pillow + NumPy

## Features
- Upload image
- Add/remove/reorder linear nodes
- Blur node (radius parameter)
- Noise node (intensity parameter)
- Process image through pipeline order
- Side-by-side original/processed preview
- Download processed image

## Run with Docker
```bash
docker compose up --build
```

Frontend: [http://localhost:5173](http://localhost:5173)  
Backend: [http://localhost:8000](http://localhost:8000)

## Run without Docker

Backend:
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

## API
`POST /process-image`

Multipart fields:
- `image`: image file
- `pipeline`: JSON string like:

```json
{
  "nodes": [
    { "id": "blur-1", "type": "blur", "params": { "radius": 6 } },
    { "id": "noise-1", "type": "noise", "params": { "intensity": 25 } }
  ]
}
```

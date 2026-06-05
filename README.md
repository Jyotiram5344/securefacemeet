# SecureFaceMeet

**AI-based face recognition with passive liveness and JWT-gated virtual meeting entry.**

- **Backend:** FastAPI, PyTorch, InsightFace (ArcFace / `buffalo_l`), ONNX anti-spoof (Silent-Face style), PostgreSQL, SQLAlchemy, JWT.
- **Frontend:** React, Vite, TailwindCSS, Axios, WebRTC camera capture (frames sent to API only).

## Architecture

```
SecureFaceMeet/
├── backend/           # FastAPI app
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   ├── schemas/
│   ├── routes/
│   ├── services/
│   ├── utils/
│   ├── weights/       # Place anti_spoof.onnx here (not committed)
│   └── requirements.txt
├── frontend/          # React + Vite
├── docker-compose.yml
├── sample_schema.sql
└── README.md
```

### Verification chain (server-side only)

1. `POST /api/v1/face/verify-face` → ArcFace match (cosine ≥ `FACE_MATCH_THRESHOLD`, default **0.6**) → **`verify_token`** (JWT).
2. `POST /api/v1/liveness/check-liveness` with `Authorization: Bearer <verify_token>` → passive liveness score → **`liveness_token`** if score ≥ `LIVENESS_SCORE_THRESHOLD` (default **0.8**).
3. `POST /api/v1/meeting/generate-meeting-token` with `Authorization: Bearer <liveness_token>` → **meeting JWT** (default expiry **5 minutes**).

Never trust the frontend for verification; it only uploads images and stores the issued JWT for UI gating.

## Prerequisites

- Python **3.11**
- Node **18+** (for frontend)
- PostgreSQL **14+** (local or Docker)
- GPU optional (InsightFace uses GPU if PyTorch sees CUDA)

### Anti-spoof ONNX weights

Place an ONNX export compatible with **NCHW float32** input (e.g. MiniFASNet / CDNet-style **80×80** RGB) at:

- `backend/weights/anti_spoof.onnx`

The [Silent-Face-Anti-Spoofing](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing) project provides training/export paths; you must export or obtain an ONNX model and align preprocessing in `services/liveness_service.py` if your model uses different input sizes (the loader reads static spatial dims when present).

### InsightFace models

On first run, InsightFace downloads **`buffalo_l`** into `INSIGHTFACE_ROOT` (default `~/.insightface`).

## Local setup (without Docker)

### 1. Database

Create database and user (or use defaults from `.env.example`), then:

```bash
psql -U secureface -d securefacemeet -f sample_schema.sql
```

Or rely on SQLAlchemy `init_db()` on API startup (development only).

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
copy .env.example .env          # edit DATABASE_URL and JWT_SECRET_KEY
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs: `http://127.0.0.1:8000/docs`

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Set `VITE_API_BASE_URL` if the API is not on `http://127.0.0.1:8000`.

## Docker

From `SecureFaceMeet/`:

```bash
docker compose up --build
```

- API: `http://localhost:8000`
- Mount your ONNX file into `./backend/weights/anti_spoof.onnx` (see `docker-compose.yml`).

Set a strong `JWT_SECRET_KEY` in the environment for production.

## API summary

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/face/register-face` | Enroll face (multipart: `email`, `full_name`, optional `password`, `file`) |
| POST | `/api/v1/face/verify-face` | Verify face; optional form field `email` to restrict match |
| POST | `/api/v1/liveness/check-liveness` | Passive liveness; requires Bearer **verify_token** |
| POST | `/api/v1/meeting/generate-meeting-token` | Issue meeting JWT; requires Bearer **liveness_token** |
| GET | `/api/v1/meeting/verify-token` | Validate meeting JWT |
| GET | `/health` | Health check |

## Security notes

- Use **HTTPS** in production; terminate TLS at a reverse proxy (nginx, Caddy, cloud LB).
- Rotate **`JWT_SECRET_KEY`**; keep it out of source control.
- Store **password hashes** only (bcrypt via `passlib` when password is provided on register).
- Tune **`FACE_MATCH_THRESHOLD`** and **`LIVENESS_SCORE_THRESHOLD`** for your dataset and camera conditions.

## Further accuracy (optional)

- Swap the lightweight ONNX anti-spoof for a **finer-grained** model or **multi-frame** scoring.
- Use **InsightFace** larger models or dedicated **ArcFace** exports with metric learning on your own gallery.
- Add **active liveness** (challenge-response) for higher assurance than passive-only.

## License

Project scaffold provided as-is for integration into your product and compliance review.

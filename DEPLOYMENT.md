# Onboarding KOF Entersys - Deployment Guide

## Project Overview

This is the **Onboarding Security Training System** for Coca-Cola FEMSA (KOF) contractors, separated from the main EnterSys monorepo into its own standalone project. It handles the complete onboarding lifecycle: video training, security exams, digital credentials, and certificate management.

## Architecture

```
Onboarding-Kof-Entersys/
├── frontend/                    # React 18 SPA (root level - package.json is at project root)
│   ├── src/
│   │   ├── App.jsx              # Route definitions (5 routes)
│   │   ├── main.jsx             # Entry point (BrowserRouter + HelmetProvider)
│   │   ├── index.css            # Tailwind CSS entry
│   │   ├── pages/
│   │   │   ├── CursoSeguridad.jsx              # Video training (anti-skip)
│   │   │   ├── FormularioCursoSeguridad.jsx     # 30-question exam (3 sections)
│   │   │   ├── CredencialKOF.jsx               # Digital credential display
│   │   │   ├── CertificacionSeguridad.jsx      # Certificate validation (QR scan)
│   │   │   └── ActualizarPerfil.jsx            # Profile update form
│   │   ├── components/
│   │   │   ├── SecureVideoPlayer.jsx           # Anti-skip video player
│   │   │   └── SEO/MetaTags.jsx                # SEO metadata
│   │   ├── config/environment.js               # Centralized env config
│   │   ├── services/toast.js                   # Toast notifications
│   │   └── hooks/                              # Custom React hooks
│   ├── public/images/                          # Static assets (logos)
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── Dockerfile                              # Multi-stage: Node build → Nginx serve
│   ├── docker-compose.yml                      # Traefik labels for routing
│   ├── nginx.conf                              # SPA routing + security headers
│   ├── .env.production
│   └── .env.development
│
└── backend/                     # FastAPI backend (Python 3.12)
    ├── app/
    │   ├── main.py              # FastAPI app entry point
    │   ├── core/config.py       # Pydantic Settings (env vars)
    │   ├── db/
    │   │   ├── base.py          # SQLAlchemy declarative base
    │   │   └── session.py       # DB session factory
    │   ├── api/v1/endpoints/
    │   │   └── onboarding.py    # All 14 API endpoints (~3000 lines)
    │   ├── models/
    │   │   └── exam.py          # ExamCategory + ExamQuestion models
    │   ├── schemas/
    │   │   └── onboarding_schemas.py  # Pydantic request/response models
    │   ├── services/
    │   │   └── onboarding_smartsheet_service.py  # Smartsheet API integration
    │   ├── utils/
    │   │   ├── qr_utils.py      # QR code generation with logo
    │   │   └── pdf_utils.py     # Certificate PDF generation
    │   └── static/              # Backend static assets (logos for QR/PDF)
    ├── requirements.txt
    ├── Dockerfile
    ├── docker-compose.yml
    └── .env.example

```

**IMPORTANT**: The frontend files (package.json, Dockerfile, docker-compose.yml, etc.) are at the project root level, NOT inside a `frontend/` subfolder. The structure above shows the logical separation, but physically:
- Root level = Frontend (React SPA)
- `backend/` = Backend (FastAPI)

## Production URLs (MUST NOT CHANGE)

| Component | URL |
|-----------|-----|
| Video Training | `https://www.entersys.mx/curso-seguridad` |
| Exam Form | `https://www.entersys.mx/formulario-curso-seguridad` |
| Digital Credential | `https://www.entersys.mx/credencial-kof/{rfc}` |
| Certificate Validation | `https://www.entersys.mx/certificacion-seguridad/{uuid}` |
| Profile Update | `https://www.entersys.mx/actualizar-perfil` |
| API Backend | `https://api.entersys.mx/api/v1/onboarding/*` |

These URLs are shared with Coca-Cola FEMSA (KOF) and printed on QR codes. They must remain identical.

## API Endpoints (14 total)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/generate` | Generate QR certificate (Smartsheet Bridge webhook) |
| GET | `/validate` | Validate QR certificate (redirect on scan) |
| GET | `/certificate-info/{uuid}` | Get certificate details |
| GET | `/credential/{rfc}` | Get credential data for virtual credential |
| GET | `/lookup-rfc` | Search RFC by NSS + email |
| GET | `/check-exam-status/{rfc}` | Check if user can take exam |
| GET | `/exam-questions` | Get dynamic exam questions (no answers sent) |
| POST | `/submit-exam` | Submit exam and calculate scores |
| POST | `/upload-photo` | Upload credential photo to GCS |
| POST | `/resend-certificate` | Resend certificate by RFC + NSS |
| GET | `/download-certificate/{rfc}` | Download certificate PDF |
| POST | `/profile/verify` | Verify identity for profile updates |
| GET | `/list-all-registros` | Admin: list all records |
| PUT | `/update-record` | Admin: update Smartsheet record |

## External Services & Dependencies

| Service | Purpose | Config Key |
|---------|---------|------------|
| **PostgreSQL** | Exam questions/categories DB | `POSTGRES_*` env vars |
| **Smartsheet** | Source of truth for contractor data, certificates, scores | `SMARTSHEET_ACCESS_TOKEN`, `SHEET_ID` |
| **Google Cloud Storage** | Credential photos storage | `GCS_BUCKET_NAME`, `GCS_PROJECT_ID` |
| **Gmail API** | Send certificate emails | Service account credentials |
| **Traefik v2.10** | Reverse proxy, TLS, routing | Docker labels in docker-compose.yml |

## Database Tables

```sql
-- Exam categories (3 sections: Seguridad, Inocuidad, Ambiental)
CREATE TABLE exam_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    color VARCHAR(20) NOT NULL DEFAULT 'gray',
    display_order INTEGER NOT NULL DEFAULT 0,
    questions_to_show INTEGER NOT NULL DEFAULT 10,
    min_score_percent INTEGER NOT NULL DEFAULT 80,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Exam questions (30 total, 10 per category)
CREATE TABLE exam_questions (
    id SERIAL PRIMARY KEY,
    category_id INTEGER REFERENCES exam_categories(id) NOT NULL,
    question_text TEXT NOT NULL,
    options JSONB NOT NULL,          -- ["option_a", "option_b", "option_c", "option_d"]
    correct_answer TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_exam_questions_category ON exam_questions(category_id);
```

These tables live in the **same PostgreSQL database** as the main EnterSys backend (shared DB). The Smartsheet sheet is the primary source for contractor records, certificates, and scores.

## Deployment to Production Server

### Server Info
- **IP**: 34.59.193.54 (GCP e2-standard-4)
- **OS**: Debian 12
- **Docker**: 94 containers with Traefik v2.10
- **Network**: `traefik-public` (external Docker network)

### Deploy Frontend (React SPA)

```bash
# SSH into production server
ssh user@34.59.193.54

# Clone or pull the repo
cd /opt/apps
git clone https://github.com/armando-entersys/Obnboarding-Kof-Entersys.git onboarding-kof
cd onboarding-kof

# Build and deploy the frontend container
docker compose up -d --build

# Verify
docker ps | grep entersys-onboarding
curl -I https://www.entersys.mx/curso-seguridad
```

The frontend docker-compose.yml (at project root) has Traefik labels that route the 5 onboarding paths from `www.entersys.mx` to this container with priority 100.

### Deploy Backend (FastAPI)

**IMPORTANT**: The backend is currently served as part of the main `entersys-backend` container. To fully separate it:

1. Create a `.env` file in `backend/` with production credentials (see `.env.example`)
2. Copy the GCP service account JSON for Gmail API and GCS access
3. Deploy:

```bash
cd /opt/apps/onboarding-kof/backend

# Create .env from example and fill in real values
cp .env.example .env
vim .env

# Build and deploy
docker compose up -d --build

# Verify
curl https://api.entersys.mx/api/v1/onboarding/health
```

**NOTE ON BACKEND SEPARATION**: Currently the onboarding API endpoints live inside the main `entersys-backend` FastAPI app (shared with CRM, admin, and other services). The backend code in this repo is extracted for reference and future independent deployment. To fully separate it:
- The backend docker-compose.yml uses priority 110 on Traefik so it takes precedence over the main backend for `/api/v1/onboarding` routes
- You need to ensure the main backend's onboarding router is removed once this service is independently deployed
- Both share the same PostgreSQL database (exam_categories, exam_questions tables)

### Environment Variables

#### Frontend (.env.production)
| Variable | Value |
|----------|-------|
| `VITE_APP_URL` | `https://www.entersys.mx` |
| `VITE_API_URL` | `https://api.entersys.mx/api` |
| `VITE_GA4_MEASUREMENT_ID` | `G-3468MEXLPS` |
| `VITE_ENABLE_ANALYTICS` | `true` |

#### Backend (.env)
| Variable | Description |
|----------|-------------|
| `POSTGRES_*` | PostgreSQL connection (shared DB) |
| `SMARTSHEET_ACCESS_TOKEN` | Smartsheet API token |
| `MIDDLEWARE_API_KEY` | API key for webhook auth |
| `SHEET_ID` | Smartsheet sheet ID: `7060277951418244` |
| `GCS_BUCKET_NAME` | GCS bucket: `entersys-onboarding-photos` |
| `GCS_PROJECT_ID` | GCP project: `mi-infraestructura-web` |
| `SMTP_USER` / `SMTP_PASSWORD` | Gmail credentials for sending certificates |
| `SECRET_KEY` | JWT secret for auth tokens |

## Business Logic

### Exam Flow
1. Contractor watches video at `/curso-seguridad` (90% completion required, anti-skip)
2. Takes exam at `/formulario-curso-seguridad` (30 questions, 3 sections of 10)
3. Must score >= 80% per section to pass
4. Maximum 3 attempts per RFC
5. On pass: certificate generated, QR created, email sent, Smartsheet updated
6. On fail: remaining attempts shown, section-by-section results displayed

### Credential System
- `/credencial-kof/{rfc}` shows a digital credential card with photo, QR, status
- Two risk levels from Smartsheet:
  - **Low/Medium risk**: Basic credential (name, photo, status, QR)
  - **High risk**: Extended technical sheet with legal info and competencies

### Certificate Validation
- QR codes on certificates link to `/certificacion-seguridad/{uuid}`
- Shows validity status, name, score, expiration (365 days)
- Expired certificates prompt re-taking the exam

## Key Constants (in onboarding.py)
```python
MINIMUM_SCORE = 80.0              # Minimum % to pass each section
CERTIFICATE_VALIDITY_DAYS = 365   # Certificate expires after 1 year
MAX_ATTEMPTS = 3                  # Maximum exam attempts per RFC
```

## Docker Networking
Both containers must be on the `traefik-public` network. Traefik handles TLS via Let's Encrypt and routes based on Host + PathPrefix labels.

```
Internet → Traefik → entersys-onboarding (Nginx, port 80) → React SPA
                   → onboarding-kof-api (Uvicorn, port 8000) → FastAPI
```

## IMPORTANT: Soft Limits Only
When configuring Docker resources, use ONLY `reservations` (soft limits). NEVER use `limits` (hard limits like `mem_limit`). This is a team-wide policy for EnterSys infrastructure.

## Troubleshooting

- **Frontend 404 on direct URL access**: nginx.conf has `try_files $uri $uri/ /index.html` for SPA routing
- **CORS errors**: Backend CORS allows `www.entersys.mx`, `entersys.mx`, `dev.entersys.mx`
- **Smartsheet API errors**: Check `SMARTSHEET_ACCESS_TOKEN` is valid and `SHEET_ID` is correct
- **Photo upload fails**: Verify GCS service account has write access to `entersys-onboarding-photos` bucket
- **Email not sending**: Gmail API requires service account with domain-wide delegation or app password

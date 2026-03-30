# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.endpoints import onboarding, smartsheet_webhook

app = FastAPI(
    title="Onboarding KOF API",
    description="API for KOF security onboarding: exams, certificates, credentials",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.entersys.mx",
        "https://entersys.mx",
        "https://dev.entersys.mx",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register onboarding router
app.include_router(
    onboarding.router,
    prefix="/api/v1/onboarding",
    tags=["Onboarding"],
)


app.include_router(
    smartsheet_webhook.router,
    prefix="/api/v1/smartsheet-webhook",
    tags=["Smartsheet Webhook"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "onboarding-kof-api"}

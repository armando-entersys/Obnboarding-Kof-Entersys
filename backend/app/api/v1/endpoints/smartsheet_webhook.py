# app/api/v1/endpoints/smartsheet_webhook.py
"""
Smartsheet webhook handler for the Onboarding KOF system.
Detects changes in the 'Reenviar correo' checkbox column and
triggers certificate resend in background.
"""
from fastapi import APIRouter, Header, Depends, HTTPException, Request, BackgroundTasks, status
from typing import Optional, List, Dict, Any
import logging
import httpx
import asyncio
import uuid as uuid_module
from datetime import datetime, timedelta

from app.core.config import settings
from app.services.onboarding_smartsheet_service import (
    OnboardingSmartsheetService,
    OnboardingSmartsheetServiceError,
    get_onboarding_service_singleton,
)
from app.api.v1.endpoints.onboarding import (
    resend_approved_certificate_email,
    send_qr_email,
)
from app.utils.qr_utils import generate_certificate_qr

router = APIRouter()
logger = logging.getLogger(__name__)

SHEET_REGISTROS_ID = OnboardingSmartsheetService.SHEET_REGISTROS_ID

# In-memory job tracking
_processing_jobs: Dict[str, Dict[str, Any]] = {}


def validate_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    if x_api_key != settings.MIDDLEWARE_API_KEY:
        logger.warning(f"Smartsheet webhook: invalid API key: {x_api_key[:10]}...")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


async def process_email_queue(job_id: str, row_ids: List[int]):
    """Process queued rows for certificate resend in background."""
    job = _processing_jobs.get(job_id, {})
    job.update({
        "status": "processing",
        "started_at": datetime.utcnow().isoformat(),
        "total": len(row_ids),
        "processed": 0, "success": 0, "failed": 0, "skipped": 0,
        "details": [],
    })
    _processing_jobs[job_id] = job

    logger.info(f"Job {job_id}: Processing {len(row_ids)} rows")

    service = get_onboarding_service_singleton()
    await service._get_registros_column_maps()

    for row_id in row_ids:
        result = {"row_id": row_id, "status": "pending", "email": None, "error": None}

        try:
            row_data = await service.get_row_data_by_id(row_id)
            if row_data is None:
                result.update(status="skipped", error="could not read row")
                job["skipped"] += 1
                job["details"].append(result)
                job["processed"] += 1
                continue

            resultado = str(row_data.get(service.COLUMN_RESULTADO, "")).strip().lower()
            cert_uuid = row_data.get(service.COLUMN_UUID)
            email = row_data.get(service.COLUMN_CORREO_ELECTRONICO)
            full_name = row_data.get(service.COLUMN_NOMBRE_COLABORADOR, "Colaborador")
            vencimiento = row_data.get(service.COLUMN_VENCIMIENTO)

            result["email"] = email
            result["name"] = full_name

            if not email or not str(email).strip():
                result.update(status="skipped", error="empty email")
                job["skipped"] += 1
                job["details"].append(result)
                job["processed"] += 1
                try:
                    await service.uncheck_reenviar_correo(row_id)
                except Exception:
                    pass
                continue

            collaborator_data = {
                "nombre_completo": str(full_name).strip(),
                "rfc_colaborador": row_data.get(service.COLUMN_RFC_COLABORADOR, ""),
                "rfc_empresa": row_data.get(service.COLUMN_RFC_EMPRESA, ""),
                "nss": row_data.get(service.COLUMN_NSS_COLABORADOR, ""),
                "tipo_servicio": row_data.get(service.COLUMN_TIPO_SERVICIO, ""),
                "proveedor": row_data.get(service.COLUMN_PROVEEDOR_EMPRESA, ""),
                "foto_url": row_data.get(service.COLUMN_URL_IMAGEN, ""),
            }

            section_results = {
                "Seguridad": row_data.get(service.COLUMN_SECCION1, 0),
                "Inocuidad": row_data.get(service.COLUMN_SECCION2, 0),
                "Ambiental": row_data.get(service.COLUMN_SECCION3, 0),
            }

            vencimiento_str = str(vencimiento) if vencimiento else ""
            sent = False
            max_retries = 3

            if resultado == "aprobado":
                # Generate UUID if missing
                if not cert_uuid or not str(cert_uuid).strip():
                    logger.warning(f"Job {job_id}: row {row_id} approved without UUID, generating...")
                    cert_uuid = str(uuid_module.uuid4())
                    expiration_date = datetime.utcnow() + timedelta(days=365)
                    try:
                        await service.update_certificate_data(row_id, cert_uuid, expiration_date)
                        vencimiento_str = expiration_date.strftime('%Y-%m-%d')
                    except Exception as e:
                        result.update(status="failed", error=f"could not save UUID: {e}")
                        job["failed"] += 1
                        job["details"].append(result)
                        job["processed"] += 1
                        try:
                            await service.uncheck_reenviar_correo(row_id)
                        except Exception:
                            pass
                        continue

                for attempt in range(max_retries):
                    try:
                        sent = resend_approved_certificate_email(
                            email_to=str(email).strip(),
                            full_name=str(full_name).strip(),
                            cert_uuid=str(cert_uuid).strip(),
                            expiration_date_str=vencimiento_str,
                            collaborator_data=collaborator_data,
                            section_results=section_results,
                        )
                        if sent:
                            break
                    except Exception as e:
                        logger.warning(f"Job {job_id}: Attempt {attempt+1} failed for {email}: {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(5)

            elif resultado == "reprobado":
                s1 = float(str(section_results.get("Seguridad", 0) or 0).replace('%', '').strip() or 0)
                s2 = float(str(section_results.get("Inocuidad", 0) or 0).replace('%', '').strip() or 0)
                s3 = float(str(section_results.get("Ambiental", 0) or 0).replace('%', '').strip() or 0)
                overall_score = (s1 + s2 + s3) / 3 if (s1 or s2 or s3) else 0

                ref_uuid = cert_uuid if cert_uuid else str(uuid_module.uuid4())
                qr_image = generate_certificate_qr(ref_uuid, "https://api.entersys.mx")
                exp_date = datetime.utcnow() + timedelta(days=365)

                for attempt in range(max_retries):
                    try:
                        sent = send_qr_email(
                            email_to=str(email).strip(),
                            full_name=str(full_name).strip(),
                            qr_image=qr_image,
                            expiration_date=exp_date,
                            cert_uuid=ref_uuid,
                            is_valid=False,
                            score=overall_score,
                        )
                        if sent:
                            break
                    except Exception as e:
                        logger.warning(f"Job {job_id}: Attempt {attempt+1} failed for {email} (reprobado): {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(5)
            else:
                result.update(status="skipped", error=f"unknown resultado={resultado}")
                job["skipped"] += 1
                job["details"].append(result)
                job["processed"] += 1
                try:
                    await service.uncheck_reenviar_correo(row_id)
                except Exception:
                    pass
                continue

            if sent:
                result.update(status="success", resultado=resultado)
                job["success"] += 1
                logger.info(f"Job {job_id}: Email sent to {email} ({resultado})")
            else:
                result.update(status="failed", error=f"send failed after retries ({resultado})")
                job["failed"] += 1
                logger.error(f"Job {job_id}: Failed to send to {email} ({resultado})")

            try:
                await service.uncheck_reenviar_correo(row_id)
            except Exception as e:
                logger.warning(f"Job {job_id}: Could not uncheck row {row_id}: {e}")

        except Exception as e:
            result.update(status="error", error=str(e))
            job["failed"] += 1
            logger.error(f"Job {job_id}: Error processing row {row_id}: {e}")

        job["details"].append(result)
        job["processed"] += 1
        await asyncio.sleep(3)

    job["status"] = "completed"
    job["completed_at"] = datetime.utcnow().isoformat()
    logger.info(f"Job {job_id}: Done - success={job['success']}, failed={job['failed']}, skipped={job['skipped']}")

    # Keep only last 50 jobs
    if len(_processing_jobs) > 50:
        for key in sorted(_processing_jobs.keys())[:-50]:
            del _processing_jobs[key]


@router.post(
    "/callback",
    summary="Smartsheet webhook callback",
    description="Receives change notifications from Smartsheet. "
    "Detects 'Reenviar correo' checkbox changes and queues certificate resend.",
)
async def webhook_callback(request: Request, background_tasks: BackgroundTasks):
    # Challenge phase
    challenge = request.headers.get("Smartsheet-Hook-Challenge")
    if challenge:
        logger.info("Smartsheet webhook: challenge received")
        return {"smartsheetHookResponse": challenge}

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    scope_object_id = body.get("scopeObjectId")
    if not scope_object_id or int(scope_object_id) != SHEET_REGISTROS_ID:
        logger.warning(f"Smartsheet webhook: unexpected sheet {scope_object_id}")
        return {"status": "ignored", "reason": "wrong sheet"}

    events = body.get("events", [])
    if not events:
        return {"status": "ok", "processed": 0}

    service = get_onboarding_service_singleton()
    await service._get_registros_column_maps()
    reenviar_col_id = service.get_reenviar_correo_column_id()

    if not reenviar_col_id:
        logger.error("Smartsheet webhook: 'Reenviar correo' column ID not found")
        return {"status": "error", "reason": "column_id_not_found"}

    affected_row_ids = set()
    for event in events:
        if (event.get("objectType") == "cell"
                and event.get("eventType") == "updated"
                and event.get("columnId") == reenviar_col_id):
            affected_row_ids.add(event["rowId"])

    if not affected_row_ids:
        return {"status": "ok", "queued": 0}

    job_id = f"job_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{len(affected_row_ids)}"
    rows_list = list(affected_row_ids)

    _processing_jobs[job_id] = {
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
        "total": len(rows_list),
        "row_ids": rows_list,
    }

    background_tasks.add_task(process_email_queue, job_id, rows_list)
    logger.info(f"Smartsheet webhook: Queued {len(rows_list)} rows (job_id={job_id})")

    return {
        "status": "queued",
        "job_id": job_id,
        "queued_rows": len(rows_list),
    }


@router.get("/job-status/{job_id}", summary="Job status")
async def get_job_status(job_id: str):
    job = _processing_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    response = {k: v for k, v in job.items() if k != "details"}
    if job.get("details"):
        response["details_count"] = len(job["details"])
        response["recent_details"] = job["details"][-10:]
    return response


@router.get("/jobs", summary="List recent jobs")
async def list_jobs(api_key: str = Depends(validate_api_key)):
    jobs_summary = []
    for job_id, job in sorted(_processing_jobs.items(), reverse=True):
        jobs_summary.append({
            "job_id": job_id,
            "status": job.get("status"),
            "total": job.get("total"),
            "processed": job.get("processed", 0),
            "success": job.get("success", 0),
            "failed": job.get("failed", 0),
            "created_at": job.get("created_at"),
            "completed_at": job.get("completed_at"),
        })
    return {"jobs": jobs_summary[:20]}


@router.post("/register", summary="Register webhook in Smartsheet")
async def register_webhook(api_key: str = Depends(validate_api_key)):
    callback_url = settings.SMARTSHEET_WEBHOOK_CALLBACK_URL
    if not callback_url:
        raise HTTPException(status_code=400, detail="SMARTSHEET_WEBHOOK_CALLBACK_URL not configured")

    headers = {
        "Authorization": f"Bearer {settings.SMARTSHEET_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    webhook_payload = {
        "name": "Onboarding KOF - Reenviar Correo",
        "callbackUrl": callback_url,
        "scope": "sheet",
        "scopeObjectId": SHEET_REGISTROS_ID,
        "version": 1,
        "events": ["*.*"],
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.SMARTSHEET_API_BASE_URL}/webhooks",
            json=webhook_payload, headers=headers,
        )
        resp.raise_for_status()
        webhook_id = resp.json().get("result", {}).get("id")

        if not webhook_id:
            raise HTTPException(status_code=502, detail="No webhook ID returned")

        enable_resp = await client.put(
            f"{settings.SMARTSHEET_API_BASE_URL}/webhooks/{webhook_id}",
            json={"enabled": True}, headers=headers,
        )
        enable_resp.raise_for_status()

        logger.info(f"Webhook {webhook_id} created and enabled")
        return {
            "status": "ok",
            "webhook_id": webhook_id,
            "callback_url": callback_url,
        }


@router.get("/status", summary="Webhook status")
async def webhook_status(api_key: str = Depends(validate_api_key)):
    headers = {"Authorization": f"Bearer {settings.SMARTSHEET_ACCESS_TOKEN}"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.SMARTSHEET_API_BASE_URL}/webhooks", headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

    all_webhooks = data.get("data", [])
    our_webhooks = [wh for wh in all_webhooks if wh.get("scopeObjectId") == SHEET_REGISTROS_ID]

    return {
        "status": "ok",
        "total_webhooks": len(all_webhooks),
        "registros_webhooks": len(our_webhooks),
        "webhooks": [{
            "id": wh.get("id"),
            "name": wh.get("name"),
            "enabled": wh.get("enabled"),
            "status": wh.get("status"),
            "callbackUrl": wh.get("callbackUrl"),
        } for wh in our_webhooks],
    }

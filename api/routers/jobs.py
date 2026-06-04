from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import uuid
import os
from models.schemas import Job, JobStage
from pipeline.controller import advance
from services.db import save_job, load_job
from services.sse import event_stream

router = APIRouter()


class StartJobRequest(BaseModel):
    message: str


class SendMessageRequest(BaseModel):
    message: str


@router.post("/jobs", status_code=201)
async def start_job(request: StartJobRequest):
    job = Job(job_id=str(uuid.uuid4()))
    save_job(job)

    reply = await advance(job, request.message)
    job.messages.append({"role": "user", "text": request.message})
    job.messages.append({"role": "assistant", "text": reply})
    save_job(job)

    return {
        "job_id": job.job_id,
        "reply": reply,
        "stage": job.stage
    }


@router.post("/jobs/{job_id}/message")
async def send_message(job_id: str, request: SendMessageRequest):
    job = load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.stage == JobStage.COMPLETE:
        raise HTTPException(status_code=400, detail="Job is already complete")

    if job.stage == JobStage.FAILED:
        raise HTTPException(status_code=400, detail=f"Job failed: {job.error}")

    reply = await advance(job, request.message)
    job.messages.append({"role": "user", "text": request.message})
    job.messages.append({"role": "assistant", "text": reply})
    save_job(job)

    return {
        "job_id": job.job_id,
        "reply": reply,
        "stage": job.stage
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job.job_id,
        "stage": job.stage,
        "messages": job.messages,
        "pptx_ready": job.stage == JobStage.COMPLETE,
        "error": job.error
    }


@router.get("/jobs/{job_id}/download")
async def download_pptx(job_id: str):
    job = load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.stage != JobStage.COMPLETE:
        raise HTTPException(status_code=400, detail="Presentation not ready yet")

    if not job.pptx_path or not os.path.exists(job.pptx_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=job.pptx_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename="presentation.pptx"
    )

@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    job = load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return StreamingResponse(
        event_stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
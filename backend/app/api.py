from __future__ import annotations

import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from .database import availability, book, cancel, init_db, list_appointments, list_doctors

app = FastAPI(title="Careline appointment API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET", "POST"], allow_headers=["*"])


@app.on_event("startup")
def startup() -> None:
    init_db()


class BookingRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=20)
    slot_id: int


class CancellationRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=20)
    appointment_id: int | None = None


def normalize_phone(phone: str) -> str:
    normalized = re.sub(r"[^\d+]", "", phone)
    if len(re.sub(r"\D", "", normalized)) < 7:
        raise HTTPException(422, "Please provide the caller's spoken phone number.")
    return normalized


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/doctors")
def doctors() -> list[dict]:
    return list_doctors()


@app.get("/api/appointments")
def appointments() -> list[dict]:
    return list_appointments()


@app.get("/api/availability")
def get_availability(doctor: str | None = None, speciality: str | None = None, date: str | None = None) -> list[dict]:
    return availability(doctor, speciality, date)


@app.post("/api/appointments", status_code=201)
def create_appointment(body: BookingRequest) -> dict:
    try:
        return book(normalize_phone(body.phone), body.slot_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/appointments/cancel")
def cancel_appointment(body: CancellationRequest) -> dict:
    try:
        return cancel(normalize_phone(body.phone), body.appointment_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

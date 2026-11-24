"""SQLite repository and seed data for the appointment assistant."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).resolve().parents[1] / "data" / "appointments.db"))


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, speciality TEXT NOT NULL,
            location TEXT NOT NULL, initials TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY, doctor_id INTEGER NOT NULL REFERENCES doctors(id),
            starts_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'available'
                CHECK(status IN ('available','booked')),
            UNIQUE(doctor_id, starts_at)
        );
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY, doctor_id INTEGER NOT NULL REFERENCES doctors(id),
            slot_id INTEGER NOT NULL REFERENCES slots(id), phone TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'booked' CHECK(status IN ('booked','cancelled')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_appointments_phone ON appointments(phone, status);
        """)
        if db.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] == 0:
            doctors = [
                ("Dr. Maya Patel", "Cardiology", "Riverside Medical Centre", "MP"),
                ("Dr. Arjun Mehta", "Dermatology", "Riverside Medical Centre", "AM"),
                ("Dr. Sara Kim", "Family Medicine", "Northside Clinic", "SK"),
                ("Dr. Daniel Brooks", "Orthopedics", "Northside Clinic", "DB"),
                ("Dr. Leena Rao", "Pediatrics", "Riverside Medical Centre", "LR"),
            ]
            db.executemany("INSERT INTO doctors(name,speciality,location,initials) VALUES(?,?,?,?)", doctors)
            # Upcoming slots are deterministic and easy to understand in the demo.
            times = ["09:00", "10:30", "13:00", "14:30", "16:00"]
            from datetime import date, timedelta
            for day in range(1, 6):
                d = (date.today() + timedelta(days=day)).isoformat()
                for doctor_id in range(1, len(doctors) + 1):
                    for time in times[:3 + (doctor_id % 3)]:
                        db.execute("INSERT INTO slots(doctor_id,starts_at) VALUES(?,?)", (doctor_id, f"{d}T{time}:00"))


def list_doctors() -> list[dict]:
    with connect() as db:
        doctors = db.execute("SELECT * FROM doctors ORDER BY name").fetchall()
        result = []
        for doctor in doctors:
            slots = db.execute("SELECT id,starts_at FROM slots WHERE doctor_id=? AND status='available' ORDER BY starts_at", (doctor['id'],)).fetchall()
            result.append({**dict(doctor), "available_slots": [dict(row) for row in slots]})
        return result


def list_appointments() -> list[dict]:
    with connect() as db:
        rows = db.execute("""SELECT a.id,a.phone,a.status,s.starts_at,d.name AS doctor_name,
            d.speciality,d.location FROM appointments a JOIN doctors d ON d.id=a.doctor_id
            JOIN slots s ON s.id=a.slot_id ORDER BY s.starts_at DESC""").fetchall()
        return [dict(row) for row in rows]


def appointments_for_phone(phone: str) -> list[dict]:
    with connect() as db:
        rows = db.execute("""SELECT a.id,a.phone,a.status,s.starts_at,d.name AS doctor_name,d.speciality
            FROM appointments a JOIN slots s ON s.id=a.slot_id JOIN doctors d ON d.id=a.doctor_id
            WHERE a.phone=? AND a.status='booked' ORDER BY s.starts_at""", (phone,)).fetchall()
        return [dict(row) for row in rows]


def availability(doctor_name: str | None = None, speciality: str | None = None, appointment_date: str | None = None) -> list[dict]:
    query = """SELECT s.id AS slot_id,s.starts_at,d.id AS doctor_id,d.name,d.speciality,d.location
        FROM slots s JOIN doctors d ON d.id=s.doctor_id WHERE s.status='available'"""
    args: list[str] = []
    if doctor_name:
        query += " AND lower(d.name) LIKE ?"; args.append(f"%{doctor_name.lower()}%")
    if speciality:
        query += " AND lower(d.speciality) LIKE ?"; args.append(f"%{speciality.lower()}%")
    if appointment_date:
        query += " AND date(s.starts_at)=date(?)"; args.append(appointment_date)
    query += " ORDER BY s.starts_at,d.name LIMIT 30"
    with connect() as db:
        return [dict(row) for row in db.execute(query, args).fetchall()]


def book(phone: str, slot_id: int) -> dict:
    with connect() as db:
        slot = db.execute("SELECT s.id,s.status,s.starts_at,d.name AS doctor_name,d.speciality FROM slots s JOIN doctors d ON d.id=s.doctor_id WHERE s.id=?", (slot_id,)).fetchone()
        if not slot:
            raise ValueError("That appointment slot does not exist.")
        if slot["status"] != "available":
            raise ValueError("That appointment slot has just been taken. Please choose another time.")
        result = db.execute("UPDATE slots SET status='booked' WHERE id=? AND status='available'", (slot_id,))
        if result.rowcount != 1:
            raise ValueError("That appointment slot has just been taken. Please choose another time.")
        cur = db.execute("INSERT INTO appointments(doctor_id,slot_id,phone) SELECT doctor_id,id,? FROM slots WHERE id=?", (phone, slot_id))
        return {"id": cur.lastrowid, "phone": phone, "starts_at": slot["starts_at"], "doctor_name": slot["doctor_name"], "speciality": slot["speciality"], "status": "booked"}


def cancel(phone: str, appointment_id: int | None = None) -> dict:
    with connect() as db:
        if appointment_id is None:
            appointment = db.execute("""SELECT a.id,a.slot_id,s.starts_at,d.name AS doctor_name,d.speciality
                FROM appointments a JOIN slots s ON s.id=a.slot_id JOIN doctors d ON d.id=a.doctor_id
                WHERE a.phone=? AND a.status='booked' ORDER BY s.starts_at LIMIT 1""", (phone,)).fetchone()
        else:
            appointment = db.execute("""SELECT a.id,a.slot_id,s.starts_at,d.name AS doctor_name,d.speciality
                FROM appointments a JOIN slots s ON s.id=a.slot_id JOIN doctors d ON d.id=a.doctor_id
                WHERE a.phone=? AND a.status='booked' AND a.id=?""", (phone, appointment_id)).fetchone()
        if not appointment:
            raise ValueError("I couldn't find an active appointment for that phone number.")
        db.execute("UPDATE appointments SET status='cancelled' WHERE id=?", (appointment["id"],))
        db.execute("UPDATE slots SET status='available' WHERE id=?", (appointment["slot_id"],))
        return {"id": appointment["id"], "phone": phone, "starts_at": appointment["starts_at"], "doctor_name": appointment["doctor_name"], "speciality": appointment["speciality"], "status": "cancelled"}

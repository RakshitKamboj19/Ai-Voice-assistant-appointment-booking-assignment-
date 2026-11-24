# Careline — Voice AI Doctor Appointment Assistant

A local full-stack appointment assistant with a real Pipecat voice pipeline, browser audio over the Pipecat WebSocket transport, SQLite persistence, and a React dashboard. It uses ElevenLabs Realtime STT and TTS and Gemini function calling. The demo dataset contains mock doctors and upcoming appointment slots.

## Requirements

- Python 3.11–3.14
- Node.js 18 or newer
- API keys for Google Gemini and ElevenLabs
- A browser with microphone access (localhost is treated as a secure origin)

## Setup

1. Copy `.env.example` to `backend/.env` and fill in `GOOGLE_API_KEY`, `ELEVENLABS_API_KEY`, and optionally `ELEVENLABS_VOICE_ID`. Do not commit this file.
2. Install backend dependencies:

   ```powershell
   cd backend
   py -3.12 -m venv .venv
   .venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

3. Install frontend dependencies:

   ```powershell
   cd ..\frontend
   npm install
   ```

## Run locally

Start three terminals from the project root.

Terminal 1 — dashboard API and SQLite initialization:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 2 — Pipecat voice agent and WebSocket audio transport:

```powershell
cd backend
..\.venv\Scripts\python.exe bot.py -t websocket --host 127.0.0.1 --port 7860
```

Terminal 3 — React dashboard:

```powershell
cd frontend
npm run dev
```

Open <http://localhost:5173>. Select **Start voice call** and allow microphone access. The initial agent greeting is spoken through ElevenLabs. Ask about a doctor or specialty, then speak a phone number to book or cancel. The agent should read the full number back and ask for confirmation before it changes an appointment. Dashboard data refreshes every five seconds.

## Pipeline and data

Browser microphone and speaker audio connect to Pipecat using its WebSocket transport and Protobuf frame serializer. The cascade pipeline is:

```text
Browser audio → Pipecat WebSocket → ElevenLabs Realtime STT → Gemini (tool calling)
                                                         → ElevenLabs TTS → Browser
```

Gemini has three registered function tools: `check_doctor_availability`, `book_appointment`, and `cancel_appointment`. Tool callbacks call the same SQLite repository used by the dashboard API. Booking claims a slot with a conditional update inside a transaction; cancellation restores the slot and records a cancelled appointment. No login, OTP, patient name, or caller-ID lookup is implemented. Phone numbers are used only when spoken by the caller and are stored with appointment records. The UI masks all but the last four digits.

The database is created and seeded on first API startup at `backend/data/appointments.db`. Delete that file to reset the local demo schedule. Mock appointment dates are generated relative to the first initialization date.

## Configuration

See [`.env.example`](.env.example). `GEMINI_MODEL` defaults to `gemini-3.5-flash-lite`, which returned a live response with the configured key during verification. Choose another model enabled for the key if needed. ElevenLabs Realtime STT uses the account's Scribe realtime access. `ELEVENLABS_VOICE_ID` defaults to Sarah (`EXAVITQu4vr4xnSDxMaL`), which was verified to synthesize with the configured account. Override it with another voice ID available to your account.

## Verification and known limits

An end-to-end call requires valid Gemini and ElevenLabs API credentials, microphone permission, and network access to those providers. The dashboard transcript is populated from Pipecat client transcript callbacks. The active backend must be restarted after changing model configuration.

The app is intended for local assignment demonstration. The WebSocket transport is suited to a local prototype; a public deployment should use a production WebRTC transport and HTTPS. The seed records are mock data and are not connected to a real clinic.

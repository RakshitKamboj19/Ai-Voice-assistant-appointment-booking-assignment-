"""Pipecat cascade voice agent: browser audio -> ElevenLabs STT -> Gemini tools -> ElevenLabs TTS."""
from __future__ import annotations

import os
import re
import sys
import types
from pathlib import Path

# Pipecat's development runner prints box-drawing characters on startup. The
# default Windows console encoding (often cp1252) cannot encode those glyphs
# and can abort before the WebSocket server starts.
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

# Pipecat uses sentencex only for sentence boundary detection. On managed
# Windows devices its native DLL may be blocked by Application Control; keep
# the app voice stack usable with the local pure-Python English fallback.
try:
    from sentencex import segment as _sentencex_segment
except ImportError:
    from app.sentencex_compat import segment as _sentencex_segment

    _sentencex_module = types.ModuleType("sentencex")
    _sentencex_module.segment = _sentencex_segment
    sys.modules["sentencex"] = _sentencex_module

from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext, standard_message_text
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.transports.base_transport import TransportParams
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.workers.runner import WorkerRunner
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams

from app.database import appointments_for_phone, availability, book, cancel

SYSTEM = """You are Careline, a warm and concise doctor appointment assistant. Help callers check availability, book, and cancel. Obtain identity ONLY by asking the caller to speak their phone number; do not request a name, login, OTP, or caller ID. Before either booking or cancelling, read the full phone number back and ask explicit confirmation. Do not call a mutation tool until the caller confirms. Availability checks need no phone. When availability is returned, offer a few exact doctor names, specialties, dates, and times from the returned slots; never invent general office hours or claim availability not in the results. For booking, agree on a returned slot_id and use that exact slot. For cancellation, list matching active appointments if ambiguous and confirm which one. Never claim success unless the corresponding tool succeeds. Speak in short natural sentences; do not use Markdown, bullets, asterisks, tables, or decorative punctuation. Today's date is provided by the server's current date."""


def caller_confirmed(params: FunctionCallParams, phone_number: str) -> bool:
    """Require an affirmative latest caller turn after the number was spoken back."""
    messages = getattr(getattr(params, "context", None), "messages", []) or []
    latest_user = None
    assistant_since_user = []
    assistant_before_latest_user = []
    for message in messages:
        # Pipecat contexts can contain LLMSpecificMessage objects alongside
        # standard dict messages (Gemini adds these for thought signatures).
        # Only standard messages carry the user/assistant role and readable
        # content needed for this confirmation gate.
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = standard_message_text(message)
        if role == "user":
            latest_user = content
            assistant_before_latest_user = assistant_since_user
            assistant_since_user = []
        elif role in ("assistant", "model"):
            assistant_since_user.append(content)
    digits = re.sub(r"\D", "", phone_number)
    spoken_back = any(digits and digits in re.sub(r"\D", "", text) for text in assistant_before_latest_user)
    affirmative = bool(re.match(r"\s*(yes|yeah|yep|correct|right|that's right|that is right|confirm|confirmed|please do)\b", latest_user or "", re.I))
    return spoken_back and affirmative


async def run_bot(transport, runner_args: RunnerArguments) -> None:
    from datetime import date
    stt = ElevenLabsRealtimeSTTService(api_key=os.environ["ELEVENLABS_API_KEY"])
    # gemini-2.5-flash was retired for new API users. gemini-3.8-flash returned
    # 503 for this configured account during live testing; 3.5 Flash Lite is
    # currently callable and supports the function-calling workflow.
    llm = GoogleLLMService(
        api_key=os.environ["GOOGLE_API_KEY"],
        settings=GoogleLLMService.Settings(
            model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            system_instruction=SYSTEM,
            max_tokens=512,
        ),
        # Gemini can take longer to emit its first streamed chunk than
        # Pipecat's 20s default, especially during provider load spikes.
        stream_idle_timeout_secs=60,
    )
    # Sarah is available to the configured ElevenLabs account. The previous
    # hard-coded Rachel library voice returned 402 paid_plan_required.
    tts = ElevenLabsTTSService(api_key=os.environ["ELEVENLABS_API_KEY"], settings=ElevenLabsTTSService.Settings(voice=os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")))

    async def check_doctor_availability(params: FunctionCallParams, doctor_name: str | None = None, speciality: str | None = None, date: str | None = None):
        result = availability(doctor_name, speciality, date)
        await params.result_callback({"available_slots": result, "message": "No matching available slots." if not result else "Available slots returned."})

    async def book_appointment(params: FunctionCallParams, phone_number: str, slot_id: int):
        if not caller_confirmed(params, phone_number):
            await params.result_callback({"success": False, "confirmation_required": True, "message": "Do not book yet. Read the caller's full phone number back, ask for confirmation, and wait for an affirmative reply."})
            return
        try:
            result = book(phone_number, int(slot_id))
            await params.result_callback({"success": True, "appointment": result})
        except (ValueError, KeyError) as exc:
            await params.result_callback({"success": False, "message": str(exc)})

    async def cancel_appointment(params: FunctionCallParams, phone_number: str, appointment_id: int | None = None):
        if not caller_confirmed(params, phone_number):
            await params.result_callback({"success": False, "confirmation_required": True, "message": "Do not cancel yet. Read the caller's full phone number back, ask for confirmation, and wait for an affirmative reply."})
            return
        try:
            result = cancel(phone_number, appointment_id)
            await params.result_callback({"success": True, "appointment": result})
        except (ValueError, KeyError) as exc:
            await params.result_callback({"success": False, "message": str(exc)})

    async def find_caller_appointments(params: FunctionCallParams, phone_number: str):
        await params.result_callback({"appointments": appointments_for_phone(phone_number)})

    context = LLMContext(tools=[check_doctor_availability, book_appointment, cancel_appointment, find_caller_appointments])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)
    pipeline = Pipeline([transport.input(), stt, user_aggregator, llm, tts, transport.output(), assistant_aggregator])
    worker = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True, enable_usage_metrics=True), idle_timeout_secs=runner_args.pipeline_idle_timeout_secs, processor_unusable_policy=ProcessorUnusablePolicy.END)
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        context.add_message({"role": "developer", "content": f"Today's date is {date.today().isoformat()}. Introduce yourself and ask what appointment help is needed."})
        await worker.queue_frames([LLMRunFrame()])
    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await runner.cancel()
    await runner.run()


async def bot(runner_args: RunnerArguments):
    transport_params = {
        "websocket": lambda: FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(),
        )
    }
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main
    main()

from __future__ import annotations

import hmac
import json
import os
import re
import shutil
import subprocess
import threading
import time
import traceback
import unicodedata
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import (
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from gradio_client import Client, handle_file
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask


GRADIO_URL = os.getenv(
    "VIENEU_GRADIO_URL",
    "http://127.0.0.1:7860",
).rstrip("/")

API_KEY = os.getenv("VIENEU_API_KEY", "").strip()

VOICES_FILE = Path(
    os.getenv(
        "VIENEU_VOICES_FILE",
        "/opt/VieNeu-TTS/src/vieneu/assets/voices_v3_turbo.json",
    )
)

CUSTOM_VOICES_DIR = Path(
    os.getenv(
        "VIENEU_CUSTOM_VOICES_DIR",
        "/opt/vieneu-api/custom_voices",
    )
)

UPLOAD_TMP_DIR = Path(
    os.getenv(
        "VIENEU_UPLOAD_TMP_DIR",
        "/opt/vieneu-api/upload_tmp",
    )
)

TMP_DIR = Path("/opt/vieneu-api/tmp")
OUTPUT_DIR = Path("/opt/vieneu-api/output")

MAX_UPLOAD_SIZE = 50 * 1024 * 1024

for directory in (
    CUSTOM_VOICES_DIR,
    UPLOAD_TMP_DIR,
    TMP_DIR,
    OUTPUT_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)

client: Client | None = None
model_ready = False
last_error: str | None = None
tts_lock = threading.Lock()


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    voice: str = Field(min_length=1, max_length=200)
    filename: str | None = Field(default=None, max_length=200)


def check_api_key(x_api_key: str | None) -> None:
    if not API_KEY:
        return

    if not x_api_key or not hmac.compare_digest(
        x_api_key,
        API_KEY,
    ):
        raise HTTPException(
            status_code=401,
            detail="API Key không hợp lệ.",
        )


def get_client() -> Client:
    global client

    if client is None:
        client = Client(
            GRADIO_URL,
            download_files=str(TMP_DIR),
            verbose=False,
        )

    return client


def load_model() -> Any:
    global model_ready, last_error

    try:
        gradio = get_client()

        with tts_lock:
            result = gradio.predict(
                "VieNeu-TTS-v3-Turbo (int8)",
                "NeuCodec (Distill)",
                "Auto",
                False,
                "",
                None,
                "",
                api_name="/load_model",
            )

        model_ready = True
        last_error = None
        return result

    except Exception as exc:
        model_ready = False
        last_error = str(exc)
        raise


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("đ", "d")
    value = unicodedata.normalize("NFD", value)
    value = "".join(
        char
        for char in value
        if unicodedata.category(char) != "Mn"
    )
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")

    if not value:
        value = f"voice-{uuid.uuid4().hex[:8]}"

    return value[:64]


def validate_voice_id(voice_id: str) -> str:
    if not re.fullmatch(
        r"[a-z0-9][a-z0-9_-]{0,63}",
        voice_id,
    ):
        raise HTTPException(
            status_code=400,
            detail="voice_id không hợp lệ.",
        )

    return voice_id


def read_preset_voices() -> list[dict[str, Any]]:
    if not VOICES_FILE.exists():
        return []

    with VOICES_FILE.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    presets = data.get("presets", {})

    if not isinstance(presets, dict):
        return []

    voices: list[dict[str, Any]] = []

    for voice_id, metadata in presets.items():
        if not isinstance(metadata, dict):
            metadata = {}

        voices.append(
            {
                "id": str(voice_id),
                "name": str(voice_id),
                "type": "preset",
                "description": str(
                    metadata.get("description", "")
                ),
                "enabled": True,
            }
        )

    return sorted(
        voices,
        key=lambda item: item["name"].casefold(),
    )


def read_custom_voices() -> list[dict[str, Any]]:
    voices: list[dict[str, Any]] = []

    if not CUSTOM_VOICES_DIR.exists():
        return voices

    for voice_dir in CUSTOM_VOICES_DIR.iterdir():
        if not voice_dir.is_dir():
            continue

        metadata_file = voice_dir / "voice.json"
        reference_file = voice_dir / "reference.wav"

        if not metadata_file.exists():
            continue

        if not reference_file.exists():
            continue

        try:
            with metadata_file.open(
                "r",
                encoding="utf-8",
            ) as handle:
                metadata = json.load(handle)

            metadata["type"] = "custom"
            metadata["audio_path"] = str(reference_file)
            voices.append(metadata)

        except (OSError, json.JSONDecodeError):
            continue

    return sorted(
        voices,
        key=lambda item: str(
            item.get("name", "")
        ).casefold(),
    )


def get_custom_voice(
    voice_id: str,
) -> dict[str, Any] | None:
    voice_dir = CUSTOM_VOICES_DIR / voice_id
    metadata_file = voice_dir / "voice.json"
    reference_file = voice_dir / "reference.wav"

    if not metadata_file.exists():
        return None

    if not reference_file.exists():
        return None

    try:
        with metadata_file.open(
            "r",
            encoding="utf-8",
        ) as handle:
            metadata = json.load(handle)

        metadata["type"] = "custom"
        metadata["audio_path"] = str(reference_file)
        return metadata

    except (OSError, json.JSONDecodeError):
        return None


def process_reference_audio(
    source: Path,
    destination: Path,
    denoise: bool,
    trim_silence: bool,
) -> None:
    filters: list[str] = []

    # Chỉ cắt khoảng lặng ở đầu file.
    # Không dừng tại khoảng nghỉ giữa câu.
    if trim_silence:
        filters.append(
            "silenceremove="
            "start_periods=1:"
            "start_duration=0.15:"
            "start_threshold=-50dB"
        )

    # Chỉ khử nhiễu nhẹ.
    if denoise:
        filters.append("afftdn=nf=-35")

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "48000",
    ]

    if filters:
        command.extend([
            "-af",
            ",".join(filters),
        ])

    command.extend([
        "-t",
        "8",
        str(destination),
    ])

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or "FFmpeg xử lý file thất bại."
        )

    if not destination.exists():
        raise RuntimeError(
            "Không tạo được reference.wav."
        )

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(destination),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    try:
        duration = float(probe.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(
            "Không xác định được thời lượng file mẫu."
        ) from exc

    if duration < 3:
        raise RuntimeError(
            f"File mẫu sau xử lý chỉ dài {duration:.2f} giây. "
            "Hãy dùng đoạn giọng rõ dài từ 3 đến 8 giây."
        )

    if destination.stat().st_size < 1000:
        raise RuntimeError(
            "File giọng sau xử lý không hợp lệ."
        )

def extract_audio_path(result: Any) -> Path:
    def collect_candidates(value: Any):
        if value is None:
            return

        if isinstance(value, Path):
            yield str(value)
            return

        if isinstance(value, str):
            value = value.strip()

            if value:
                yield value

            return

        if isinstance(value, dict):
            for key in ("path", "url", "name"):
                candidate = value.get(key)

                if candidate:
                    yield from collect_candidates(candidate)

            for nested_value in value.values():
                yield from collect_candidates(nested_value)

            return

        if isinstance(value, (list, tuple)):
            for nested_value in value:
                yield from collect_candidates(nested_value)

            return

        for attribute in ("path", "url", "name"):
            candidate = getattr(value, attribute, None)

            if candidate:
                yield from collect_candidates(candidate)

    checked: set[str] = set()

    for candidate in collect_candidates(result):
        candidate = str(candidate).strip()

        if not candidate or candidate in checked:
            continue

        checked.add(candidate)

        if candidate.startswith(("http://", "https://")):
            destination = (
                TMP_DIR
                / f"download-{uuid.uuid4().hex}.wav"
            )

            with httpx.stream(
                "GET",
                candidate,
                timeout=300,
                follow_redirects=True,
            ) as response:
                response.raise_for_status()

                with destination.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)

            if destination.exists():
                return destination

            continue

        try:
            source_path = Path(candidate)

            if source_path.exists() and source_path.is_file():
                return source_path

        except (OSError, ValueError):
            continue

    result_text = repr(result)

    if len(result_text) > 2000:
        result_text = result_text[:2000] + "..."

    raise RuntimeError(
        "Không tìm thấy file âm thanh trong kết quả Gradio. "
        f"Kết quả: {result_text}"
    )


GRADIO_MODE_FN_INDEXES = {
    "preset_mode": 2,
    "custom_mode": 3,
}


def set_gradio_mode(
    gradio: Client,
    mode: str,
) -> None:
    fn_index = GRADIO_MODE_FN_INDEXES.get(mode)

    if fn_index is None:
        raise RuntimeError(
            f"Chế độ Gradio không hợp lệ: {mode}"
        )

    result = gradio.predict(
        fn_index=fn_index,
    )

    print(
        f"Gradio mode changed: {mode}, "
        f"fn_index={fn_index}, result={result!r}",
        flush=True,
    )


def generate_wav(request: TTSRequest) -> Path:
    global last_error

    if not model_ready:
        load_model()

    gradio = get_client()
    custom_voice = get_custom_voice(
        request.voice
    )

    try:
        with tts_lock:
            if custom_voice:
                reference_path = Path(
                    custom_voice["audio_path"]
                )

                set_gradio_mode(
                    gradio,
                    "custom_mode",
                )

                result = gradio.predict(
                    param_0=request.text.strip(),
                    param_1=None,
                    param_2=handle_file(
                        str(reference_path)
                    ),
                    param_3=str(
                        custom_voice.get(
                            "reference_text",
                            "",
                        )
                    ),
                    param_5="Standard (Một lần)",
                    param_6=True,
                    param_7=1,
                    param_8=0.1,
                    param_9=128,
                    param_10="Tự nhiên",
                    param_11=True,
                    api_name="/wrapper",
                )

            else:
                set_gradio_mode(
                    gradio,
                    "preset_mode",
                )

                result = gradio.predict(
                    param_0=request.text.strip(),
                    param_1=request.voice.strip(),
                    param_2=None,
                    param_3=None,
                    param_5="Standard (Một lần)",
                    param_6=True,
                    param_7=1,
                    param_8=0.1,
                    param_9=128,
                    param_10="Tự nhiên",
                    param_11=True,
                    api_name="/wrapper",
                )

        print("Gradio wrapper result:", repr(result), flush=True)
        source_path = extract_audio_path(result)

        if request.filename:
            filename = Path(
                request.filename
            ).name
        else:
            filename = (
                f"vieneu-{uuid.uuid4().hex}.wav"
            )

        if not filename.lower().endswith(".wav"):
            filename += ".wav"

        destination = OUTPUT_DIR / filename
        shutil.copy2(source_path, destination)

        last_error = None
        return destination

    except Exception as exc:
        last_error = str(exc)
        raise


def remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global last_error

    for attempt in range(30):
        try:
            load_model()
            print("VieNeu model preload OK")
            break

        except Exception as exc:
            last_error = str(exc)
            print(
                f"Waiting for VieNeu "
                f"{attempt + 1}/30: {exc}"
            )
            time.sleep(3)

    yield


app = FastAPI(
    title="VieNeu-TTS REST API",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/")
def root():
    return {
        "service": "VieNeu-TTS REST API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/api/health")
def health():
    try:
        response = httpx.get(
            f"{GRADIO_URL}/config",
            timeout=5,
        )
        gradio_online = response.is_success

    except Exception:
        gradio_online = False

    return {
        "status": (
            "ok"
            if gradio_online and model_ready
            else "degraded"
        ),
        "gradio_online": gradio_online,
        "model_ready": model_ready,
        "preset_voices": len(
            read_preset_voices()
        ),
        "custom_voices": len(
            read_custom_voices()
        ),
        "last_error": last_error,
    }


@app.get("/api/voices")
def voices(
    x_api_key: str | None = Header(default=None),
):
    check_api_key(x_api_key)

    preset = read_preset_voices()
    custom = read_custom_voices()
    items = preset + custom

    return {
        "count": len(items),
        "preset_count": len(preset),
        "custom_count": len(custom),
        "voices": items,
    }


@app.get("/api/custom-voices")
def custom_voices(
    x_api_key: str | None = Header(default=None),
):
    check_api_key(x_api_key)

    items = read_custom_voices()

    return {
        "count": len(items),
        "voices": items,
    }


@app.post("/api/custom-voices")
async def create_custom_voice(
    audio: UploadFile = File(...),
    name: str = Form(...),
    voice_id: str | None = Form(default=None),
    gender: str = Form(default=""),
    region: str = Form(default=""),
    style: str = Form(default=""),
    description: str = Form(default=""),
    reference_text: str = Form(default=""),
    denoise: bool = Form(default=True),
    trim_silence: bool = Form(default=True),
    x_api_key: str | None = Header(default=None),
):
    check_api_key(x_api_key)

    name = name.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Tên giọng không được để trống.",
        )

    filename = audio.filename or ""

    if Path(filename).suffix.lower() != ".wav":
        raise HTTPException(
            status_code=400,
            detail="Chỉ chấp nhận file WAV.",
        )

    final_voice_id = slugify(
        voice_id or name
    )
    validate_voice_id(final_voice_id)

    destination_dir = (
        CUSTOM_VOICES_DIR / final_voice_id
    )

    if destination_dir.exists():
        raise HTTPException(
            status_code=409,
            detail=(
                f"Giọng {final_voice_id} "
                "đã tồn tại."
            ),
        )

    work_dir = (
        UPLOAD_TMP_DIR / uuid.uuid4().hex
    )
    work_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    original_file = work_dir / "original.wav"
    reference_file = work_dir / "reference.wav"

    try:
        total_size = 0

        with original_file.open("wb") as handle:
            while True:
                chunk = await audio.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            "File vượt quá giới hạn "
                            "50 MB."
                        ),
                    )

                handle.write(chunk)

        process_reference_audio(
            source=original_file,
            destination=reference_file,
            denoise=denoise,
            trim_silence=trim_silence,
        )

        metadata = {
            "id": final_voice_id,
            "name": name,
            "type": "custom",
            "gender": gender.strip(),
            "region": region.strip(),
            "style": style.strip(),
            "description": description.strip(),
            "reference_text": (
                reference_text.strip()
            ),
            "enabled": True,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        with (
            work_dir / "voice.json"
        ).open("w", encoding="utf-8") as handle:
            json.dump(
                metadata,
                handle,
                ensure_ascii=False,
                indent=2,
            )

        os.replace(
            work_dir,
            destination_dir,
        )

        metadata["audio_path"] = str(
            destination_dir / "reference.wav"
        )

        return {
            "success": True,
            "voice": metadata,
        }

    except HTTPException:
        shutil.rmtree(
            work_dir,
            ignore_errors=True,
        )
        raise

    except Exception as exc:
        shutil.rmtree(
            work_dir,
            ignore_errors=True,
        )

        raise HTTPException(
            status_code=500,
            detail=f"Lưu giọng thất bại: {exc}",
        ) from exc


@app.get(
    "/api/custom-voices/{voice_id}/audio"
)
def custom_voice_audio(
    voice_id: str,
    x_api_key: str | None = Header(default=None),
):
    check_api_key(x_api_key)
    validate_voice_id(voice_id)

    voice = get_custom_voice(voice_id)

    if not voice:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy giọng.",
        )

    audio_path = Path(voice["audio_path"])

    return FileResponse(
        audio_path,
        media_type="audio/wav",
        filename=f"{voice_id}.wav",
    )


@app.delete("/api/custom-voices/{voice_id}")
def delete_custom_voice(
    voice_id: str,
    x_api_key: str | None = Header(default=None),
):
    check_api_key(x_api_key)
    validate_voice_id(voice_id)

    voice_dir = CUSTOM_VOICES_DIR / voice_id

    if not voice_dir.exists():
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy giọng.",
        )

    shutil.rmtree(voice_dir)

    return {
        "success": True,
        "deleted_voice": voice_id,
    }


@app.post("/api/preload")
def preload(
    x_api_key: str | None = Header(default=None),
):
    check_api_key(x_api_key)

    try:
        load_model()

        return {
            "success": True,
            "model_ready": True,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Load model thất bại: {exc}",
        ) from exc


@app.post("/api/tts")
def create_tts(
    request: TTSRequest,
    x_api_key: str | None = Header(default=None),
):
    check_api_key(x_api_key)

    preset_ids = {
        item["id"]
        for item in read_preset_voices()
    }

    custom_ids = {
        item["id"]
        for item in read_custom_voices()
    }

    if (
        request.voice not in preset_ids
        and request.voice not in custom_ids
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Không tìm thấy giọng: "
                f"{request.voice}"
            ),
        )

    try:
        audio_path = generate_wav(request)

    except Exception as exc:
        print(
            "TTS EXCEPTION:",
            repr(exc),
            flush=True,
        )
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=f"Tạo giọng thất bại: {exc}",
        ) from exc

    return FileResponse(
        path=audio_path,
        media_type="audio/wav",
        filename=audio_path.name,
        background=BackgroundTask(
            remove_file,
            audio_path,
        ),
    )


VOICE_MANAGER_HTML = Path(
    "/opt/vieneu-api/voice-manager.html"
)


@app.get(
    "/voice-manager",
    include_in_schema=False,
)
def voice_manager_page():
    if not VOICE_MANAGER_HTML.exists():
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy giao diện quản lý giọng.",
        )

    return FileResponse(
        path=VOICE_MANAGER_HTML,
        media_type="text/html",
    )

"""JSONL chat file parsing and GPG decryption."""

import getpass
import json
import shutil
import subprocess
from datetime import datetime

from .models import Chat, Message, Swipe


def _parse_gen_seconds(obj: dict) -> float:
    started = obj.get("gen_started", "")
    finished = obj.get("gen_finished", "")
    if started and finished:
        try:
            fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
            dt_s = datetime.strptime(started, fmt)
            dt_f = datetime.strptime(finished, fmt)
            return max(0.0, (dt_f - dt_s).total_seconds())
        except (ValueError, TypeError):
            pass
    return 0.0


def _format_time(ts: str) -> str:
    """'2026-06-24T03:12:02.044Z' -> '3:12am'"""
    if not ts:
        return ""
    try:
        raw = ts.rstrip("Z")
        if "." in raw:
            dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f")
        else:
            dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%-I:%M%p").lower()
    except (ValueError, TypeError):
        return ts


def _format_date(ts: str) -> str:
    """'2026-06-24T03:12:02.044Z' -> '2026-06-24'"""
    if not ts:
        return ""
    try:
        return ts[:10]
    except (ValueError, TypeError):
        return ""


GPG_ARMOR = b"-----BEGIN PGP MESSAGE-----"


def _is_gpg_file(path: str) -> bool:
    with open(path, "rb") as f:
        header = f.read(64)
    if not header:
        return False
    # GPG binary packets always have bit 7 set in the first byte
    if header[0] & 0x80:
        return True
    return GPG_ARMOR in header


def _decrypt_gpg(path: str) -> str:
    """Decrypt a GPG file in memory, prompting for passphrase. Returns plaintext."""
    if not shutil.which("gpg"):
        raise RuntimeError("GPG encrypted file detected but 'gpg' is not installed or not in PATH")
    passphrase = getpass.getpass("GPG passphrase: ")
    result = subprocess.run(
        ["gpg", "--decrypt", "--batch", "--yes",
         "--passphrase-fd", "0", "--no-tty", path],
        input=passphrase.encode(),
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")
        raise RuntimeError(f"GPG decryption failed: {stderr}")
    return result.stdout.decode()


def load_chat(path: str) -> Chat:
    """Load a chat from a JSONL file, decrypting with GPG if needed."""
    if _is_gpg_file(path):
        text = _decrypt_gpg(path)
        lines = text.splitlines()
    else:
        with open(path) as f:
            lines = f.readlines()
    return parse_chat(lines)


def parse_chat(lines: list[str]) -> Chat:
    messages = []
    title = ""
    chat_date = ""
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        obj = json.loads(line)
        if i == 0 and "chat_metadata" in obj:
            continue
        name = obj.get("name", "???")
        is_user = obj.get("is_user", False)
        is_system = obj.get("is_system", False)
        timestamp = obj.get("send_date", "")
        swipe_texts = obj.get("swipes", [])
        swipe_infos = obj.get("swipe_info", [])
        active_swipe = obj.get("swipe_id", 0) or 0

        if not title and obj.get("title"):
            title = obj["title"]
        if not chat_date and timestamp:
            chat_date = _format_date(timestamp)

        main_text = obj.get("mes", "")
        main_extra = obj.get("extra", {})
        main_reasoning = main_extra.get("reasoning", "") or ""
        main_model = main_extra.get("model", "") or ""
        main_tokens = main_extra.get("token_count", 0) or 0
        main_gen = _parse_gen_seconds(obj)

        if swipe_texts:
            swipes = []
            for j, st in enumerate(swipe_texts):
                reasoning = ""
                model = ""
                tokens = 0
                gen_secs = 0.0
                if j < len(swipe_infos):
                    si = swipe_infos[j]
                    si_extra = si.get("extra", {})
                    reasoning = si_extra.get("reasoning", "") or ""
                    model = si_extra.get("model", "") or ""
                    tokens = si_extra.get("token_count", 0) or 0
                    gen_secs = _parse_gen_seconds(si)
                if j == active_swipe:
                    reasoning = reasoning or main_reasoning
                    model = model or main_model
                    tokens = tokens or main_tokens
                    gen_secs = gen_secs or main_gen
                swipes.append(Swipe(text=st, reasoning=reasoning,
                                    model=model, token_count=tokens,
                                    gen_seconds=gen_secs))
        else:
            swipes = [Swipe(text=main_text, reasoning=main_reasoning,
                            model=main_model, token_count=main_tokens,
                            gen_seconds=main_gen)]

        messages.append(Message(
            name=name, is_user=is_user, is_system=is_system,
            timestamp=timestamp, swipes=swipes, active_swipe=active_swipe,
        ))

    if not title and messages:
        title = messages[0].name

    return Chat(title=title, date=chat_date, messages=messages)

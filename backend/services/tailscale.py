"""LLMWikiNG – Tailscale & Funnel Integration Service.

Manages Tailscale authentication, serve (Tailnet-private proxy),
and funnel (public HTTP/HTTPS proxy) in same-container deployment.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import DATA_DIR
from core.security import encrypt_tailscale_key, decrypt_tailscale_key, verify_password

log = logging.getLogger("llmwiking.tailscale")

CONFIG_PATH = DATA_DIR / "tailscale.json"
SERVE_CONFIG_HOST_DIR = Path(os.getenv("TS_CONFIG_DIR", "/config/tailscale"))
SERVE_CONFIG_PATH = SERVE_CONFIG_HOST_DIR / "serve.json"

DEFAULT_APP_PORT = int(os.getenv("APP_PORT") or os.getenv("PORT") or "8080")

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "hostname": "zerodot1sllmwiking",
    "auth_key_encrypted": None,
    "auth_key_hint": None,
    "app_port": DEFAULT_APP_PORT,
    "funnel_port": 443,
    "funnel_enabled": False,
    "serve_enabled": True,
    "serve_path": "/",
    "extra_args": "",
    "last_status": {},
    "updated_at": None,
    "updated_by": None,
}


def load_config() -> dict[str, Any]:
    """Loads Tailscale configuration from data/tailscale.json."""
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return {**DEFAULTS, **data}
        except Exception as e:
            log.warning("tailscale.json read error: %s", e)
    return dict(DEFAULTS)


def save_config(cfg: dict[str, Any]) -> None:
    """Saves Tailscale configuration to data/tailscale.json securely."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg["updated_at"] = datetime.now(timezone.utc).isoformat()
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    try:
        CONFIG_PATH.chmod(0o600)
    except Exception:
        pass


def _which_tailscale() -> str | None:
    return shutil.which("tailscale")


async def _run(cmd: list[str], timeout: float = 60.0) -> tuple[int, str, str]:
    """Executes a shell command asynchronously and returns (code, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutExpired:
            proc.kill()
            await proc.wait()
            return 124, "", "command timeout"
        return (
            proc.returncode or 0,
            out_b.decode("utf-8", errors="replace"),
            err_b.decode("utf-8", errors="replace"),
        )
    except Exception as e:
        return 1, "", str(e)


def build_serve_config(cfg: dict[str, Any], cert_domain: str | None = None) -> dict[str, Any]:
    """Generates serve.json configuration structure for Tailscale."""
    domain = cert_domain or "${TS_CERT_DOMAIN}"
    port = int(cfg.get("funnel_port") or 443)
    app_port = int(cfg.get("app_port") or DEFAULT_APP_PORT)
    path = cfg.get("serve_path") or "/"
    key = f"{domain}:{port}"
    return {
        "TCP": {str(port): {"HTTPS": True}},
        "Web": {
            key: {
                "Handlers": {
                    path: {"Proxy": f"http://127.0.0.1:{app_port}"}
                }
            }
        },
        "AllowFunnel": {key: bool(cfg.get("funnel_enabled"))},
    }


def write_serve_config(cfg: dict[str, Any], cert_domain: str | None = None) -> Path | None:
    """Writes serve.json configuration file if host directory is writable."""
    try:
        SERVE_CONFIG_HOST_DIR.mkdir(parents=True, exist_ok=True)
        data = build_serve_config(cfg, cert_domain)
        SERVE_CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return SERVE_CONFIG_PATH
    except Exception as e:
        log.warning("Could not write serve.json: %s", e)
        return None


async def get_status() -> dict[str, Any]:
    """Fetches live status from Tailscale daemon."""
    if not _which_tailscale():
        return {
            "available": False,
            "backend_state": "NotInstalled",
            "error": "tailscale binary not found in container PATH",
        }

    code, out, err = await _run(["tailscale", "status", "--json"])
    if code != 0:
        return {
            "available": True,
            "backend_state": "Stopped",
            "error": err.strip() or out.strip() or f"exit code {code}",
        }

    try:
        st = json.loads(out)
    except Exception:
        return {
            "available": True,
            "backend_state": "Unknown",
            "error": "invalid status JSON output",
            "raw": out[:500],
        }

    self_info = st.get("Self") or {}
    dns_name = self_info.get("DNSName", "").rstrip(".")
    ips = self_info.get("TailscaleIPs") or []

    funnel_info = {}
    code2, out2, _ = await _run(["tailscale", "funnel", "status", "--json"])
    if code2 == 0 and out2.strip():
        try:
            funnel_info = json.loads(out2)
        except Exception:
            pass

    serve_info = {}
    code3, out3, _ = await _run(["tailscale", "serve", "status", "--json"])
    if code3 == 0 and out3.strip():
        try:
            serve_info = json.loads(out3)
        except Exception:
            pass

    funnel_urls = []
    if dns_name:
        fport = 443
        funnel_urls.append(f"https://{dns_name}:{fport}" if fport != 443 else f"https://{dns_name}")

    return {
        "available": True,
        "backend_state": st.get("BackendState", "Unknown"),
        "dns_name": dns_name,
        "tailscale_ips": ips,
        "online": self_info.get("Online", False),
        "funnel_urls": funnel_urls,
        "funnel": funnel_info,
        "serve": serve_info,
        "https_cert_ok": bool(dns_name and self_info.get("Online")),
    }


async def up(cfg: dict[str, Any], raw_auth_key: str | None = None) -> dict[str, Any]:
    """Runs `tailscale up` with configured parameters."""
    if not _which_tailscale():
        return {"ok": False, "error": "tailscale binary not found"}

    key = raw_auth_key
    if not key and cfg.get("auth_key_encrypted"):
        key = decrypt_tailscale_key(cfg["auth_key_encrypted"])
    if not key:
        return {"ok": False, "error": "No Auth key configured"}

    cmd = [
        "tailscale", "up",
        f"--authkey={key}",
        f"--hostname={cfg.get('hostname') or 'zerodot1sllmwiking'}",
        "--accept-dns=true",
    ]
    extra = (cfg.get("extra_args") or "").strip()
    if extra:
        cmd.extend(extra.split())

    code, out, err = await _run(cmd, timeout=120.0)
    return {"ok": code == 0, "stdout": out, "stderr": err, "code": code}


async def down() -> dict[str, Any]:
    """Runs `tailscale down` to disconnect from Tailnet."""
    if not _which_tailscale():
        return {"ok": False, "error": "tailscale binary not found"}

    code, out, err = await _run(["tailscale", "down"])
    return {"ok": code == 0, "stdout": out, "stderr": err}


async def apply_serve_funnel(cfg: dict[str, Any]) -> dict[str, Any]:
    """Applies `tailscale serve` and `tailscale funnel` settings via CLI."""
    if not _which_tailscale():
        return {"ok": False, "error": "tailscale binary not found"}

    app_port = int(cfg.get("app_port") or DEFAULT_APP_PORT)
    fport = int(cfg.get("funnel_port") or 443)
    target = f"http://127.0.0.1:{app_port}"
    results = []

    # Serve (Tailnet private)
    if cfg.get("serve_enabled", True):
        code, out, err = await _run(
            ["tailscale", "serve", "--bg", f"--https={fport}", target]
        )
        results.append({"step": "serve", "ok": code == 0, "out": out, "err": err})

    # Funnel (Public internet)
    if cfg.get("funnel_enabled"):
        code, out, err = await _run(
            ["tailscale", "funnel", "--bg", f"--https={fport}", target]
        )
        results.append({"step": "funnel", "ok": code == 0, "out": out, "err": err})
    else:
        # Turn off Funnel while keeping Serve
        c_res, o_res, e_res = await _run(["tailscale", "funnel", "reset"])
        results.append({"step": "funnel_reset", "ok": c_res == 0, "out": o_res, "err": e_res})

    write_serve_config(cfg)
    status = await get_status()
    return {"ok": all(r.get("ok") for r in results), "steps": results, "status": status}


async def reset_funnel_serve() -> dict[str, Any]:
    """Resets tailscale funnel and serve configurations."""
    if not _which_tailscale():
        return {"ok": False, "error": "tailscale binary not found"}

    c1, o1, e1 = await _run(["tailscale", "funnel", "reset"])
    c2, o2, e2 = await _run(["tailscale", "serve", "reset"])
    status = await get_status()
    return {
        "ok": c1 == 0 and c2 == 0,
        "funnel_reset": {"code": c1, "out": o1, "err": e1},
        "serve_reset": {"code": c2, "out": o2, "err": e2},
        "status": status,
    }


async def setup_all(
    *,
    hostname: str,
    auth_key: str | None,
    app_port: int,
    funnel_port: int,
    funnel_enabled: bool,
    serve_enabled: bool,
    extra_args: str,
    actor: str,
) -> dict[str, Any]:
    """One-Click setup: Save config -> tailscale up -> apply serve/funnel -> get status."""
    cfg = load_config()
    cfg["hostname"] = (hostname or "zerodot1sllmwiking").strip()
    cfg["app_port"] = int(app_port)
    cfg["funnel_port"] = int(funnel_port)
    cfg["funnel_enabled"] = bool(funnel_enabled)
    cfg["serve_enabled"] = bool(serve_enabled)
    cfg["extra_args"] = (extra_args or "").strip()
    cfg["enabled"] = True
    cfg["updated_by"] = actor

    if auth_key and auth_key.strip():
        clean_key = auth_key.strip()
        cfg["auth_key_encrypted"] = encrypt_tailscale_key(clean_key)
        hint_start = clean_key[:12] if len(clean_key) >= 12 else clean_key[:4]
        hint_end = clean_key[-4:] if len(clean_key) >= 4 else ""
        cfg["auth_key_hint"] = f"{hint_start}…{hint_end}"

    save_config(cfg)

    up_res = await up(cfg, raw_auth_key=auth_key)
    if not up_res.get("ok"):
        cfg["last_status"] = {"error": up_res.get("stderr") or up_res.get("error")}
        save_config(cfg)
        return {"ok": False, "step": "up", **up_res}

    apply_res = await apply_serve_funnel(cfg)
    status = apply_res.get("status") or await get_status()
    cfg["last_status"] = {
        **status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "error": None if apply_res.get("ok") else "serve/funnel partial failure",
    }
    save_config(cfg)
    return {"ok": apply_res.get("ok", False), "up": up_res, "apply": apply_res, "status": status}


def reveal_auth_key(password: str, user_password_hash: str) -> str | None:
    """Verifies user password and decrypts stored Tailscale auth key."""
    if not password or not verify_password(password, user_password_hash):
        return None
    cfg = load_config()
    enc_key = cfg.get("auth_key_encrypted")
    if not enc_key:
        return None
    return decrypt_tailscale_key(enc_key)

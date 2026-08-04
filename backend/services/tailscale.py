# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
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
import shlex
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import DATA_DIR
from core.security import encrypt_tailscale_key, decrypt_tailscale_key, verify_password

log = logging.getLogger("llmwiking.tailscale")

CONFIG_PATH = DATA_DIR / "tailscale.json"
SERVE_CONFIG_HOST_DIR = Path(os.getenv("TS_CONFIG_DIR", "/config/tailscale"))
SERVE_CONFIG_PATH = SERVE_CONFIG_HOST_DIR / "serve.json"
STATE_DIR = Path(os.getenv("TS_STATE_DIR", "/var/lib/tailscale"))
PID_FILE = STATE_DIR / "tailscaled.pid"

DEFAULT_APP_PORT = int(os.getenv("APP_PORT") or os.getenv("PORT") or "8080")

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "hostname": "llmwiking",
    "auth_key_encrypted": None,
    "auth_key_hint": None,
    "app_port": DEFAULT_APP_PORT,
    "proxy_target": None,
    "funnel_port": 443,
    "funnel_enabled": False,
    "serve_enabled": True,
    "serve_path": "/",
    "extra_args": "",
    "last_status": {},
    "updated_at": None,
    "updated_by": None,
}


def get_proxy_target(cfg: dict[str, Any]) -> str:
    """Returns the configured proxy target URL or defaults to http://127.0.0.1:<app_port>."""
    target = (cfg.get("proxy_target") or "").strip()
    if target:
        if not target.startswith("http://") and not target.startswith("https://"):
            target = f"http://{target}"
        return target
    app_port = int(cfg.get("app_port") or DEFAULT_APP_PORT)
    return f"http://127.0.0.1:{app_port}"


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
    from core.config import _atomic_write
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write(CONFIG_PATH, json.dumps(cfg, indent=2, ensure_ascii=False))
    try:
        CONFIG_PATH.chmod(0o600)
    except Exception:
        pass


def _which_tailscale() -> str | None:
    return shutil.which("tailscale")


async def _run(cmd: list[str], timeout: float = 60.0, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Executes a shell command asynchronously and returns (code, stdout, stderr)."""
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=run_env,
        )
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except (asyncio.TimeoutError, TimeoutError):
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


def _check_https_cert(dns_name: str, serve_info: dict[str, Any], funnel_info: dict[str, Any]) -> bool:
    """Checks whether an actual HTTPS SSL/TLS certificate exists or is active."""
    if not dns_name:
        return False

    # 1. Check certificate files on disk
    possible_paths = [
        STATE_DIR / "certs" / f"{dns_name}.crt",
        STATE_DIR / f"{dns_name}.crt",
        SERVE_CONFIG_HOST_DIR / f"{dns_name}.crt",
        STATE_DIR / "certs" / f"{dns_name}.key",
    ]
    if any(p.exists() and p.stat().st_size > 0 for p in possible_paths):
        return True

    # 2. Check active serve / funnel HTTPS configuration
    def _has_active_https(info: dict[str, Any]) -> bool:
        if not isinstance(info, dict):
            return False
        tcp = info.get("TCP") or {}
        for port_data in tcp.values():
            if isinstance(port_data, dict) and port_data.get("HTTPS"):
                return True
        web = info.get("Web") or {}
        for web_key in web:
            if dns_name in web_key:
                return True
        return False

    return _has_active_https(serve_info) or _has_active_https(funnel_info)


def build_serve_config(cfg: dict[str, Any], cert_domain: str | None = None) -> dict[str, Any]:
    """Generates serve.json configuration structure for Tailscale."""
    domain = cert_domain or "${TS_CERT_DOMAIN}"
    port = int(cfg.get("funnel_port") or 443)
    proxy_target = get_proxy_target(cfg)
    path = cfg.get("serve_path") or "/"
    key = f"{domain}:{port}"
    return {
        "TCP": {str(port): {"HTTPS": True}},
        "Web": {
            key: {
                "Handlers": {
                    path: {"Proxy": proxy_target}
                }
            }
        },
        "AllowFunnel": {key: bool(cfg.get("funnel_enabled"))},
    }


def write_serve_config(cfg: dict[str, Any], cert_domain: str | None = None) -> Path | None:
    """Writes serve.json configuration file if host directory is writable."""
    try:
        from core.config import _atomic_write
        SERVE_CONFIG_HOST_DIR.mkdir(parents=True, exist_ok=True)
        data = build_serve_config(cfg, cert_domain)
        _atomic_write(SERVE_CONFIG_PATH, json.dumps(data, indent=2, ensure_ascii=False))
        return SERVE_CONFIG_PATH
    except Exception as e:
        log.warning("Could not write serve.json: %s", e)
        return None


async def get_status(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetches live status from Tailscale daemon."""
    if cfg is None:
        cfg = load_config()

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
        fport = int(cfg.get("funnel_port") or 443)
        funnel_urls.append(f"https://{dns_name}:{fport}" if fport != 443 else f"https://{dns_name}")

    is_online = bool(self_info.get("Online"))
    https_cert_ok = _check_https_cert(dns_name, serve_info, funnel_info)

    return {
        "available": True,
        "backend_state": st.get("BackendState", "Unknown"),
        "dns_name": dns_name,
        "tailscale_ips": ips,
        "online": is_online,
        "funnel_urls": funnel_urls,
        "funnel": funnel_info,
        "serve": serve_info,
        "https_cert_ok": https_cert_ok,
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

    # Pass Auth key securely via a temporary restricted file to prevent process list leakage (ps aux)
    key_fd, key_file_path = tempfile.mkstemp(prefix=".ts_key_", dir="/tmp")
    try:
        with os.fdopen(key_fd, "w", encoding="utf-8") as f:
            f.write(key.strip())
        os.chmod(key_file_path, 0o600)

        cmd = [
            "tailscale", "up",
            f"--authkey=file:{key_file_path}",
            f"--hostname={cfg.get('hostname') or 'llmwiking'}",
            "--accept-dns=true",
        ]
        extra = (cfg.get("extra_args") or "").strip()
        if extra:
            try:
                cmd.extend(shlex.split(extra))
            except Exception as e:
                log.warning("shlex parsing error in extra_args, falling back to split(): %s", e)
                cmd.extend(extra.split())

        code, out, err = await _run(cmd, timeout=120.0)
        return {"ok": code == 0, "stdout": out, "stderr": err, "code": code}
    finally:
        try:
            if os.path.exists(key_file_path):
                os.remove(key_file_path)
        except Exception:
            pass


async def down() -> dict[str, Any]:
    """Runs `tailscale down` to disconnect from Tailnet."""
    if not _which_tailscale():
        return {"ok": False, "error": "tailscale binary not found"}

    code, out, err = await _run(["tailscale", "down"])
    return {"ok": code == 0, "stdout": out, "stderr": err}


async def fetch_cert(cert_dir: Path | str | None = None) -> dict[str, Any]:
    """Runs `tailscale cert <dns_name>` to provision Let's Encrypt TLS certificate files."""
    if not _which_tailscale():
        return {"ok": False, "error": "tailscale binary not found"}

    st = await get_status()
    dns_name = st.get("dns_name")
    if not dns_name:
        return {"ok": False, "error": "Tailscale DNS-Name nicht gefunden. Stelle sicher, dass Tailscale online ist (tailscale up)."}

    cmd = ["tailscale", "cert"]
    if cert_dir:
        out_path = Path(cert_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        cmd.extend(["--cert-file", str(out_path / f"{dns_name}.crt"), "--key-file", str(out_path / f"{dns_name}.key")])
    cmd.append(dns_name)

    code, out, err = await _run(cmd, timeout=120.0)
    return {
        "ok": code == 0,
        "dns_name": dns_name,
        "stdout": out,
        "stderr": err,
        "code": code,
    }


async def apply_serve_funnel(cfg: dict[str, Any]) -> dict[str, Any]:
    """Applies `tailscale serve` and `tailscale funnel` settings via CLI."""
    if not _which_tailscale():
        return {"ok": False, "error": "tailscale binary not found"}

    app_port = int(cfg.get("app_port") or DEFAULT_APP_PORT)
    fport = int(cfg.get("funnel_port") or 443)
    target = get_proxy_target(cfg)
    results = []

    # Optional: fetch/provision HTTPS cert if enabled
    if cfg.get("serve_enabled", True) or cfg.get("funnel_enabled"):
        cert_res = await fetch_cert()
        if cert_res.get("ok"):
            results.append({"step": "cert", "ok": True, "out": cert_res.get("stdout"), "err": ""})
        else:
            log.info("tailscale cert info: %s", cert_res.get("stderr") or cert_res.get("error"))

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
    status = await get_status(cfg)
    return {"ok": all(r.get("ok") for r in results if r.get("step") != "cert"), "steps": results, "status": status}


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


async def restart_tailscale() -> dict[str, Any]:
    """Restarts Tailscale daemon/connection independently from the main server using targeted PID signal management."""
    if not _which_tailscale():
        return {"ok": False, "error": "tailscale binary not found"}

    cfg = load_config()

    # 1. Targeted daemon shutdown using PID file or specific process matching
    pid_killed = False
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            if pid > 1:
                os.kill(pid, 15)  # SIGTERM
                pid_killed = True
        except Exception as e:
            log.warning("Could not terminate tailscaled PID from file: %s", e)

    if not pid_killed:
        # Targeted process check for container tailscaled daemon
        code, pids, _ = await _run(["pgrep", "-x", "tailscaled"])
        if code == 0 and pids.strip():
            for p_str in pids.strip().split():
                try:
                    p_val = int(p_str)
                    if p_val > 1:
                        os.kill(p_val, 15)  # SIGTERM
                except Exception:
                    pass

    await asyncio.sleep(1.5)

    # 2. Relaunch tailscaled daemon using persistent host state directory
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / "tailscaled.state"

    if Path("/dev/net/tun").exists():
        cmd = ["tailscaled", f"--state={state_file}", f"--statedir={STATE_DIR}"]
    else:
        cmd = ["tailscaled", "--tun=userspace-networking", f"--state={state_file}", f"--statedir={STATE_DIR}"]

    try:
        proc = await asyncio.create_subprocess_exec(*cmd)
        if proc and proc.pid:
            try:
                PID_FILE.write_text(str(proc.pid), encoding="utf-8")
            except Exception:
                pass
    except Exception as e:
        log.warning("Could not launch tailscaled daemon: %s", e)

    await asyncio.sleep(2.0)

    # 3. Re-apply connection and serve/funnel settings if enabled
    if cfg.get("enabled"):
        if cfg.get("auth_key_encrypted"):
            await up(cfg)
        await apply_serve_funnel(cfg)

    status = await get_status(cfg)
    return {"ok": True, "message": "Tailscale neugestartet", "status": status}


async def auto_restore_on_startup() -> None:
    """Restores Tailscale connection and serve/funnel proxy settings on app startup."""
    cfg = load_config()
    if not cfg.get("enabled"):
        return
    try:
        st = await get_status()
        if st.get("backend_state") not in ("Running", "Starting"):
            await up(cfg)
        await apply_serve_funnel(cfg)
    except Exception as e:
        log.warning("Tailscale auto-restore failed: %s", e)


async def setup_all(
    *,
    hostname: str,
    auth_key: str | None,
    app_port: int,
    proxy_target: str | None = None,
    funnel_port: int,
    funnel_enabled: bool,
    serve_enabled: bool,
    extra_args: str,
    actor: str,
) -> dict[str, Any]:
    """One-Click setup: Save config -> tailscale up -> apply serve/funnel -> get status."""
    cfg = load_config()
    cfg["hostname"] = (hostname or "llmwiking").strip()
    cfg["app_port"] = int(app_port)
    if proxy_target is not None:
        cfg["proxy_target"] = proxy_target.strip()
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

/**
 * LLMWikiNG – Tailscale & Funnel Integration Frontend Logic
 */

(function () {
    "use strict";

    var currentDnsName = "";
    var currentFunnelUrl = "";
    var decryptedAuthKey = "";

    function getBasePath() {
        return window.BASE_PATH || "/LLMWikiNG";
    }

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
        if (window.CSRF_TOKEN) return window.CSRF_TOKEN;
        return "";
    }

    function showMsg(msg, isError) {
        var box = document.getElementById("ts-msg-box");
        if (!box) return;
        box.innerText = msg;
        box.className = "p-3 rounded-lg text-xs " + (isError ? "bg-error/10 text-error border border-error/20" : "bg-success/10 text-success border border-success/20");
        box.classList.remove("hidden");
    }

    function clearMsg() {
        var box = document.getElementById("ts-msg-box");
        if (box) box.classList.add("hidden");
    }

    function renderStatusBadge(status) {
        var badge = document.getElementById("ts-status-badge");
        if (!badge) return;

        var state = status.backend_state || "Unknown";
        var isOnline = status.online || false;
        var hasFunnel = status.funnel_urls && status.funnel_urls.length > 0;

        var badgeText = state;
        var badgeClass = "inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border ";

        if (state === "Running" && isOnline) {
            if (hasFunnel) {
                badgeClass += "bg-primary/10 text-primary border-primary/30";
                badgeText = "🌐 Online (Funnel aktiv)";
            } else {
                badgeClass += "bg-success/10 text-success border-success/30";
                badgeText = "🟢 Online (Tailnet)";
            }
        } else if (state === "NeedsLogin") {
            badgeClass += "bg-warning/10 text-warning border-warning/30";
            badgeText = "🔑 Login erforderlich";
        } else if (state === "NotInstalled") {
            badgeClass += "bg-error/10 text-error border-error/30";
            badgeText = "⚠️ Tailscale nicht installiert";
        } else {
            badgeClass += "bg-bg-sunken text-text-secondary border-border";
            badgeText = "⚪ Off-line (" + state + ")";
        }

        badge.className = badgeClass;
        badge.innerHTML = "<span>" + badgeText + "</span>";
    }

    function updateStatusOverview(status) {
        renderStatusBadge(status);

        var stateEl = document.getElementById("ts-live-state");
        if (stateEl) stateEl.innerText = status.backend_state || "Unbekannt";

        var dnsEl = document.getElementById("ts-live-dns");
        var copyDnsBtn = document.getElementById("ts-copy-dns-btn");
        if (dnsEl) {
            currentDnsName = status.dns_name || "";
            dnsEl.innerText = currentDnsName || "--";
            if (copyDnsBtn) {
                if (currentDnsName) copyDnsBtn.classList.remove("hidden");
                else copyDnsBtn.classList.add("hidden");
            }
        }

        var ipsEl = document.getElementById("ts-live-ips");
        if (ipsEl) {
            var ips = status.tailscale_ips || [];
            ipsEl.innerText = ips.length ? ips.join(", ") : "--";
        }

        var certEl = document.getElementById("ts-live-cert");
        if (certEl) {
            certEl.innerText = status.https_cert_ok ? "✅ Aktiv (HTTPS OK)" : "❌ Inaktiv";
            certEl.className = status.https_cert_ok ? "font-semibold text-success" : "font-semibold text-text-secondary";
        }

        // Funnel URL display
        var funnelCard = document.getElementById("ts-funnel-url-card");
        var funnelLink = document.getElementById("ts-funnel-url-link");
        var urls = status.funnel_urls || [];
        if (funnelCard && funnelLink) {
            if (urls.length > 0) {
                currentFunnelUrl = urls[0];
                funnelLink.href = currentFunnelUrl;
                funnelLink.innerText = currentFunnelUrl;
                funnelCard.classList.remove("hidden");
            } else {
                currentFunnelUrl = "";
                funnelCard.classList.add("hidden");
            }
        }

        // Update Agent snippets
        var nodeName = status.dns_name || "<node>.<tailnet>.ts.net";
        var baseUrl = currentFunnelUrl || ("https://" + nodeName);
        var sseUrl = baseUrl.replace(/\/$/, "") + getBasePath() + "/mcp";
        var apiUrl = baseUrl.replace(/\/$/, "") + getBasePath() + "/api/v1/";

        var sseSpan = document.getElementById("ts-agent-mcp-sse-url");
        if (sseSpan) sseSpan.innerText = sseUrl;

        var apiSpan = document.getElementById("ts-agent-api-url");
        if (apiSpan) apiSpan.innerText = apiUrl;

        var jsonSpan = document.getElementById("ts-json-mcp-url");
        if (jsonSpan) jsonSpan.innerText = sseUrl;
    }

    function populateForm(config) {
        if (!config) return;
        var hostInput = document.getElementById("ts-hostname");
        if (hostInput && config.hostname) hostInput.value = config.hostname;

        var appPortInput = document.getElementById("ts-app-port");
        if (appPortInput && config.app_port) appPortInput.value = config.app_port;

        var funnelPortSelect = document.getElementById("ts-funnel-port");
        if (funnelPortSelect && config.funnel_port) funnelPortSelect.value = config.funnel_port;

        var serveCb = document.getElementById("ts-serve-enabled");
        if (serveCb) serveCb.checked = config.serve_enabled !== false;

        var funnelCb = document.getElementById("ts-funnel-enabled");
        if (funnelCb) funnelCb.checked = !!config.funnel_enabled;

        var extraInput = document.getElementById("ts-extra-args");
        if (extraInput) extraInput.value = config.extra_args || "";

        var hintText = document.getElementById("ts-auth-key-hint-text");
        var revealBtn = document.getElementById("ts-reveal-key-btn");
        if (config.has_auth_key) {
            if (hintText) hintText.innerText = "Gespeicherter Auth-Key: " + (config.auth_key_hint || "Verschlüsselt");
            if (revealBtn) revealBtn.classList.remove("hidden");
        } else {
            if (hintText) hintText.innerText = "Einmalig erstelle den Auth-Key im Tailscale Admin Console (tskey-auth-...).";
            if (revealBtn) revealBtn.classList.add("hidden");
        }
    }

    window.loadTailscaleData = function () {
        fetch(getBasePath() + "/api/v1/system/tailscale")
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.config) populateForm(data.config);
                if (data.status) updateStatusOverview(data.status);
            })
            .catch(function (err) {
                console.error("Tailscale config error:", err);
            });
    };

    window.refreshTailscaleStatus = function () {
        fetch(getBasePath() + "/api/v1/system/tailscale/status")
            .then(function (res) { return res.json(); })
            .then(function (status) {
                updateStatusOverview(status);
            })
            .catch(function (err) {
                console.error("Tailscale status refresh error:", err);
            });
    };

    window.handleTailscaleSetup = function (event) {
        if (event) event.preventDefault();
        clearMsg();

        var btn = document.getElementById("ts-setup-btn");
        var origText = btn ? btn.innerHTML : "";
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = "<span>⏳</span> Einrichten läuft...";
        }

        var payload = {
            hostname: document.getElementById("ts-hostname").value,
            auth_key: document.getElementById("ts-auth-key").value,
            app_port: parseInt(document.getElementById("ts-app-port").value, 10),
            funnel_port: parseInt(document.getElementById("ts-funnel-port").value, 10),
            serve_enabled: document.getElementById("ts-serve-enabled").checked,
            funnel_enabled: document.getElementById("ts-funnel-enabled").checked,
            extra_args: document.getElementById("ts-extra-args").value
        };

        fetch(getBasePath() + "/api/v1/system/tailscale/setup", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify(payload)
        })
            .then(function (res) {
                return res.json().then(function (data) {
                    if (!res.ok) throw new Error(data.detail || data.error || "Setup fehlgeschlagen");
                    return data;
                });
            })
            .then(function (res) {
                if (res.ok) {
                    showMsg("✅ Tailscale & Funnel wurden erfolgreich eingerichtet!", false);
                    document.getElementById("ts-auth-key").value = "";
                    window.loadTailscaleData();
                } else {
                    var err = res.error || (res.up && res.up.stderr) || "Setup teilweise fehlgeschlagen";
                    showMsg("⚠️ Setup-Fehler: " + err, true);
                }
            })
            .catch(function (err) {
                showMsg("❌ Fehler: " + err.message, true);
            })
            .finally(function () {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = origText;
                }
            });
    };

    function setBtnLoading(btn, isBusy, busyText) {
        if (!btn) return;
        if (isBusy) {
            btn.dataset.origText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = "<span>⏳</span> " + busyText;
        } else {
            btn.disabled = false;
            if (btn.dataset.origText) btn.innerHTML = btn.dataset.origText;
        }
    }

    window.handleTailscaleSaveOnly = function () {
        clearMsg();
        var btn = document.getElementById("ts-save-btn");
        setBtnLoading(btn, true, "Speichert...");

        var payload = {
            hostname: document.getElementById("ts-hostname").value,
            auth_key: document.getElementById("ts-auth-key").value,
            app_port: parseInt(document.getElementById("ts-app-port").value, 10),
            funnel_port: parseInt(document.getElementById("ts-funnel-port").value, 10),
            serve_enabled: document.getElementById("ts-serve-enabled").checked,
            funnel_enabled: document.getElementById("ts-funnel-enabled").checked,
            extra_args: document.getElementById("ts-extra-args").value
        };

        fetch(getBasePath() + "/api/v1/system/tailscale", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify(payload)
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.ok) {
                    showMsg("💾 Konfiguration gespeichert.", false);
                    document.getElementById("ts-auth-key").value = "";
                    window.loadTailscaleData();
                } else {
                    showMsg("❌ Fehler beim Speichern.", true);
                }
            })
            .catch(function (err) {
                showMsg("❌ Speicherfehler: " + err.message, true);
            })
            .finally(function () {
                setBtnLoading(btn, false);
            });
    };

    window.handleTailscaleDown = function () {
        if (!confirm("Möchtest du die Tailscale-Verbindung wirklich trennen (down)?")) return;
        clearMsg();
        var btn = document.getElementById("ts-stop-btn");
        setBtnLoading(btn, true, "Trennt...");

        fetch(getBasePath() + "/api/v1/system/tailscale/down", {
            method: "POST",
            headers: { "X-CSRF-Token": getCsrfToken() }
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.ok) {
                    showMsg("🛑 Tailscale Verbindung getrennt.", false);
                    window.refreshTailscaleStatus();
                } else {
                    showMsg("❌ Fehler beim Trennen: " + (data.stderr || data.error), true);
                }
            })
            .catch(function (err) {
                showMsg("❌ Fehler: " + err.message, true);
            })
            .finally(function () {
                setBtnLoading(btn, false);
            });
    };

    window.handleTailscaleReset = function () {
        if (!confirm("Möchtest du Tailscale Serve & Funnel zurücksetzen?")) return;
        clearMsg();
        var btn = document.getElementById("ts-reset-btn");
        setBtnLoading(btn, true, "Zurücksetzen...");

        fetch(getBasePath() + "/api/v1/system/tailscale/reset", {
            method: "POST",
            headers: { "X-CSRF-Token": getCsrfToken() }
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.ok) {
                    showMsg("↩️ Tailscale Funnel & Serve zurückgesetzt.", false);
                    window.refreshTailscaleStatus();
                } else {
                    showMsg("❌ Fehler beim Zurücksetzen.", true);
                }
            })
            .catch(function (err) {
                showMsg("❌ Fehler: " + err.message, true);
            })
            .finally(function () {
                setBtnLoading(btn, false);
            });
    };

    window.handleTailscaleCert = function () {
        clearMsg();
        showMsg("⏳ SSL/TLS-Zertifikat wird von Tailscale / Let's Encrypt abgerufen...", false);
        var btn = document.getElementById("ts-cert-btn") || document.getElementById("ts-live-cert-btn");
        setBtnLoading(btn, true, "Abrufen...");

        fetch(getBasePath() + "/api/v1/system/tailscale/cert", {
            method: "POST",
            headers: { "X-CSRF-Token": getCsrfToken() }
        })
            .then(function (res) {
                return res.json().then(function (data) {
                    if (!res.ok) throw new Error(data.detail || data.error || "Zertifikatsabruf fehlgeschlagen");
                    return data;
                });
            })
            .then(function (data) {
                if (data.ok) {
                    showMsg("✅ SSL/TLS-Zertifikat für " + (data.dns_name || "Tailscale") + " erfolgreich abgerufen!", false);
                    window.refreshTailscaleStatus();
                } else {
                    showMsg("⚠️ Zertifikatsfehler: " + (data.stderr || data.error || "Zertifikat konnte nicht erstellt werden"), true);
                }
            })
            .catch(function (err) {
                showMsg("❌ Fehler: " + err.message, true);
            })
            .finally(function () {
                setBtnLoading(btn, false);
            });
    };

    window.handleTailscaleRestart = function () {
        if (!confirm("Möchtest du den Tailscale Daemon wirklich neustarten? (Der Webserver bleibt online)")) return;
        clearMsg();
        showMsg("⏳ Tailscale Daemon wird neugestartet...", false);
        var btn = document.getElementById("ts-restart-btn");
        setBtnLoading(btn, true, "Neustart...");

        fetch(getBasePath() + "/api/v1/system/tailscale/restart", {
            method: "POST",
            headers: { "X-CSRF-Token": getCsrfToken() }
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.ok) {
                    showMsg("🔄 Tailscale Daemon erfolgreich neugestartet.", false);
                    if (data.status) updateStatusOverview(data.status);
                    else window.refreshTailscaleStatus();
                } else {
                    showMsg("❌ Fehler beim Neustarten: " + (data.error || "Unbekannter Fehler"), true);
                }
            })
            .catch(function (err) {
                showMsg("❌ Neustart-Fehler: " + err.message, true);
            })
            .finally(function () {
                setBtnLoading(btn, false);
            });
    };

    window.copyTsDns = function () {
        if (!currentDnsName) return;
        navigator.clipboard.writeText(currentDnsName).then(function () {
            var btn = document.getElementById("ts-copy-dns-btn");
            if (btn) {
                var orig = btn.innerText;
                btn.innerText = "✓ Kopiert!";
                setTimeout(function () { btn.innerText = orig; }, 2000);
            }
        });
    };

    window.copyTsFunnelUrl = function () {
        if (!currentFunnelUrl) return;
        navigator.clipboard.writeText(currentFunnelUrl).then(function () {
            alert("Funnel URL kopiert: " + currentFunnelUrl);
        });
    };

    /* Modal for revealing Auth key */
    window.openTsRevealModal = function () {
        document.getElementById("tsRevealPassword").value = "";
        document.getElementById("tsRevealError").classList.add("hidden");
        document.getElementById("tsRevealKeyContainer").classList.add("hidden");
        document.getElementById("tsRevealKeyContainer").innerText = "";
        document.getElementById("tsRevealSubmitBtn").classList.remove("hidden");
        document.getElementById("tsRevealCopyBtn").classList.add("hidden");
        document.getElementById("tsRevealModal").classList.remove("hidden");
        document.getElementById("tsRevealPassword").focus();
        decryptedAuthKey = "";
    };

    window.closeTsRevealModal = function () {
        document.getElementById("tsRevealModal").classList.add("hidden");
    };

    window.submitTsRevealKey = function (event) {
        event.preventDefault();
        var pw = document.getElementById("tsRevealPassword").value;
        var errorEl = document.getElementById("tsRevealError");
        var container = document.getElementById("tsRevealKeyContainer");
        var submitBtn = document.getElementById("tsRevealSubmitBtn");
        var copyBtn = document.getElementById("tsRevealCopyBtn");

        errorEl.classList.add("hidden");

        fetch(getBasePath() + "/api/v1/system/tailscale/reveal", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({ password: pw })
        })
            .then(function (res) {
                return res.json().then(function (data) {
                    if (!res.ok) throw new Error(data.detail || data.error || "Verifizierung fehlgeschlagen");
                    return data;
                });
            })
            .then(function (data) {
                decryptedAuthKey = data.raw_key;
                container.innerText = decryptedAuthKey;
                container.classList.remove("hidden");
                submitBtn.classList.add("hidden");
                copyBtn.classList.remove("hidden");

                copyBtn.onclick = function () {
                    navigator.clipboard.writeText(decryptedAuthKey).then(function () {
                        copyBtn.innerText = "✓ Kopiert!";
                        setTimeout(function () { copyBtn.innerText = "Kopieren"; }, 2000);
                    });
                };
            })
            .catch(function (err) {
                errorEl.innerText = err.message;
                errorEl.classList.remove("hidden");
            });
    };

    document.addEventListener("DOMContentLoaded", function () {
        // Load data if current active tab is tailscale or on explicit call
        window.loadTailscaleData();
    });
})();

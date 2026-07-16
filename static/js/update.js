// update.js – "Check for update" helper shared by update.html and settings.html
(function () {
  "use strict";

  function checkUpdate() {
    var BASE = window.BASE_PATH || "";
    var btn = document.getElementById("checkUpdateBtn");
    var result = document.getElementById("checkResult");
    if (!btn || !result) return;

    var cfg = result.dataset;
    btn.disabled = true;
    btn.textContent = btn.dataset.checking || "…";
    result.classList.remove("hidden");
    result.innerHTML = '<p class="text-text-muted text-sm">' + (cfg.checkingText || "") + "</p>";

    var tokenInput = document.getElementById("github_token_input");
    var token = tokenInput ? tokenInput.value.trim() : "";
    var checkUrl = BASE + "/admin/update/check";
    if (token) {
      checkUrl += "?github_token=" + encodeURIComponent(token);
    }

    fetch(checkUrl)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) {
          result.innerHTML = '<div class="rounded-lg border border-warning/40 bg-warning-subtle p-3 text-sm"><strong>' + (cfg.errorPrefix || "") + "</strong> " + data.error + "</div>";
          return;
        }
        if (data.up_to_date) {
          result.innerHTML =
            '<div class="rounded-lg border border-success/40 bg-success-subtle p-4 text-sm">' +
            '<strong class="text-success">' + (cfg.upToDate || "") + "</strong><br>" +
            '<span class="text-text-secondary">' + (cfg.localLabel || "") + " <strong>" + data.local_version + "</strong> – " + (cfg.githubLabel || "") + " <strong>" + data.github_version + "</strong></span></div>";
        } else {
          result.innerHTML =
            '<div class="rounded-lg border border-warning/40 bg-warning-subtle p-4 text-sm">' +
            '<strong class="text-warning">' + (cfg.updateAvailable || "") + "</strong><br>" +
            '<span class="text-text-secondary">' + (cfg.localLabel || "") + " <strong>" + data.local_version + "</strong> → " + (cfg.githubLabel || "") + " <strong>" + data.github_version + "</strong></span>" +
            '<br><br><a href="' + BASE + '/settings?tab=update" class="rounded-lg bg-success px-3 py-1.5 text-white no-underline">' + (cfg.runButton || "") + "</a></div>";
        }
      })
      .catch(function (err) {
        result.innerHTML = '<div class="rounded-lg border border-warning/40 bg-warning-subtle p-3 text-sm"><strong>' + (cfg.errorPrefix || "") + "</strong> " + err.message + "</div>";
      })
      .finally(function () {
        btn.disabled = false;
        btn.textContent = btn.dataset.label || (cfg.checkButton || "");
      });
  }

  window.checkUpdate = checkUpdate;
})();

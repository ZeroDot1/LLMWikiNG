// presets.js – SMTP preset helper shared by config.html and settings.html
(function () {
  "use strict";

  window.applyPreset = function (host, port, useTls, placeholder) {
    var h = document.getElementById("smtp_host");
    var p = document.getElementById("smtp_port");
    var t = document.getElementById("use_tls");
    var u = document.getElementById("smtp_user");
    if (h) h.value = host;
    if (p) p.value = port;
    if (t) t.checked = useTls;
    if (u) u.placeholder = (u.dataset.phPrefix ? u.dataset.phPrefix + " " : "") + placeholder;
  };
})();

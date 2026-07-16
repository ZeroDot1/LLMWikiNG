// page.js – copy current page link to clipboard
(function () {
  "use strict";

  window.copyPageLink = function (btn) {
    var url = window.location.href;
    function done() {
      var orig = btn.innerHTML;
      btn.innerHTML = btn.dataset.copied || "Kopiert!";
      btn.classList.add("bg-success", "text-white");
      setTimeout(function () {
        btn.innerHTML = orig;
        btn.classList.remove("bg-success", "text-white");
      }, 2500);
    }
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = url;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        done();
      } catch (e) {
        btn.innerHTML = btn.dataset.error || "Fehler";
      }
      document.body.removeChild(ta);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done).catch(fallback);
    } else {
      fallback();
    }
  };
})();

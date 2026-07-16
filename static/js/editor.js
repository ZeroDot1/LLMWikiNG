// editor.js – live markdown preview + form sync, save via /edit/save
(function () {
  "use strict";

  const BASE_PATH = window.BASE_PATH || "";
  let currentMode = "wysiwyg";
  let previewTimer = null;

  function getCsrfFallback() {
    return null;
  }

  function postPreview(content, callback) {
    fetch(BASE_PATH + "/edit/preview", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "content=" + encodeURIComponent(content),
    })
      .then(function (r) { return r.text(); })
      .then(callback)
      .catch(function () {});
  }

  function htmlToMarkdown(html) {
    let md = html;
    md = md.replace(/<blockquote[^>]*>([\s\S]*?)<\/blockquote>/gi, function (m, c) {
      return "\n" + c.trim().split(/<br\s*\/?>|\n/gi).map(function (l) { return "> " + l.replace(/<[^>]+>/g, "").trim(); }).join("\n") + "\n\n";
    });
    md = md.replace(/<h1[^>]*>(.*?)<\/h1>/gi, "# $1\n\n");
    md = md.replace(/<h2[^>]*>(.*?)<\/h2>/gi, "## $1\n\n");
    md = md.replace(/<h3[^>]*>(.*?)<\/h3>/gi, "### $1\n\n");
    md = md.replace(/<strong[^>]*>(.*?)<\/strong>/gi, "**$1**");
    md = md.replace(/<b[^>]*>(.*?)<\/b>/gi, "**$1**");
    md = md.replace(/<em[^>]*>(.*?)<\/em>/gi, "*$1*");
    md = md.replace(/<i[^>]*>(.*?)<\/i>/gi, "*$1*");
    md = md.replace(/<(strike|s|del)[^>]*>(.*?)<\/\1>/gi, "~~$2~~");
    md = md.replace(/<code[^>]*>(.*?)<\/code>/gi, "`$1`");
    md = md.replace(/<a[^>]+href="([^"]+)"[^>]*>(.*?)<\/a>/gi, "[$2]($1)");
    md = md.replace(/<img[^>]+src="([^"]+)"[^>]*alt="([^"]*)"[^>]*>/gi, "![$2]($1)");
    md = md.replace(/<img[^>]+src="([^"]+)"[^>]*>/gi, "![]($1)");
    md = md.replace(/<hr[^>]*>/gi, "\n---\n\n");
    md = md.replace(/<li[^>]*>(.*?)<\/li>/gi, "* $1\n");
    md = md.replace(/<ul[^>]*>/gi, "");
    md = md.replace(/<\/ul>/gi, "\n");
    md = md.replace(/<ol[^>]*>/gi, "");
    md = md.replace(/<\/ol>/gi, "\n");
    md = md.replace(/<p[^>]*>(.*?)<\/p>/gi, "$1\n\n");
    md = md.replace(/<br\s*\/?>/gi, "\n");
    md = md.replace(/<[^>]+>/g, "");
    const txt = document.createElement("textarea");
    txt.innerHTML = md;
    return txt.value.trim();
  }

  function execCmd(command, arg) {
    document.execCommand(command, false, arg);
    const el = document.getElementById("editor-wysiwyg");
    if (el) el.focus();
  }

  function wrapFrontmatter(body) {
    const today = new Date().toISOString().split("T")[0];
    return "---\ntype: Concept\ntitle: \"Neue Seite\"\ndescription: \"Beschreibung\"\nresource: \"\"\ntags: []\ntimestamp: " + today + "T00:00:00Z\n---\n\n" + body;
  }

  function switchTab(mode) {
    if (mode === currentMode) return;
    const tabW = document.getElementById("tab-wysiwyg");
    const tabM = document.getElementById("tab-markdown");
    const wrapW = document.getElementById("wysiwyg-editor-wrapper");
    const wrapM = document.getElementById("markdown-editor-wrapper");
    const toolbar = document.getElementById("editor-toolbar");
    const edW = document.getElementById("editor-wysiwyg");
    const edM = document.getElementById("editor-markdown");

    if (mode === "markdown") {
      const mdContent = htmlToMarkdown(edW.innerHTML);
      if (!edM.value.trim() && mdContent) {
        edM.value = wrapFrontmatter(mdContent);
      } else if (mdContent) {
        const fm = edM.value.match(/^---.*?---\s*/s);
        edM.value = (fm ? fm[0] : "") + mdContent;
      }
      wrapW.style.display = "none";
      if (toolbar) toolbar.style.display = "none";
      wrapM.style.display = "block";
      tabW.classList.remove("active");
      tabM.classList.add("active");
      currentMode = "markdown";
    } else {
      const content = edM.value;
      wrapM.style.display = "none";
      wrapW.style.display = "block";
      if (toolbar) toolbar.style.display = "flex";
      postPreview(content, function (html) { edW.innerHTML = html; });
      tabM.classList.remove("active");
      tabW.classList.add("active");
      currentMode = "wysiwyg";
    }
  }

  function initEditor() {
    const form = document.getElementById("editor-form");
    if (!form) return;

    const edW = document.getElementById("editor-wysiwyg");
    const edM = document.getElementById("editor-markdown");

    // Live preview while typing markdown
    if (edM) {
      edM.addEventListener("input", function () {
        clearTimeout(previewTimer);
        const val = edM.value;
        previewTimer = setTimeout(function () {
          if (currentMode === "markdown") {
            const prev = document.getElementById("preview");
            postPreview(val, function (html) { if (prev) prev.innerHTML = html; });
          }
        }, 400);
      });
    }

    // Submit: sync WYSIWYG -> markdown
    form.addEventListener("submit", function () {
      if (currentMode === "wysiwyg") {
        const mdContent = htmlToMarkdown(edW.innerHTML);
        const fm = edM.value.match(/^---.*?---\s*/s);
        edM.value = (fm ? fm[0] : wrapFrontmatter("")) + mdContent;
      }
    });

    // Initial render of existing content into WYSIWYG
    if (edM && edM.value.trim()) {
      postPreview(edM.value, function (html) { edW.innerHTML = html; });
    }

    window.switchTab = switchTab;
    window.execCmd = execCmd;
    window.insertLink = function () {
      const url = prompt("URL eingeben:");
      if (url) execCmd("createLink", url);
    };
    window.insertImage = function () {
      const url = prompt("Bild-URL eingeben:");
      if (url) execCmd("insertImage", url);
    };
    window.insertInlineCode = function () {
      const sel = window.getSelection();
      const code = document.createElement("code");
      if (!sel.isCollapsed) { code.textContent = sel.toString(); sel.getRangeAt(0).deleteContents(); sel.getRangeAt(0).insertNode(code); }
      else { code.textContent = "code"; sel.getRangeAt(0).insertNode(code); }
      edW.focus();
    };
  }

  document.addEventListener("DOMContentLoaded", initEditor);
})();

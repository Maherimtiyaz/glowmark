// glowmark web editor -------------------------------------------------

(function () {
  "use strict";

  var SEED = <!--GLOWMARK:SEED-->;
  var DEFAULT_MD =
    "# Hello, glowmark\n\n" +
    "Paste **any markdown** on the left — the preview updates as you type.\n\n" +
    "## Why glowmark?\n\n" +
    "| Feature | CLI | Web |\n" +
    "| ------- | --- | --- |\n" +
    "| Live preview | ✅ | ✅ |\n" +
    "| Standalone HTML | ✅ | ✅ |\n\n" +
    "```python\nprint(\"one command, beautiful pages\")\n```\n\n" +
    "> [!TIP]\n> Try editing this text, or paste your own README.";

  var editor = document.getElementById("editor");
  var preview = document.getElementById("preview");
  var stats = document.getElementById("stats");
  var headTitle = document.getElementById("headTitle");
  var timer = null;
  var pending = false;
  var lastHtml = "";

  editor.value = SEED !== null && SEED !== undefined ? SEED : DEFAULT_MD;

  function renderNow(full, cb) {
    var payload = JSON.stringify({ md: editor.value, full: !!full });
    fetch("/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
    })
      .then(function (r) {
        if (!r.ok) throw new Error("render failed");
        return r.json();
      })
      .then(cb)
      .catch(function (e) {
        stats.textContent = "error: " + e.message;
      });
  }

  function schedule() {
    if (timer) clearTimeout(timer);
    stats.textContent = "typing…";
    timer = setTimeout(function () {
      pending = true;
      renderNow(false, function (data) {
        pending = false;
        if (data.error) {
          stats.textContent = "error: " + data.error;
          return;
        }
        preview.innerHTML = data.body || '<p class="preview-empty">Nothing to preview yet — start typing!</p>';
        lastHtml = data.body;
        headTitle.textContent = data.title || "";
        stats.textContent =
          data.words.toLocaleString() + " words · " + data.minutes + " min read";
      });
    }, 200);
  }

  editor.addEventListener("input", schedule);
  editor.addEventListener("keydown", function (e) {
    if (e.key === "Tab") {
      e.preventDefault();
      var s = editor.selectionStart;
      var en = editor.selectionEnd;
      editor.value = editor.value.slice(0, s) + "  " + editor.value.slice(en);
      editor.selectionStart = editor.selectionEnd = s + 2;
      schedule();
    }
  });

  // initial render
  renderNow(false, function (data) {
    if (data.error) {
      stats.textContent = "error: " + data.error;
      return;
    }
    preview.innerHTML = data.body || '<p class="preview-empty">Nothing to preview yet — start typing!</p>';
    lastHtml = data.body;
    headTitle.textContent = data.title || "";
    stats.textContent = data.words.toLocaleString() + " words · " + data.minutes + " min read";
  });

  // copy / download the standalone page ---------------------------------
  function flash(btn, text) {
    var old = btn.textContent;
    btn.textContent = text;
    btn.classList.add("done");
    setTimeout(function () {
      btn.textContent = old;
      btn.classList.remove("done");
    }, 1600);
  }

  function withFullPage(cb) {
    stats.textContent = "building standalone page…";
    renderNow(true, function (data) {
      if (data.error) {
        stats.textContent = "error: " + data.error;
        return;
      }
      cb(data.html);
    });
  }

  document.getElementById("copyHtml").addEventListener("click", function () {
    var btn = this;
    withFullPage(function (html) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(html).then(
          function () {
            flash(btn, "copied!");
            stats.textContent = "full HTML copied to clipboard";
          },
          function () {
            flash(btn, "failed");
          }
        );
      }
    });
  });

  document.getElementById("downloadHtml").addEventListener("click", function () {
    var btn = this;
    withFullPage(function (html) {
      var blob = new Blob([html], { type: "text/html" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = (headTitle.textContent || "glowmark").replace(/[^\w-]+/g, "-").toLowerCase() + ".html";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () {
        URL.revokeObjectURL(a.href);
      }, 1000);
      flash(btn, "saved!");
      stats.textContent = "standalone page downloaded — works offline";
    });
  });

  // theme toggle ----------------------------------------------------------
  var themeBtn = document.getElementById("webTheme");
  themeBtn.addEventListener("click", function () {
    var root = document.documentElement;
    var next = root.className.replace("theme-", "") === "light" ? "dark" : "light";
    root.className = "theme-" + next;
    themeBtn.textContent = next === "dark" ? "🌙" : "☀️";
    try {
      localStorage.setItem("glowmark-theme", next);
    } catch (e) {}
  });
  // reflect stored preference on the button
  (function () {
    var cur = document.documentElement.className.replace("theme-", "");
    themeBtn.textContent = cur === "dark" ? "🌙" : "☀️";
  })();

  // mobile tabs ------------------------------------------------------------
  var editPane = document.getElementById("editPane");
  var viewPane = document.getElementById("viewPane");
  var tabEdit = document.getElementById("tabEdit");
  var tabView = document.getElementById("tabView");
  function showTab(which) {
    editPane.classList.toggle("active", which === "edit");
    viewPane.classList.toggle("active", which === "view");
  }
  tabEdit.addEventListener("click", function () {
    showTab("edit");
  });
  tabView.addEventListener("click", function () {
    showTab("view");
  });
})();

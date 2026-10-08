// glowmark page behavior ---------------------------------------------

(function () {
  "use strict";

  var root = document.documentElement;
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // theme toggle -----------------------------------------------------
  var themeBtn = document.getElementById("themeToggle");
  function applyTheme(next) {
    root.className = "theme-" + next;
    try {
      localStorage.setItem("glowmark-theme", next);
    } catch (e) {}
  }
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var current = root.className.replace("theme-", "");
      var next = current === "light" ? "dark" : "light";

      if (!reduced && document.startViewTransition) {
        var rect = themeBtn.getBoundingClientRect();
        root.style.setProperty("--vt-x", rect.left + rect.width / 2 + "px");
        root.style.setProperty("--vt-y", rect.top + rect.height / 2 + "px");
        var done = function () {
          root.style.removeProperty("--vt-x");
          root.style.removeProperty("--vt-y");
          highlightMermaid();
        };
        try {
          document.startViewTransition(function () {
            applyTheme(next);
          }).finished.then(done, done);
          return;
        } catch (e) {}
      }
      // fallback: quick crossfade
      root.classList.add("theme-anim");
      applyTheme(next);
      setTimeout(function () {
        root.classList.remove("theme-anim");
        highlightMermaid();
      }, 350);
    });
  }

  // TOC: open/close (mobile) + backdrop --------------------------------
  var toc = document.getElementById("toc");
  var tocBtn = document.getElementById("tocToggle");
  var backdrop = document.getElementById("tocBackdrop");
  function setToc(open) {
    if (!toc) return;
    toc.classList.toggle("open", open);
    if (backdrop) backdrop.classList.toggle("on", open);
  }
  if (tocBtn && toc) {
    tocBtn.addEventListener("click", function () {
      setToc(!toc.classList.contains("open"));
    });
    if (backdrop) backdrop.addEventListener("click", function () {
      setToc(false);
    });
    document.addEventListener("click", function (e) {
      if (toc.classList.contains("open") && !toc.contains(e.target) && e.target !== tocBtn) {
        setToc(false);
      }
    });
    toc.addEventListener("click", function (e) {
      if (e.target.tagName === "A") setToc(false);
    });
  }

  // TOC: sliding indicator + scroll spy ---------------------------------
  var indicator = null;
  var links = Array.prototype.slice.call(document.querySelectorAll(".toc nav a[href^='#']"));
  var activeLink = null;

  function moveIndicator(link) {
    if (!indicator) return;
    if (!link) {
      indicator.classList.remove("on");
      return;
    }
    indicator.style.top = link.offsetTop + 1 + "px";
    indicator.style.left = link.offsetLeft + "px";
    indicator.style.width = link.offsetWidth + "px";
    indicator.style.height = link.offsetHeight + "px";
    indicator.classList.add("on");
  }

  var tocNav = document.querySelector(".toc nav");
  if (tocNav && links.length) {
    indicator = document.createElement("div");
    indicator.className = "toc-indicator";
    indicator.setAttribute("aria-hidden", "true");
    tocNav.insertBefore(indicator, tocNav.firstChild);
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        moveIndicator(links[0]);
      });
    });
  }

  if (links.length && "IntersectionObserver" in window) {
    var byId = {};
    var targets = [];
    links.forEach(function (link) {
      var id = decodeURIComponent(link.getAttribute("href").slice(1));
      var el = document.getElementById(id);
      if (el) {
        byId[id] = link;
        targets.push(el);
      }
    });

    var visible = new Set();
    var spy = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) visible.add(entry.target.id);
          else visible.delete(entry.target.id);
        });
        var active = null;
        for (var i = 0; i < targets.length; i++) {
          if (visible.has(targets[i].id)) {
            active = targets[i].id;
            break;
          }
        }
        links.forEach(function (l) {
          l.classList.remove("toc-active");
        });
        var link = active ? byId[active] : null;
        if (link) {
          link.classList.add("toc-active");
          if (link !== activeLink) {
            activeLink = link;
            moveIndicator(link);
          }
        }
      },
      { rootMargin: "-10% 0px -70% 0px", threshold: 0 }
    );
    targets.forEach(function (t) {
      spy.observe(t);
    });

    window.addEventListener("resize", function () {
      moveIndicator(activeLink);
    });
  }

  // scroll reveals ------------------------------------------------------
  if ("IntersectionObserver" in window && !reduced) {
    var revealSel = [
      ".content h2",
      ".content h3",
      ".content pre",
      ".content .highlight",
      ".content table",
      ".content blockquote",
      ".content .admonition",
      ".content img",
      ".content .mermaid",
      ".content hr",
      ".content .footnotes",
      ".footer",
    ].join(",");
    var revealEls = Array.prototype.slice.call(document.querySelectorAll(revealSel));
    if (revealEls.length) {
      var revealObserver = new IntersectionObserver(
        function (entries) {
          var shown = 0;
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            var delay = Math.min(shown * 60, 240);
            entry.target.style.setProperty("--reveal-delay", delay + "ms");
            entry.target.classList.add("in");
            revealObserver.unobserve(entry.target);
            shown++;
          });
        },
        { rootMargin: "0px 0px -8% 0px", threshold: 0.05 }
      );
      revealEls.forEach(function (el) {
        el.classList.add("reveal");
        revealObserver.observe(el);
      });
    }
  }

  // progress bar + hero fade + back-to-top -------------------------------
  var progress = document.getElementById("progress");
  var progressBar = document.getElementById("progressBar");
  var hero = document.querySelector(".hero");
  var toTop = document.getElementById("toTop");
  var ticking = false;

  function onScroll() {
    var y = window.scrollY || document.documentElement.scrollTop;
    var max = document.documentElement.scrollHeight - window.innerHeight;
    var pct = max > 0 ? Math.min(100, (y / max) * 100) : 0;

    if (progress && progressBar) {
      progressBar.style.width = pct + "%";
      progress.classList.toggle("on", pct > 0.5);
    }
    if (hero && !reduced) {
      var h = hero.offsetHeight || 1;
      var fade = Math.max(0, 1 - y / (h * 1.1));
      hero.style.opacity = fade;
      hero.style.transform = y < h ? "translateY(" + -y * 0.08 + "px)" : "";
    }
    if (toTop) toTop.classList.toggle("on", y > 600);
    ticking = false;
  }
  window.addEventListener(
    "scroll",
    function () {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(onScroll);
      }
    },
    { passive: true }
  );
  onScroll();

  if (toTop) {
    toTop.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
    });
  }

  // copy buttons ----------------------------------------------------------
  function addCopyButtons() {
    var blocks = document.querySelectorAll(".content pre");
    Array.prototype.forEach.call(blocks, function (pre) {
      if (pre.querySelector(".copy-btn")) return;
      var btn = document.createElement("button");
      btn.className = "copy-btn";
      btn.type = "button";
      btn.textContent = "Copy";
      btn.addEventListener("click", function () {
        var code = pre.querySelector("code");
        var text = (code || pre).innerText;
        var done = function () {
          btn.textContent = "\u2713 Copied!";
          btn.classList.add("copied");
          setTimeout(function () {
            btn.textContent = "Copy";
            btn.classList.remove("copied");
          }, 1600);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, done);
        } else {
          var ta = document.createElement("textarea");
          ta.value = text;
          document.body.appendChild(ta);
          ta.select();
          try {
            document.execCommand("copy");
          } catch (e) {}
          document.body.removeChild(ta);
          done();
        }
      });
      pre.appendChild(btn);
    });
  }
  addCopyButtons();

  // mermaid diagrams ---------------------------------------------------
  function highlightMermaid() {
    if (typeof mermaid === "undefined") return;
    try {
      mermaid.run({ querySelector: ".mermaid" });
    } catch (e) {}
  }
  if (document.querySelector(".mermaid")) {
    var dark =
      root.className === "theme-dark" ||
      (root.className === "theme-auto" &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
    var s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js";
    s.onload = function () {
      mermaid.initialize({
        startOnLoad: false,
        theme: dark ? "dark" : "neutral",
      });
      highlightMermaid();
    };
    document.head.appendChild(s);
  }

  // math (KaTeX) --------------------------------------------------------
  if (document.querySelector(".content")) {
    var hasMath = /\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\$[^$\n]+\$/.test(
      document.getElementById("content").innerText
    );
    if (hasMath) {
      var katexCss = document.createElement("link");
      katexCss.rel = "stylesheet";
      katexCss.href = "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css";
      document.head.appendChild(katexCss);
      var katexJs = document.createElement("script");
      katexJs.src = "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js";
      katexJs.onload = function () {
        var auto = document.createElement("script");
        auto.src =
          "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js";
        auto.onload = function () {
          renderMathInElement(document.getElementById("content"), {
            delimiters: [
              { left: "$$", right: "$$", display: true },
              { left: "\\[", right: "\\]", display: true },
              { left: "$", right: "$", display: false },
            ],
          });
        };
        document.head.appendChild(auto);
      };
      document.head.appendChild(katexJs);
    }
  }
})();

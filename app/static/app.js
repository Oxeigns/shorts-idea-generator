/* ViralShorts Ideas — dashboard behaviour.
   Plain ES2019, no build step, no third-party code.
   Every server error message is shown verbatim; nothing is swallowed. */
(function () {
  "use strict";

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  /* ------------------------------------------------------------------ toasts */
  function toast(title, message, variant, duration) {
    var host = document.getElementById("toasts");
    if (!host) return;
    var el = document.createElement("div");
    el.className = "toast" + (variant ? " " + variant : "");
    el.setAttribute("role", variant === "error" ? "alert" : "status");
    var strong = document.createElement("strong");
    strong.textContent = title || "Notice";
    el.appendChild(strong);
    if (message) {
      var body = document.createElement("span");
      body.textContent = String(message);
      el.appendChild(body);
    }
    host.appendChild(el);

    var closed = false;
    var close = function () {
      if (closed) return;
      closed = true;
      el.classList.add("leaving");
      window.setTimeout(function () { el.remove(); }, 220);
    };
    el.addEventListener("click", close);
    window.setTimeout(close, duration || 6000);
    while (host.children.length > 4) host.firstElementChild.remove();
  }

  /* --------------------------------------------------------------- api calls */
  function detailOf(payload) {
    if (!payload) return "";
    var detail = payload.detail;
    if (Array.isArray(detail)) {
      return detail.map(function (item) {
        if (item && typeof item === "object") return item.msg || JSON.stringify(item);
        return String(item);
      }).join("; ");
    }
    if (detail && typeof detail === "object") return JSON.stringify(detail);
    if (detail) return String(detail);
    if (payload.reason) return String(payload.reason);
    return "";
  }

  function api(url, options) {
    options = options || {};
    var hasBody = options.body !== undefined && options.body !== null;
    return fetch(url, {
      method: options.method || "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: hasBody ? { "Content-Type": "application/json" } : {},
      body: hasBody ? JSON.stringify(options.body) : undefined
    }).then(function (res) {
      return res.text().then(function (text) {
        var payload = null;
        if (text) {
          try { payload = JSON.parse(text); } catch (err) { payload = null; }
        }
        if (!res.ok) {
          var message = detailOf(payload) || (payload && payload.error) ||
            ("HTTP " + res.status + (res.statusText ? " " + res.statusText : ""));
          var error = new Error(message);
          error.status = res.status;
          throw error;
        }
        return payload;
      });
    }, function () {
      throw new Error("Network request failed. Check the connection and try again.");
    });
  }

  /* ------------------------------------------------------------- India clock */
  function startClock() {
    var timeEls = $$("[data-clock-time]");
    var dateEls = $$("[data-clock-date]");
    if (!timeEls.length && !dateEls.length) return;

    var timeFmt, dateFmt;
    try {
      timeFmt = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false
      });
      dateFmt = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Kolkata", day: "2-digit", month: "2-digit", year: "numeric"
      });
    } catch (err) {
      timeFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
      dateFmt = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "2-digit", year: "numeric" });
    }

    var parts = function (fmt, date) {
      var out = {};
      fmt.formatToParts(date).forEach(function (part) { out[part.type] = part.value; });
      return out;
    };

    var tick = function () {
      var now = new Date();
      var t = parts(timeFmt, now);
      var hour = t.hour === "24" ? "00" : t.hour;
      var time = hour + ":" + t.minute + ":" + t.second;
      var d = parts(dateFmt, now);
      var date = d.day + "-" + d.month + "-" + d.year;

      timeEls.forEach(function (el) { if (el.textContent !== time) el.textContent = time; });
      dateEls.forEach(function (el) { if (el.textContent !== date) el.textContent = date; });
    };

    tick();
    window.setInterval(tick, 1000);
  }

  /* --------------------------------------------------------------- clipboard */
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.top = "0";
      area.style.left = "-9999px";
      document.body.appendChild(area);
      area.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
      area.remove();
      if (ok) resolve(); else reject(new Error("The browser blocked clipboard access."));
    });
  }

  /* --------------------------------------------------------------- generator */
  function initGenerator() {
    var panel = $("[data-active-run]");
    var genBtn = $("[data-generate]");
    if (!genBtn) return;

    var count = 10;
    var autoBox = $("[data-auto]");
    var catField = $("[data-cat-field]");
    var countGroup = $("[data-count-group]");

    if (countGroup) {
      $$("[data-count]", countGroup).forEach(function (btn) {
        btn.addEventListener("click", function () {
          $$("[data-count]", countGroup).forEach(function (other) {
            other.classList.toggle("active", other === btn);
            other.setAttribute("aria-pressed", other === btn ? "true" : "false");
          });
          var next = parseInt(btn.getAttribute("data-count"), 10);
          count = next === 20 || next === 50 ? next : 10;
        });
      });
    }

    var categories = function () {
      if (!catField) return [];
      return $$("input[type=checkbox]", catField).filter(function (box) { return box.checked; })
        .map(function (box) { return box.value; });
    };

    var syncCats = function () {
      if (!catField) return;
      var off = !!(autoBox && autoBox.checked);
      catField.classList.toggle("disabled", off);
      catField.setAttribute("aria-disabled", off ? "true" : "false");
      $$("input[type=checkbox]", catField).forEach(function (box) { box.disabled = off; });
    };

    if (autoBox) {
      autoBox.addEventListener("change", syncCats);
      syncCats();
    }

    var selectAllBtn = $("[data-select-all]");
    var refreshSelectAll = function () {
      if (!selectAllBtn || !catField) return;
      var boxes = $$("input[type=checkbox]", catField);
      var allOn = boxes.length > 0 && boxes.every(function (box) { return box.checked; });
      selectAllBtn.textContent = allOn ? "Clear all" : "Select all";
    };
    if (catField) {
      catField.addEventListener("change", refreshSelectAll);
      refreshSelectAll();
    }
    if (selectAllBtn && catField) {
      selectAllBtn.addEventListener("click", function () {
        var boxes = $$("input[type=checkbox]", catField).filter(function (box) { return !box.disabled; });
        var allOn = boxes.length > 0 && boxes.every(function (box) { return box.checked; });
        boxes.forEach(function (box) { box.checked = !allOn; });
        refreshSelectAll();
      });
    }

    var box = $("[data-run]");
    var nodes = {
      label: box ? $("[data-run-label]", box) : null,
      count: box ? $("[data-run-count]", box) : null,
      bar: box ? $("[data-run-bar]", box) : null,
      note: box ? $("[data-run-note]", box) : null
    };
    var LABELS = { queued: "Queued", running: "Generating…", done: "Done", failed: "Failed" };
    var pollTimer = null;

    var renderRun = function (run) {
      if (!box) return;
      box.hidden = false;
      if (nodes.label) nodes.label.textContent = LABELS[run.status] || run.status || "Working…";
      if (nodes.count) nodes.count.textContent = (run.generated || 0) + "/" + (run.requested || 0);
      var settled = (run.generated || 0) + (run.rejected || 0);
      var pct = run.status === "done" ? 100
        : Math.min(99, Math.round((settled / Math.max(1, run.requested || 1)) * 100));
      if (nodes.bar) nodes.bar.style.width = pct + "%";
      if (nodes.note) {
        var bits = [];
        if (run.rejected) bits.push(run.rejected + " rejected by validation or the duplicate check");
        if (run.model) bits.push("model " + run.model);
        if (run.status === "failed" && run.error) bits.push(run.error);
        nodes.note.textContent = bits.join(" · ");
      }
    };

    var stopPolling = function () {
      if (pollTimer) { window.clearTimeout(pollTimer); pollTimer = null; }
    };

    var setBusy = function (busy) {
      genBtn.disabled = !!busy;
      if (busy) genBtn.setAttribute("aria-busy", "true");
      else genBtn.removeAttribute("aria-busy");
    };

    var pollRun = function (runId) {
      stopPolling();
      var failures = 0;

      var step = function () {
        api("/api/runs/" + encodeURIComponent(runId)).then(function (run) {
          failures = 0;
          renderRun(run);
          if (run.status === "done") {
            setBusy(false);
            toast("Ideas ready",
              (run.generated || 0) + " of " + (run.requested || 0) + " ideas passed validation.",
              "good", 3400);
            window.setTimeout(function () {
              window.location.href = "/?run=" + encodeURIComponent(run.id);
            }, 700);
            return;
          }
          if (run.status === "failed") {
            setBusy(false);
            toast("Generation failed", run.error || "The provider returned an error.", "error", 12000);
            return;
          }
          pollTimer = window.setTimeout(step, 1500);
        }).catch(function (err) {
          failures += 1;
          if (failures >= 4) {
            setBusy(false);
            toast("Lost track of the run",
              err.message + " Open History to see whether the batch finished.", "error", 12000);
            return;
          }
          pollTimer = window.setTimeout(step, 2500);
        });
      };

      pollTimer = window.setTimeout(step, 500);
    };

    genBtn.addEventListener("click", function () {
      var autoOn = !!(autoBox && autoBox.checked);
      var chosen = autoOn ? [] : categories();
      if (!autoOn && chosen.length === 0) {
        toast("Pick a category", "Select at least one category, or switch Auto mode on.", "warn");
        return;
      }
      var wasHidden = box && box.hidden;
      renderRun({ status: "queued", requested: count, generated: 0, rejected: 0, model: "" });
      if (box) box.hidden = false;
      setBusy(true);

      api("/api/ideas/generate", {
        method: "POST",
        body: { count: count, categories: chosen, auto: autoOn }
      }).then(function (run) {
        renderRun(run);
        pollRun(run.id);
      }).catch(function (err) {
        setBusy(false);
        if (box && wasHidden) box.hidden = true;
        toast("Could not start", err.message, "error", 12000);
      });
    });

    var activeId = panel && panel.getAttribute("data-active-run");
    if (activeId) {
      box && (box.hidden = false);
      setBusy(true);
      pollRun(activeId);
    }
  }

  /* ----------------------------------------------------------------- filters */
  function initFilters() {
    var input = $("[data-search]");
    var cards = $$("[data-idea]");
    if (!input || !cards.length) return;

    var buttons = $$("[data-filter]");
    var countEl = $("[data-result-count]");
    var noMatch = $("[data-no-match]");
    var filter = "all";

    var apply = function () {
      var query = input.value.trim().toLowerCase();
      var shown = 0;
      cards.forEach(function (card) {
        var haystack = card.getAttribute("data-search") || "";
        var matchesQuery = !query || haystack.indexOf(query) !== -1;
        var matchesFilter = filter === "all" ||
          (filter === "saved" && card.getAttribute("data-saved") === "true") ||
          (filter === "today" && card.getAttribute("data-today") === "true");
        var visible = matchesQuery && matchesFilter;
        card.classList.toggle("is-hidden", !visible);
        if (visible) shown += 1;
      });
      if (countEl) countEl.textContent = "Showing " + shown + " idea" + (shown === 1 ? "" : "s");
      if (noMatch) noMatch.hidden = shown !== 0;
    };

    input.addEventListener("input", apply);
    input.addEventListener("search", apply);
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        buttons.forEach(function (other) {
          other.classList.toggle("active", other === btn);
          other.setAttribute("aria-pressed", other === btn ? "true" : "false");
        });
        filter = btn.getAttribute("data-filter") || "all";
        apply();
      });
    });

    document.addEventListener("vs:changed", apply);
  }

  /* -------------------------------------------------------------- expand all */
  function initExpandAll() {
    var btn = $("[data-expand-all]");
    if (!btn) return;
    var details = $$("details[data-details]");
    if (!details.length) return;
    btn.addEventListener("click", function () {
      var anyClosed = details.some(function (item) { return !item.open; });
      details.forEach(function (item) { item.open = anyClosed; });
      btn.textContent = anyClosed ? "Collapse all" : "Expand all";
    });
  }

  /* -------------------------------------------------------------------- save */
  function initSave() {
    $$("[data-save]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-save");
        btn.disabled = true;
        api("/api/ideas/" + encodeURIComponent(id) + "/save", { method: "POST" })
          .then(function (out) {
            var saved = !!out.saved;
            btn.classList.toggle("on", saved);
            btn.setAttribute("aria-pressed", saved ? "true" : "false");
            btn.title = saved ? "Remove from saved" : "Save this idea";
            var card = btn.closest("[data-idea]");
            if (card) card.setAttribute("data-saved", saved ? "true" : "false");
            toast(saved ? "Saved" : "Removed",
              saved ? "Idea added to your saved list." : "Idea removed from saved.",
              "good", 2600);
            document.dispatchEvent(new CustomEvent("vs:changed"));
          })
          .catch(function (err) { toast("Could not save", err.message, "error"); })
          .then(function () { btn.disabled = false; });
      });
    });
  }

  /* -------------------------------------------------------------------- copy */
  function initCopy() {
    $$("[data-copy]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var selector = btn.getAttribute("data-copy");
        var target = selector ? document.querySelector(selector) : null;
        if (!target) {
          toast("Nothing to copy", "The source block is missing on this page.", "error");
          return;
        }
        var text = (target.textContent || "").trim();
        if (!text) {
          toast("Nothing to copy", "That block is empty.", "warn");
          return;
        }
        copyText(text)
          .then(function () { toast("Copied", "Copied " + text.length + " characters.", "good", 2400); })
          .catch(function (err) { toast("Copy failed", err.message, "error"); });
      });
    });
  }

  /* -------------------------------------------------------------- regenerate */
  function initRegenerate() {
    $$("[data-regen]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-regen");
        var original = btn.textContent;
        btn.disabled = true;
        btn.textContent = "Regenerating…";
        api("/api/ideas/" + encodeURIComponent(id) + "/regenerate", { method: "POST" })
          .then(function (out) {
            var title = out && out.idea && out.idea.title ? out.idea.title : "A fresh idea replaced the old one.";
            toast("Regenerated", title, "good", 4000);
            window.setTimeout(function () { window.location.reload(); }, 1200);
          })
          .catch(function (err) {
            toast("Regenerate failed", err.message, "error", 12000);
            btn.disabled = false;
            btn.textContent = original;
          });
      });
    });
  }

  /* ------------------------------------------------------------------ voices */
  var voicesPromise = null;

  function loadVoices() {
    if (!voicesPromise) {
      voicesPromise = api("/api/voices").catch(function (err) {
        voicesPromise = null;
        throw err;
      });
    }
    return voicesPromise;
  }

  function fillVoiceSelects() {
    var selects = $$("[data-voice-select]");
    if (!selects.length) return;
    loadVoices().then(function (data) {
      var list = (data && data.voices) || [];
      if (!list.length) {
        var reason = data && data.configured
          ? "No voices on this account"
          : "Add an ElevenLabs key in Config";
        selects.forEach(function (select) {
          select.textContent = "";
          var opt = document.createElement("option");
          opt.value = "";
          opt.textContent = reason;
          select.appendChild(opt);
          select.disabled = true;
        });
        return;
      }
      selects.forEach(function (select) {
        var current = select.value;
        select.textContent = "";
        list.forEach(function (voice) {
          var opt = document.createElement("option");
          opt.value = voice.id;
          var bits = [voice.name || voice.id];
          if (voice.gender) bits.push(voice.gender);
          if (voice.accent) bits.push(voice.accent);
          opt.textContent = bits.join(" · ");
          if (voice.preview_url) opt.setAttribute("data-preview", voice.preview_url);
          select.appendChild(opt);
        });
        var preferred = current || (data && data.default) || "";
        var exists = list.some(function (voice) { return voice.id === preferred; });
        if (preferred && exists) select.value = preferred;
      });
    }).catch(function (err) {
      selects.forEach(function (select) {
        select.textContent = "";
        var opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "Voice list unavailable";
        select.appendChild(opt);
        select.disabled = true;
      });
      toast("Voice list failed", err.message, "error", 9000);
    });
  }

  function initVoicePanels() {
    $$("[data-speed]").forEach(function (range) {
      var panel = range.closest("[data-voice-panel]") || range.closest(".voice-grid");
      var out = panel ? $("[data-speed-label]", panel) : null;
      var sync = function () {
        var value = parseFloat(range.value);
        if (out) out.textContent = String(isNaN(value) ? range.value : value) + "×";
      };
      range.addEventListener("input", sync);
      sync();
    });

    $$("[data-voice-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-voice-toggle");
        var details = document.querySelector('details[data-details="' + id + '"]');
        if (details) {
          details.open = true;
          details.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });

    $$("[data-voice]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-voice");
        var panel = btn.closest("[data-voice-panel]") ||
          document.querySelector('[data-voice-panel="' + id + '"]');
        var select = panel ? $("[data-voice-select]", panel) : null;
        var emotion = panel ? $("[data-emotion-select]", panel) : null;
        var speed = panel ? $("[data-speed]", panel) : null;
        var result = document.querySelector('[data-voice-result="' + id + '"]');
        var download = panel ? $("[data-voice-download]", panel) : null;
        var original = btn.textContent;

        btn.disabled = true;
        btn.textContent = "Generating…";
        if (result) {
          result.textContent = "";
          var note = document.createElement("p");
          note.className = "voice-meta";
          note.textContent = "Synthesising Hindi speech — this can take a few seconds.";
          result.appendChild(note);
        }

        var body = { voice_id: null, emotion: null, speed: null };
        if (select && select.value) body.voice_id = select.value;
        if (emotion && emotion.value) body.emotion = emotion.value;
        if (speed && speed.value) {
          var parsed = parseFloat(speed.value);
          if (!isNaN(parsed)) body.speed = parsed;
        }

        api("/api/ideas/" + encodeURIComponent(id) + "/voice", { method: "POST", body: body })
          .then(function (out) {
            if (result) {
              result.textContent = "";
              var audio = document.createElement("audio");
              audio.controls = true;
              audio.preload = "none";
              audio.src = out.url;
              result.appendChild(audio);

              var meta = document.createElement("p");
              meta.className = "voice-meta";
              var size = out.bytes ? Math.max(1, Math.round(out.bytes / 1024)) + " KB" : "";
              var bits = [out.voice_name || out.voice_id, out.model_id, out.speed + "×",
                out.chars + " characters"];
              if (size) bits.push(size);
              meta.textContent = bits.filter(Boolean).join(" · ");
              result.appendChild(meta);
            }
            if (download) {
              download.setAttribute("href", out.download);
              download.hidden = false;
            }
            toast("Voice ready", "Hindi voiceover generated. Press play to preview.", "good", 4000);
          })
          .catch(function (err) {
            if (result) {
              result.textContent = "";
              var problem = document.createElement("p");
              problem.className = "voice-meta bad";
              problem.textContent = err.message;
              result.appendChild(problem);
            }
            toast("Voice generation failed", err.message, "error", 14000);
          })
          .then(function () {
            btn.disabled = false;
            btn.textContent = original;
          });
      });
    });

    fillVoiceSelects();
  }

  /* -------------------------------------------------------------- config page */
  function initConfigTests() {
    var out = $("[data-test-out]");
    $$("[data-test]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var kind = btn.getAttribute("data-test");
        var original = btn.textContent;
        btn.disabled = true;
        btn.textContent = "Testing…";
        if (out) {
          out.hidden = false;
          out.className = "test-out";
          out.textContent = "Contacting the provider…";
        }
        api("/api/test/" + encodeURIComponent(kind), { method: "POST" })
          .then(function (data) {
            if (out) {
              out.textContent = JSON.stringify(data, null, 2);
              out.classList.add(data && data.ok ? "ok" : "fail");
            }
            if (data && data.ok) {
              toast("Key works", data.reason || "The provider accepted the saved key.", "good", 8000);
            } else {
              toast("Test failed", (data && (data.reason || data.message)) || "The provider rejected the key.", "error", 10000);
            }
          })
          .catch(function (err) {
            if (out) {
              out.className = "test-out fail";
              out.textContent = err.message;
            }
            toast("Test failed", err.message, "error", 10000);
          })
          .then(function () {
            btn.disabled = false;
            btn.textContent = original;
          });
      });
    });
  }

  /* --------------------------------------------------------------------- boot */
  startClock();
  initGenerator();
  initFilters();
  initExpandAll();
  initSave();
  initCopy();
  initRegenerate();
  initVoicePanels();
  initConfigTests();
})();

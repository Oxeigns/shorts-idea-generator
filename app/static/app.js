/* ViralShorts Ideas — interface behaviour.
   Plain ES2017, no build step, no third-party code.
   Every server error message is shown verbatim; nothing is swallowed. */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.prototype.slice.call((root || document).querySelectorAll(sel));

  /* ------------------------------------------------------------------ theme */
  const THEMES = ["dark", "light", "system"];
  const THEME_LABELS = { dark: "Dark", light: "Light", system: "Auto" };
  const META_COLORS = { dark: "#06060a", light: "#f2f2f7", system: "#f2f2f7" };

  function preferredTheme() {
    const match = document.cookie.match(/(?:^|;\s*)theme=(dark|light|system)/);
    if (match) return match[1];
    return document.documentElement.getAttribute("data-theme") || "dark";
  }

  function applyTheme(value, persist) {
    const theme = THEMES.indexOf(value) === -1 ? "dark" : value;
    document.documentElement.setAttribute("data-theme", theme);
    if (persist) {
      document.cookie = "theme=" + theme + "; Path=/; Max-Age=31536000; SameSite=Lax";
    }
    const dark =
      theme === "dark" ||
      (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", dark ? META_COLORS.dark : META_COLORS.light);

    const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
    $$("[data-theme-toggle]").forEach((btn) => {
      btn.setAttribute("aria-label", "Appearance: " + THEME_LABELS[theme] + ". Switch to " + THEME_LABELS[next] + ".");
      btn.setAttribute("title", "Appearance: " + THEME_LABELS[theme] + " (tap for " + THEME_LABELS[next] + ")");
    });
  }

  function initTheme() {
    applyTheme(preferredTheme(), false);
    $$("[data-theme-toggle]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme") || "dark";
        const next = THEMES[(THEMES.indexOf(current) + 1) % THEMES.length];
        applyTheme(next, true);
        toast("Appearance", THEME_LABELS[next] + " mode selected.", "good", 1800);
      });
    });
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if ((document.documentElement.getAttribute("data-theme") || "") === "system") applyTheme("system", false);
    };
    if (media.addEventListener) media.addEventListener("change", onChange);
    else if (media.addListener) media.addListener(onChange);
  }

  /* ------------------------------------------------------------------ toasts */
  function toast(title, message, variant, duration) {
    const host = document.getElementById("toasts");
    if (!host) return;
    const el = document.createElement("div");
    el.className = "toast" + (variant ? " " + variant : "");
    el.setAttribute("role", variant === "error" ? "alert" : "status");
    const strong = document.createElement("strong");
    strong.textContent = title || "Notice";
    el.appendChild(strong);
    if (message) {
      const body = document.createElement("span");
      body.textContent = String(message);
      el.appendChild(body);
    }
    host.appendChild(el);

    let closed = false;
    const close = () => {
      if (closed) return;
      closed = true;
      el.classList.add("leaving");
      window.setTimeout(() => el.remove(), 220);
    };
    el.addEventListener("click", close);
    window.setTimeout(close, duration || 6000);
    while (host.children.length > 4) host.firstElementChild.remove();
  }

  /* --------------------------------------------------------------- api calls */
  function detailOf(payload) {
    if (!payload) return "";
    const detail = payload.detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (item && typeof item === "object") return item.msg || JSON.stringify(item);
          return String(item);
        })
        .join("; ");
    }
    if (detail && typeof detail === "object") return JSON.stringify(detail);
    if (detail) return String(detail);
    if (payload.reason) return String(payload.reason);
    return "";
  }

  function api(url, options) {
    options = options || {};
    const hasBody = options.body !== undefined && options.body !== null;
    return fetch(url, {
      method: options.method || "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: hasBody ? { "Content-Type": "application/json" } : {},
      body: hasBody ? JSON.stringify(options.body) : undefined
    }).then((res) => {
      return res.text().then((text) => {
        let payload = null;
        if (text) {
          try {
            payload = JSON.parse(text);
          } catch (err) {
            payload = null;
          }
        }
        if (!res.ok) {
          const message =
            detailOf(payload) ||
            (payload && payload.error) ||
            ("HTTP " + res.status + (res.statusText ? " " + res.statusText : ""));
          const error = new Error(message);
          error.status = res.status;
          if (res.status === 401) {
            window.setTimeout(() => {
              window.location.href = "/login";
            }, 900);
          }
          throw error;
        }
        return payload;
      });
    }, () => {
      throw new Error("Network request failed. Check the connection and try again.");
    });
  }

  /* --------------------------------------------------------------- clock */
  function startClock() {
    const timeEls = $$("[data-clock-time]");
    const dateEls = $$("[data-clock-date]");
    if (!timeEls.length && !dateEls.length) return;

    let timeFmt;
    let dateFmt;
    try {
      timeFmt = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Kolkata",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false
      });
      dateFmt = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Kolkata",
        day: "2-digit",
        month: "2-digit",
        year: "numeric"
      });
    } catch (err) {
      timeFmt = new Intl.DateTimeFormat("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false
      });
      dateFmt = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "2-digit", year: "numeric" });
    }

    const parts = (fmt, date) => {
      const out = {};
      fmt.formatToParts(date).forEach((part) => {
        out[part.type] = part.value;
      });
      return out;
    };

    const tick = () => {
      const now = new Date();
      const t = parts(timeFmt, now);
      const hour = t.hour === "24" ? "00" : t.hour;
      const time = hour + ":" + t.minute + ":" + t.second;
      const d = parts(dateFmt, now);
      const date = d.day + "-" + d.month + "-" + d.year;

      timeEls.forEach((el) => {
        if (el.textContent !== time) el.textContent = time;
      });
      dateEls.forEach((el) => {
        if (el.textContent !== date) el.textContent = date;
      });
    };

    tick();
    window.setInterval(tick, 1000);
  }

  /* --------------------------------------------------------------- confirm */
  function confirmSheet(opts) {
    const dlg = document.getElementById("confirm-dialog");
    if (!dlg || typeof dlg.showModal !== "function") {
      return Promise.resolve(window.confirm(opts.message || opts.title || "Are you sure?"));
    }
    if (dlg.open) dlg.close();

    const title = document.getElementById("confirm-title");
    const message = document.getElementById("confirm-message");
    const okBtn = document.getElementById("confirm-ok");
    const cancelBtn = document.getElementById("confirm-cancel");

    title.textContent = opts.title || "Are you sure?";
    message.textContent = opts.message || "";
    okBtn.textContent = opts.confirmLabel || "Continue";
    okBtn.classList.toggle("danger", opts.danger !== false);

    return new Promise((resolve) => {
      let settled = false;
      const finish = (value) => {
        if (settled) return;
        settled = true;
        okBtn.removeEventListener("click", onOk);
        cancelBtn.removeEventListener("click", onCancel);
        dlg.removeEventListener("cancel", onCancel);
        dlg.removeEventListener("click", onBackdrop);
        if (dlg.open) dlg.close();
        resolve(value);
      };
      const onOk = () => finish(true);
      const onCancel = (event) => {
        if (event) event.preventDefault();
        finish(false);
      };
      const onBackdrop = (event) => {
        if (event.target === dlg) finish(false);
      };
      okBtn.addEventListener("click", onOk);
      cancelBtn.addEventListener("click", onCancel);
      dlg.addEventListener("cancel", onCancel);
      dlg.addEventListener("click", onBackdrop);
      dlg.showModal();
      window.setTimeout(() => {
        if (!opts.danger) okBtn.focus();
        else cancelBtn.focus();
      }, 40);
    });
  }

  /* --------------------------------------------------------------- clipboard */
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise((resolve, reject) => {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.className = "clipboard-helper";
      document.body.appendChild(area);
      area.select();
      let ok = false;
      try {
        ok = document.execCommand("copy");
      } catch (err) {
        ok = false;
      }
      area.remove();
      if (ok) resolve();
      else reject(new Error("The browser blocked clipboard access."));
    });
  }

  /* --------------------------------------------------------------- generator */
  function initGenerator() {
    const panel = $("[data-active-run]");
    const genBtn = $("[data-generate]");
    if (!genBtn) return;

    let count = 10;
    const autoBox = $("[data-auto]");
    const catField = $("[data-cat-field]");
    const countGroup = $("[data-count-group]");
    const summary = $("[data-gen-summary]");

    const categories = () =>
      $$("input[type=checkbox]", catField)
        .filter((box) => box.checked)
        .map((box) => box.value);

    const refreshSummary = () => {
      if (!summary) return;
      const autoOn = !!(autoBox && autoBox.checked);
      const chosen = categories().length;
      let scope = "choose at least one category";
      if (autoOn) scope = "all 12 categories";
      else if (chosen) scope = chosen + (chosen === 1 ? " category" : " categories");
      summary.textContent = count + " ideas · " + scope;
    };

    if (countGroup) {
      $$("[data-count]", countGroup).forEach((btn) => {
        btn.addEventListener("click", () => {
          count = parseInt(btn.getAttribute("data-count"), 10) || 10;
          $$("[data-count]", countGroup).forEach((other) => {
            const active = other === btn;
            other.classList.toggle("active", active);
            other.setAttribute("aria-pressed", active ? "true" : "false");
          });
          refreshSummary();
        });
      });
    }

    const syncCats = () => {
      const off = !!(autoBox && autoBox.checked);
      if (!catField) return;
      catField.classList.toggle("disabled", off);
      catField.setAttribute("aria-disabled", off ? "true" : "false");
      $$("input[type=checkbox]", catField).forEach((box) => {
        box.disabled = off;
      });
      refreshSummary();
    };

    if (autoBox) {
      autoBox.addEventListener("change", syncCats);
      syncCats();
    }

    const selectAllBtn = $("[data-select-all]");
    const refreshSelectAll = () => {
      if (!selectAllBtn || !catField) return;
      const boxes = $$("input[type=checkbox]", catField);
      const allOn = boxes.length > 0 && boxes.every((box) => box.checked);
      selectAllBtn.textContent = allOn ? "Clear all" : "Select all";
    };
    if (catField) {
      catField.addEventListener("change", () => {
        refreshSelectAll();
        refreshSummary();
      });
      refreshSelectAll();
    }
    if (selectAllBtn && catField) {
      selectAllBtn.addEventListener("click", () => {
        const boxes = $$("input[type=checkbox]", catField).filter((box) => !box.disabled);
        const allOn = boxes.length > 0 && boxes.every((box) => box.checked);
        boxes.forEach((box) => {
          box.checked = !allOn;
        });
        refreshSelectAll();
        refreshSummary();
      });
    }

    const box = $("[data-run]");
    const nodes = {
      label: box ? $("[data-run-label]", box) : null,
      count: box ? $("[data-run-count]", box) : null,
      bar: box ? $("[data-run-bar]", box) : null,
      note: box ? $("[data-run-note]", box) : null
    };
    const LABELS = { queued: "Queued", running: "Generating…", done: "Done", failed: "Failed" };
    let pollTimer = null;

    const renderRun = (run) => {
      if (!box) return;
      box.hidden = false;
      if (nodes.label) nodes.label.textContent = LABELS[run.status] || run.status || "Working…";
      if (nodes.count) nodes.count.textContent = (run.generated || 0) + "/" + (run.requested || 0);
      const settled = (run.generated || 0) + (run.rejected || 0);
      const pct =
        run.status === "done"
          ? 100
          : Math.min(99, Math.round((settled / Math.max(1, run.requested || 1)) * 100));
      if (nodes.bar) nodes.bar.style.width = pct + "%";
      if (nodes.note) {
        const bits = [];
        if (run.rejected) bits.push(run.rejected + " rejected by validation or the duplicate check");
        if (run.model) bits.push("model " + run.model);
        if (run.status === "failed" && run.error) bits.push(run.error);
        nodes.note.textContent = bits.join(" · ");
      }
    };

    const stopPolling = () => {
      if (pollTimer) {
        window.clearTimeout(pollTimer);
        pollTimer = null;
      }
    };

    const setBusy = (busy) => {
      genBtn.disabled = !!busy;
      if (busy) genBtn.setAttribute("aria-busy", "true");
      else genBtn.removeAttribute("aria-busy");
    };

    const pollRun = (runId) => {
      stopPolling();
      let failures = 0;

      const step = () => {
        api("/api/runs/" + encodeURIComponent(runId))
          .then((run) => {
            failures = 0;
            renderRun(run);
            if (run.status === "done") {
              setBusy(false);
              toast(
                "Ideas ready",
                run.generated + " of " + run.requested + " ideas passed validation.",
                "good",
                3400
              );
              window.setTimeout(() => {
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
          })
          .catch((err) => {
            failures += 1;
            if (failures >= 4) {
              setBusy(false);
              toast(
                "Lost track of the run",
                err.message + " Open History to see whether the batch finished.",
                "error",
                12000
              );
              return;
            }
            pollTimer = window.setTimeout(step, 2500);
          });
      };

      pollTimer = window.setTimeout(step, 500);
    };

    genBtn.addEventListener("click", () => {
      const autoOn = !!(autoBox && autoBox.checked);
      const chosen = autoOn ? [] : categories();
      if (!autoOn && chosen.length === 0) {
        toast("Pick a category", "Select at least one category, or switch Auto mode on.", "warn");
        return;
      }
      const wasHidden = box && box.hidden;
      renderRun({ status: "queued", requested: count, generated: 0, rejected: 0, model: "" });
      if (box) box.hidden = false;
      setBusy(true);

      api("/api/ideas/generate", {
        method: "POST",
        body: { count: count, categories: chosen, auto: autoOn }
      })
        .then((run) => {
          renderRun(run);
          pollRun(run.id);
        })
        .catch((err) => {
          setBusy(false);
          if (box && wasHidden) box.hidden = true;
          toast("Could not start", err.message, "error", 12000);
        });
    });

    const activeId = panel && panel.getAttribute("data-active-run");
    if (activeId) {
      if (box) box.hidden = false;
      setBusy(true);
      pollRun(activeId);
    }
    refreshSummary();
  }

  /* ----------------------------------------------------------------- filters */
  function initFilters() {
    const input = $("[data-search]");
    if (!input) return;

    const buttons = Array.from(document.querySelectorAll("[data-filter]"));
    const countEl = $("[data-result-count]");
    const noMatch = $("[data-no-match]");
    const initial = buttons.filter((btn) => btn.classList.contains("active"))[0];
    let filter = initial ? initial.getAttribute("data-filter") : "all";

    const apply = () => {
      const query = input.value.trim().toLowerCase();
      const cards = Array.from(document.querySelectorAll("[data-idea]"));
      let shown = 0;
      cards.forEach((card) => {
        const haystack = card.getAttribute("data-search") || "";
        const matchesQuery = !query || haystack.indexOf(query) !== -1;
        const matchesFilter =
          filter === "all" ||
          (filter === "saved" && card.getAttribute("data-saved") === "true") ||
          (filter === "today" && card.getAttribute("data-today") === "true");
        const visible = matchesQuery && matchesFilter;
        card.classList.toggle("is-hidden", !visible);
        if (visible) shown += 1;
      });
      if (countEl) countEl.textContent = "Showing " + shown + " idea" + (shown === 1 ? "" : "s");
      if (noMatch) noMatch.hidden = shown !== 0 || !cards.length;
    };

    input.addEventListener("input", apply);
    input.addEventListener("search", apply);
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        buttons.forEach((other) => {
          other.classList.toggle("active", other === btn);
          other.setAttribute("aria-pressed", other === btn ? "true" : "false");
        });
        filter = btn.getAttribute("data-filter") || "all";
        apply();
      });
    });

    document.addEventListener("vs:changed", apply);
    apply();
  }

  /* -------------------------------------------------------------- expand all */
  function initExpandAll() {
    const btn = $("[data-expand-all]");
    if (!btn) return;
    const details = $$("details[data-details]");
    if (!details.length) return;
    btn.addEventListener("click", () => {
      const anyClosed = details.some((item) => !item.open);
      details.forEach((item) => {
        item.open = anyClosed;
      });
      btn.textContent = anyClosed ? "Collapse all" : "Expand all";
    });
  }

  /* -------------------------------------------------------------------- save */
  function bumpStat(selector, delta) {
    const el = $(selector);
    if (!el) return;
    const current = parseInt(el.textContent, 10);
    if (!isNaN(current)) el.textContent = String(Math.max(0, current + delta));
  }

  function initSave() {
    $$("[data-save]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-save");
        const wasSaved = btn.getAttribute("aria-pressed") === "true";
        btn.disabled = true;
        api("/api/ideas/" + encodeURIComponent(id) + "/save", { method: "POST" })
          .then((out) => {
            const saved = !!out.saved;
            btn.classList.toggle("on", saved);
            btn.setAttribute("aria-pressed", saved ? "true" : "false");
            btn.setAttribute("aria-label", saved ? "Remove from saved" : "Save idea");
            btn.title = saved ? "Remove from saved" : "Save this idea";
            const card = btn.closest("[data-idea]");
            if (card) card.setAttribute("data-saved", saved ? "true" : "false");
            if (saved !== wasSaved) bumpStat("[data-stat-saved]", saved ? 1 : -1);
            toast(
              saved ? "Saved" : "Removed",
              saved ? "Idea added to your saved list." : "Idea removed from saved.",
              "good",
              2600
            );
            document.dispatchEvent(new CustomEvent("vs:changed"));
          })
          .catch((err) => toast("Could not save", err.message, "error"))
          .then(() => {
            btn.disabled = false;
          });
      });
    });
  }

  /* ------------------------------------------------------------------ delete */
  function initDelete() {
    $$("[data-delete]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-delete");
        const title = btn.getAttribute("data-title") || "this idea";
        confirmSheet({
          title: "Delete this idea?",
          message: "“" + title + "” will leave the library and its MP3 files will be erased. This cannot be undone.",
          confirmLabel: "Delete",
          danger: true
        }).then((ok) => {
          if (!ok) return;
          btn.disabled = true;
          api("/api/ideas/" + encodeURIComponent(id), { method: "DELETE" })
            .then((out) => {
              const card = btn.closest("[data-idea]");
              const wasSaved = !!card && card.getAttribute("data-saved") === "true";
              if (card) card.remove();
              bumpStat("[data-stat-total]", -1);
              if (wasSaved) bumpStat("[data-stat-saved]", -1);
              const files = out && out.files_removed ? " " + out.files_removed + " audio file(s) removed." : "";
              toast("Deleted", "Idea removed." + files, "good", 3200);
              document.dispatchEvent(new CustomEvent("vs:changed"));
            })
            .catch((err) => toast("Could not delete", err.message, "error", 10000))
            .then(() => {
              btn.disabled = false;
            });
        });
      });
    });
  }

  /* -------------------------------------------------------------------- copy */
  function initCopy() {
    $$("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const selector = btn.getAttribute("data-copy");
        const target = selector ? document.querySelector(selector) : null;
        if (!target) {
          toast("Nothing to copy", "The source block is missing on this page.", "error");
          return;
        }
        const text = (target.textContent || "").trim();
        if (!text) {
          toast("Nothing to copy", "That block is empty.", "warn");
          return;
        }
        copyText(text)
          .then(() => {
            toast("Copied", "Copied " + text.length + " characters.", "good", 2400);
          })
          .catch((err) => toast("Copy failed", err.message, "error"));
      });
    });
  }

  /* -------------------------------------------------------------- regenerate */
  function initRegenerate() {
    $$("[data-regen]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-regen");
        const original = btn.innerHTML;
        btn.disabled = true;
        btn.textContent = "Regenerating…";
        api("/api/ideas/" + encodeURIComponent(id) + "/regenerate", { method: "POST" })
          .then((out) => {
            const title = out && out.idea && out.idea.title ? out.idea.title : "A fresh idea replaced the old one.";
            toast("Regenerated", title, "good", 4000);
            window.setTimeout(() => {
              window.location.reload();
            }, 1200);
          })
          .catch((err) => {
            toast("Regenerate failed", err.message, "error", 12000);
            btn.disabled = false;
            btn.innerHTML = original;
          });
      });
    });
  }

  /* ------------------------------------------------------------------ voices */
  let voicesPromise = null;

  function loadVoices() {
    if (!voicesPromise) {
      voicesPromise = api("/api/voices").catch((err) => {
        voicesPromise = null;
        throw err;
      });
    }
    return voicesPromise;
  }

  function fillVoiceSelects() {
    const selects = $$("[data-voice-select]");
    if (!selects.length) return;
    loadVoices()
      .then((data) => {
        const list = (data && data.voices) || [];
        if (!list.length) {
          const reason = data && data.configured ? "No voices on this account" : "Add an ElevenLabs key in Config";
          selects.forEach((select) => {
            select.textContent = "";
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = reason;
            select.appendChild(opt);
            select.disabled = true;
          });
          return;
        }
        selects.forEach((select) => {
          const current = select.value;
          select.textContent = "";
          list.forEach((voice) => {
            const opt = document.createElement("option");
            opt.value = voice.id;
            const bits = [voice.name || voice.id];
            if (voice.gender) bits.push(voice.gender);
            if (voice.accent) bits.push(voice.accent);
            opt.textContent = bits.join(" · ");
            if (voice.preview_url) opt.setAttribute("data-preview", voice.preview_url);
            select.appendChild(opt);
          });
          const preferred = current || (data && data.default) || "";
          const exists = list.some((voice) => voice.id === preferred);
          if (preferred && exists) select.value = preferred;
        });
      })
      .catch((err) => {
        selects.forEach((select) => {
          select.textContent = "";
          const opt = document.createElement("option");
          opt.value = "";
          opt.textContent = "Voice list unavailable";
          select.appendChild(opt);
          select.disabled = true;
        });
        toast("Voice list failed", err.message, "error", 9000);
      });
  }

  function initVoicePanels() {
    $$("[data-speed]").forEach((range) => {
      const panel = range.closest("[data-voice-panel]") || range.closest(".voice-grid");
      const out = panel ? $("[data-speed-label]", panel) : null;
      const sync = () => {
        const value = parseFloat(range.value);
        if (out) out.textContent = String(isNaN(value) ? range.value : value) + "×";
      };
      range.addEventListener("input", sync);
      sync();
    });

    $$("[data-voice-toggle]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-voice-toggle");
        const details = document.querySelector('details[data-details="' + id + '"]');
        if (details) {
          details.open = true;
          details.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });

    $$("[data-voice]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-voice");
        const panel =
          btn.closest("[data-voice-panel]") || document.querySelector('[data-voice-panel="' + id + '"]');
        const select = panel ? $("[data-voice-select]", panel) : null;
        const emotion = panel ? $("[data-emotion-select]", panel) : null;
        const speed = panel ? $("[data-speed]", panel) : null;
        const result = document.querySelector('[data-voice-result="' + id + '"]');
        const download = panel ? $("[data-voice-download]", panel) : null;
        const original = btn.innerHTML;

        btn.disabled = true;
        btn.textContent = "Generating…";
        if (result) {
          result.textContent = "";
          const note = document.createElement("p");
          note.className = "voice-meta";
          note.textContent = "Synthesising Hindi speech — this can take a few seconds.";
          result.appendChild(note);
        }

        const body = { voice_id: null, emotion: null, speed: null };
        if (select && select.value) body.voice_id = select.value;
        if (emotion && emotion.value) body.emotion = emotion.value;
        if (speed && speed.value) {
          const parsed = parseFloat(speed.value);
          if (!isNaN(parsed)) body.speed = parsed;
        }

        api("/api/ideas/" + encodeURIComponent(id) + "/voice", { method: "POST", body: body })
          .then((out) => {
            if (result) {
              result.textContent = "";
              const audio = document.createElement("audio");
              audio.controls = true;
              audio.preload = "none";
              audio.src = out.url;
              result.appendChild(audio);

              const meta = document.createElement("p");
              meta.className = "voice-meta";
              const size = out.bytes ? Math.max(1, Math.round(out.bytes / 1024)) + " KB" : "";
              const bits = [
                out.voice_name || out.voice_id,
                out.model_id,
                out.speed + "×",
                out.chars + " characters"
              ];
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
          .catch((err) => {
            if (result) {
              result.textContent = "";
              const problem = document.createElement("p");
              problem.className = "voice-meta bad";
              problem.textContent = err.message;
              result.appendChild(problem);
            }
            toast("Voice generation failed", err.message, "error", 14000);
          })
          .then(() => {
            btn.disabled = false;
            btn.innerHTML = original;
          });
      });
    });

    fillVoiceSelects();
  }

  /* -------------------------------------------------------------- config page */
  function initConfigTests() {
    const out = $("[data-test-out]");
    $$("[data-test]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const kind = btn.getAttribute("data-test");
        const original = btn.textContent;
        btn.disabled = true;
        btn.textContent = "Testing…";
        if (out) {
          out.hidden = false;
          out.className = "test-out";
          out.textContent = "Contacting the provider…";
        }
        api("/api/test/" + encodeURIComponent(kind), { method: "POST" })
          .then((data) => {
            if (out) {
              out.textContent = JSON.stringify(data, null, 2);
              out.classList.add(data && data.ok ? "ok" : "fail");
            }
            if (data && data.ok) {
              toast("Key works", data.reason || "The provider accepted the saved key.", "good", 8000);
            } else {
              toast(
                "Test failed",
                (data && (data.reason || data.message)) || "The provider rejected the key.",
                "error",
                10000
              );
            }
          })
          .catch((err) => {
            if (out) {
              out.className = "test-out fail";
              out.textContent = err.message;
            }
            toast("Test failed", err.message, "error", 10000);
          })
          .then(() => {
            btn.disabled = false;
            btn.textContent = original;
          });
      });
    });
  }

  /* --------------------------------------------------------------- shortcuts */
  function initShortcuts() {
    document.addEventListener("keydown", (event) => {
      const tag = (event.target && event.target.tagName) || "";
      const typing = /INPUT|TEXTAREA|SELECT/.test(tag) || (event.target && event.target.isContentEditable);
      if (event.key === "/" && !typing) {
        const search = $("[data-search]");
        if (search) {
          event.preventDefault();
          search.focus();
          search.select();
        }
      }
      if (event.key === "Escape" && typing && event.target === $("[data-search]")) {
        const search = $("[data-search]");
        if (search && search.value) {
          search.value = "";
          search.dispatchEvent(new Event("input"));
        }
      }
    });
  }

  /* --------------------------------------------------------------------- boot */
  initTheme();
  startClock();
  initGenerator();
  initFilters();
  initExpandAll();
  initSave();
  initDelete();
  initCopy();
  initRegenerate();
  initVoicePanels();
  initConfigTests();
  initShortcuts();
})();

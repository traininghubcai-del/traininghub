/* Training Hub chat widget.
   States: hidden | open | minimized.
   Modes:  public | tm | trainer  (TM needs a key, Trainer needs a code).
   POSTs to /api/chat_bot -> chat_core.router via the bridge:
     { session_id, message, mode, tm_key?, trainer_code? }
   Renders { reply, mode, tm_id, trainer_id, display_name }. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const launcher = $("chat-launcher");
  const panel = $("chat-panel");
  const mini = $("chat-mini");
  const miniBadge = $("chat-mini-badge");
  const minBtn = $("chat-min");
  const closeBtn = $("chat-close");
  const badge = $("chat-badge");
  const hint = $("chat-hint");
  const connect = $("chat-connect");
  const keyInput = $("chat-key");
  const connectBtn = $("chat-connect-btn");
  const log = $("chat-log");
  const suggest = $("chat-suggest");
  const form = $("chat-form");
  const input = $("chat-input");

  if (!launcher || !panel) return;

  const KEY_RE = /^[A-Z0-9]+(?:-[A-Z0-9]+)+$/;
  const newSessionId = () =>
    "s-" + Math.random().toString(36).slice(2) + Date.now().toString(36);

  let sessionId = newSessionId();
  let mode = "public";        // requested lens
  let connectedAs = "";       // display name once authenticated

  // per-mode UI config
  const MODES = {
    public: {
      label: "Public",
      hint: "Ask about classes, topics, locations, and open seats.",
      placeholder: "Ask about classes, or paste a TM access key…",
      connect: null,
      chips: [
        ["FIT classes", "What FIT classes are available?"],
        ["Mini split · Nashville", "Any mini split classes in Nashville?"],
        ["Open airflow", "Show me open airflow classes"],
        ["New tech — where to start?", "I'm a brand new technician, which class should I start with?"],
      ],
    },
    tm: {
      label: "Territory Manager",
      hint: "Paste your TM access key to see stats for your territory.",
      placeholder: "Ask about your territory (e.g. “who's behind on Level 1?”)",
      connect: { label: "TM access key", placeholder: "e.g. NASH-DEMO-KEY", field: "tm_key" },
      chips: [
        ["My dealers", "Show my dealers and their training history."],
        ["Behind on Level 1", "Which dealers are behind on Level 1 in my territory?"],
      ],
    },
    trainer: {
      label: "Trainer",
      hint: "Enter your trainer code to see rosters and session stats.",
      placeholder: "Ask about your class roster and attendance",
      connect: { label: "Trainer code", placeholder: "e.g. TRAIN-MICAH", field: "trainer_code" },
      chips: [
        ["My classes", "Give me an overview of my classes and attendance."],
        ["Upcoming sessions", "What are my upcoming classes?"],
        ["Who's missing?", "Who registered but hasn't attended my classes?"],
      ],
    },
  };

  /* ---------- panel states ---------- */
  function setState(s) {
    panel.classList.toggle("chat-panel--hidden", s !== "open");
    panel.classList.toggle("chat-panel--min", false);
    launcher.classList.toggle("chat-launcher--hidden", s !== "hidden");
    mini.classList.toggle("chat-mini--hidden", s !== "minimized");
    if (s === "open") input.focus();
  }
  const openChat = () => setState("open");
  const minimizeChat = () => setState("minimized");
  const closeChat = () => setState("hidden");

  /* ---------- rendering ---------- */
  function bubble(text, who) {
    const el = document.createElement("div");
    el.className = "chat-msg chat-" + who;
    el.textContent = text;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    return el;
  }
  const me = (t) => bubble(t, "me");
  const bot = (t) => bubble(t, "bot");

  const GREET = {
    public: "Public mode. Ask me about classes, topics, locations, and open seats.",
    tm: "Territory Manager mode. Enter your TM access key above to see your dealers and their training status.",
    trainer: "Trainer mode. Enter your trainer code above to see your class rosters and attendance.",
  };
  function greet() { bot(GREET[mode]); }

  function renderChips() {
    suggest.innerHTML = "";
    MODES[mode].chips.forEach(([label, q]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.dataset.q = q;
      suggest.appendChild(b);
    });
  }

  function setBadge(text, kind) {
    badge.textContent = text;
    miniBadge.textContent = text;
    badge.className = "chat-badge chat-badge--" + kind;
    miniBadge.className = "chat-badge chat-badge--" + kind;
  }

  /* ---------- mode switching ---------- */
  function setMode(newMode) {
    const changed = newMode !== mode;
    mode = newMode;
    const cfg = MODES[mode];

    // switching mode starts a clean conversation: new server session, wiped log,
    // dropped connection. No more stacking Public + TM + Trainer in one thread.
    if (changed) {
      sessionId = newSessionId();
      connectedAs = "";
      log.innerHTML = "";
    }
    document.querySelectorAll(".chat-modebtn").forEach((b) =>
      b.classList.toggle("is-active", b.dataset.mode === mode));
    hint.textContent = cfg.hint;
    input.placeholder = cfg.placeholder;

    if (cfg.connect && !connectedAs) {
      connect.hidden = false;
      keyInput.placeholder = cfg.connect.placeholder;
      keyInput.value = "";
    } else {
      connect.hidden = true;
    }

    // badge reflects connection if any, else the mode
    if (connectedAs && mode !== "public") {
      setBadge(cfg.label + " · " + connectedAs, mode);
    } else {
      setBadge(cfg.label, mode === "public" ? "public" : mode);
    }
    renderChips();
    if (changed || !log.children.length) greet();
  }

  /* ---------- sending ---------- */
  async function post(body) {
    const typing = bot("…");
    typing.classList.add("chat-typing");
    try {
      const res = await fetch("/api/chat_bot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({ session_id: sessionId, mode }, body)),
      });
      const data = await res.json();
      typing.remove();
      bot(data.reply || "(no answer)");
      if (data.display_name) {
        connectedAs = data.display_name;
        connect.hidden = true;
        setBadge(MODES[data.mode].label + " · " + connectedAs, data.mode);
      }
      return data;
    } catch (err) {
      typing.remove();
      bot("Sorry — I couldn't reach the assistant. Is the server running?");
    }
  }

  function sendMessage(message) {
    // if the user pastes a key/code in the text box, route it as a connect
    const trimmed = message.trim();
    if (KEY_RE.test(trimmed) && mode !== "public") {
      return connectWith(trimmed);
    }
    me(message);
    post({ message });
  }

  function connectWith(code) {
    me("•••• (" + (mode === "trainer" ? "trainer code" : "access key") + ")");
    const field = MODES[mode].connect.field;
    post({ message: "", [field]: code });
  }

  /* ---------- wiring ---------- */
  launcher.addEventListener("click", openChat);
  mini.addEventListener("click", openChat);
  minBtn.addEventListener("click", minimizeChat);
  closeBtn.addEventListener("click", closeChat);

  document.querySelector(".chat-modes").addEventListener("click", (e) => {
    const btn = e.target.closest(".chat-modebtn");
    if (btn) setMode(btn.dataset.mode);
  });

  connectBtn.addEventListener("click", () => {
    const v = keyInput.value.trim();
    if (v) connectWith(v);
  });
  keyInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); connectBtn.click(); }
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    sendMessage(text);
  });

  suggest.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-q]");
    if (btn) sendMessage(btn.getAttribute("data-q"));
  });

  // init
  setMode("public");
})();

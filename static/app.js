// M&A Supply landing — per-class page driven by ?event=<id>.
// Reads the event id from the URL, loads that class, fills the page + form.
"use strict";

const ROLES = ["Technician", "Inside Sales", "Outside Sales", "Owner"];

const gate = document.getElementById("gate");
const gateInner = document.getElementById("gate-inner");
const classPage = document.getElementById("class-page");

let form, msg, submitBtn, branchSelect, list, counter, addBtn;

// ---------- gate states ----------
function showGate(html) {
  gateInner.innerHTML = html;
  gate.hidden = false;
  classPage.hidden = true;
}

const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];

// ---------- schedule guard (browser side) ----------
// The server is the authority — src/class_schedule.py refuses these writes no
// matter what the browser sends. These mirror it so the mistake is caught while
// the admin is still looking at the field, using the IDENTICAL wording.
const ERR_PAST_DATE = "Can't set the class date to a day that already passed.";
const ERR_BAD_DATE = "Date must be YYYY-MM-DD.";
const ERR_END_BEFORE_START = "End time must be after start time.";
// Mirrors src/hub_modes.GRADE_IS_FSR_ONLY. The server refuses an admin grade
// write outright; this is only so the refusal is legible before the click.
const GRADE_FSR_ONLY = "Start from FSR-VIEW to grade class";

// ---------- the Admin/FSR type filter ----------
// Buttons, not a dropdown. Each one tests the COMPUTED status coming off
// src/class_status.py, so the strip filters on what is true today rather than
// on anything stored. BAD DATE is deliberately last and only appears when
// there is at least one — it is an exception, not a category, and a chip
// reading "Bad date 0" every day would train people to ignore it.
const TYPE_FILTERS = [
  { key: "",          label: "All classes",   test: () => true },
  { key: "live",      label: "Coming up",     test: (e) => e.lifecycle === "live" },
  { key: "needs",     label: "Needs grading", test: (e) => e.fsr_audit === "needs grading" },
  { key: "graded",    label: "Graded",        test: (e) => e.status === "GRADED" },
  { key: "nosignups", label: "No signups",    test: (e) => e.status === "NO SIGNUPS" },
  { key: "erased",    label: "Erased",        test: (e) => e.status === "ERASED" },
  { key: "baddate",   label: "Bad date",      test: (e) => e.status === "BAD DATE",
    onlyIfAny: true },
];

let TYPE_FILTER = "";        // "" = All classes

// Filters whose rows are all in the past. Only these flip to newest-first;
// everything else — All classes included — stays chronological ascending.
const PAST_ONLY_FILTERS = new Set(["needs", "graded", "nosignups"]);

function chipTest(key) {
  const f = TYPE_FILTERS.find((x) => x.key === key);
  return f ? f.test : () => true;
}

// Counts come from the rows that survive every OTHER filter, so each button
// tells you what you would actually get, not what the unfiltered feed holds.
function drawChips(box, rows) {
  const html = TYPE_FILTERS.map((f) => {
    const n = rows.filter(f.test).length;
    if (f.onlyIfAny && !n && TYPE_FILTER !== f.key) return "";
    const on = TYPE_FILTER === f.key;
    return `<button type="button" class="ma-chip${on ? " is-on" : ""}${
      f.key === "baddate" ? " is-alarm" : ""}${!n ? " is-empty" : ""}"
      data-chip="${f.key}" aria-pressed="${on}">${escHtml(f.label)}<i>${n}</i></button>`;
  }).join("");
  if (box.dataset.html === html) return;      // don't blow away focus on retype
  box.dataset.html = html;
  box.innerHTML = html;
  box.querySelectorAll("[data-chip]").forEach((b) => {
    b.onclick = () => {
      TYPE_FILTER = b.dataset.chip;
      if (listRender) listRender();
    };
  });
}

// The device's LOCAL calendar day. Never toISOString() — that is UTC, and a
// Central-time admin working after 6pm would be handed tomorrow's date and
// told today is already past.
function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// Error string for a proposed date/time slot, or "" when it's legal.
// Blank times stay legal — a class with no time yet shows "Time TBD".
function scheduleError(dateStr, start, end) {
  const d = String(dateStr || "").trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return ERR_BAD_DATE;
  if (d < todayISO()) return ERR_PAST_DATE;
  const s = String(start || "").trim(), e = String(end || "").trim();
  if (s && e && e <= s) return ERR_END_BEFORE_START;
  return "";
}

// One definition of a class's display location — used by the index rows, the
// hover card and the Location filter, so the dropdown can never drift from the
// column it filters.
function locLabel(e) {
  return e.state ? `${e.region}, ${e.state}` : (e.region || "");
}

// Compact one-line class list with keyword search + month filter. Same dense row
// dense one-line rows so a long list stays scannable.
async function showIndex(intro) {
  try {
    const res = await fetch("/api/events");
    const data = await res.json();
    showEnvBanner(data.env);
    // branch names ride along on the public feed, so the FSR dialog can ask
    // "which branch?" before any code exists
    FSR_BRANCHES = data.branches || FSR_BRANCHES;
    const events = (data.events || []).slice()
      .sort((a, b) => (a.event_date || "").localeCompare(b.event_date || ""));

    // month options present in the data (for the date filter)
    const months = [];
    const seen = new Set();
    events.forEach((e) => {
      const k = (e.event_date || "").slice(0, 7);
      if (k && !seen.has(k)) { seen.add(k); months.push(k); }
    });
    const monthOpts = ['<option value="">All dates</option>'].concat(months.map((k) => {
      const [y, m] = k.split("-");
      return `<option value="${k}">${MONTH_NAMES[+m - 1]} ${y}</option>`;
    })).join("");

    // location options present in the data. Keyed off the SAME string the row's
    // Location column renders, so the dropdown and the column always agree —
    // the raw branch field is inconsistent ("101- Nashville" vs "Ft. Smith, AR").
    const locs = [];
    const locSeen = new Set();
    events.forEach((e) => {
      const k = locLabel(e);
      if (k && !locSeen.has(k)) { locSeen.add(k); locs.push(k); }
    });
    locs.sort((a, b) => a.localeCompare(b));
    const locOpts = ['<option value="">All locations</option>'].concat(
      locs.map((k) => `<option value="${escHtml(k)}">${escHtml(k)}</option>`)).join("");

    showGate(
      `<div class="ma-gate-box">
         <p class="ma-eyebrow">M&amp;A SUPPLY · TRAINING NETWORK</p>
         <h1 class="ma-gate-title">${intro || "Register for a class"}</h1>
         <p class="ma-gate-lede">Build elite technicians, protect your installs, and keep every
            dealer on the same playbook.</p>
         <div class="ma-metrics-grid" id="ma-metrics"></div>
         <div class="ma-addclass" id="add-class-box" hidden>
           <button type="button" class="ma-addclass-link" id="add-class-btn">ADD A CLASS</button>
           <p class="ma-addclass-note">Edit an existing class by opening its registration page &rarr; Admin</p>
           <div class="ma-newclass" id="new-class-form" hidden></div>
         </div>
         <div class="ma-reg-tools">
           <input id="reg-q" class="ma-reg-search" type="search" placeholder="Search class, location or FSR…" autocomplete="off" aria-label="Search classes" />
           <select id="reg-loc" class="ma-reg-month" aria-label="Filter by location">${locOpts}</select>
           <select id="reg-m" class="ma-reg-month" aria-label="Filter by month">${monthOpts}</select>

           <span class="ma-reg-count" id="reg-count"></span>
         </div>
         <!-- Type filter. Buttons, not a dropdown: the whole point is to SEE
              at a glance how much of each kind there is, and a collapsed
              select hides both the options and their counts. -->
         <div class="ma-chips" id="reg-filters" role="group"
              aria-label="Filter classes by type" hidden></div>
         <p class="ma-reg-msg" id="reg-msg" hidden></p>
         <div class="ma-reg-scroll" id="reg-scroll">
           <div class="ma-reg-heads" id="reg-heads">
             <span>Date</span><span>Class</span><span>Time</span><span>FSR</span><span>Location</span>
             <span>Reg.</span><span>Status</span><span>Last reminder</span><span>#</span><span></span>
           </div>
           <div class="ma-reg-list" id="reg-list"></div>
         </div>
         <p class="ma-gate-actions" style="margin-top:18px">
           <a class="btn btn-primary" id="print-pack" href="/qr-pack" target="_blank" rel="noopener">Print all QR codes (PDF)</a>
         </p>
       </div>`);

    const esc = (s) => encodeURIComponent(s);
    const list = document.getElementById("reg-list");
    const countEl = document.getElementById("reg-count");
    const q = document.getElementById("reg-q");
    const mSel = document.getElementById("reg-m");
    const locSel = document.getElementById("reg-loc");
    const chipBox = document.getElementById("reg-filters");
    const printBtn = document.getElementById("print-pack");

    // Both restricted lenses render from /api/hub/classes, NOT /api/events. The
    // public feed stops at today by design, and finished + cancelled classes are
    // exactly what these two views exist to show.
    //
    // Order comes from the SERVER, already ranked by the status vocabulary:
    // TODAY, TOMORROW, OPEN (soonest first), then NOT-GRADED, GRADED,
    // NO SIGNUPS, ERASED (newest first). What needs doing floats up; the
    // archive sinks. Re-sorting here would just be a second opinion.
    const adminEvents = () => ADMIN_LIST.filter((c) => c && c.event_id && c.topic);
    // FSR is no longer a needs-grading-only queue. It is the same ledger scoped
    // to ONE branch, so an FSR sees their whole branch — what's coming, what
    // they owe a grade on, and what's already settled.
    const fsrEvents = () => FSR_LIST.filter((c) => c && c.event_id && c.topic);

    const sourceEvents = () => {
      if (FSR_ON && FSR_LIST.length) return fsrEvents();
      if (ADMIN_ON && ADMIN_LIST.length) return adminEvents();
      return events;
    };

    // The month and location dropdowns are built from whatever is on screen, so
    // switching the lens on has to widen them — otherwise a past class is in
    // the list but its month isn't offered. Keeps the current pick if it survives.
    const refreshOptions = (src) => {
      const keep = (sel, opts) => {
        const was = sel.value;
        sel.innerHTML = opts;
        sel.value = [...sel.options].some((o) => o.value === was) ? was : "";
      };
      const ms = [], msSeen = new Set();
      src.forEach((e) => {
        const k = (e.event_date || "").slice(0, 7);
        if (k && !msSeen.has(k)) { msSeen.add(k); ms.push(k); }
      });
      ms.sort();
      keep(mSel, ['<option value="">All dates</option>'].concat(ms.map((k) => {
        const [y, m] = k.split("-");
        return `<option value="${k}">${MONTH_NAMES[+m - 1]} ${y}</option>`;
      })).join(""));
      const ls = [], lsSeen = new Set();
      src.forEach((e) => {
        const k = locLabel(e);
        if (k && !lsSeen.has(k)) { lsSeen.add(k); ls.push(k); }
      });
      ls.sort((a, b) => a.localeCompare(b));
      keep(locSel, ['<option value="">All locations</option>'].concat(
        ls.map((k) => `<option value="${escHtml(k)}">${escHtml(k)}</option>`)).join(""));
    };

    // The status pill. The label and its css class are both computed server-side
    // (src/class_status.py) so this can never invent a seventh vocabulary.
    // A closed class is signalled with a ring, not extra words: the column is
    // sized for the longest label ("NO SIGNUPS") and " · locked" clipped it.
    const statePill = (e) =>
      `<span class="rr-state ${e.status_css || ""}${e.closed_at ? " is-locked" : ""}"${
        e.closed_at ? ` title="Closed ${escHtml(e.closed_at)} — grades are final"` : ""
      }>${escHtml(e.status || "")}</span>`;

    // The FSR-Audit column. Same truth as the status pill, flattened to the
    // only three answers an auditor asks. Under ADMIN it is deliberately inert
    // — an admin can see that a grade is owed, and cannot write one.
    const auditCell = (e) => {
      const owed = e.fsr_audit === "needs grading";
      return `<span class="rr-audit ${e.fsr_audit_css || ""}${
        owed && ADMIN_ON ? " is-blocked" : ""}"${
        owed && ADMIN_ON ? ` title="${GRADE_FSR_ONLY}"` : ""
      }>${escHtml(e.fsr_audit || "NA")}</span>`;
    };

    // ONE row layout for both restricted lenses. Admin and FSR are looking at
    // the same ledger through the same table — same columns, same cell
    // positions, same header. The ONLY thing that differs is the action at the
    // end of the row, because that is the only thing the two roles do
    // differently. (The public list keeps its narrower, quieter row.)
    const rowHTML = (e) => {
      const loc = locLabel(e);
      // under either restricted lens the row IS a classes_overview record, so
      // it already carries status/registered/reminders — no second lookup
      const a = (ADMIN_ON || FSR_ON) ? (e.status ? e : ADMIN_ROWS[e.event_id]) : null;
      const opCells = a
        ? `<span class="rr-reg" title="${a.registered} registered of ${a.capacity || "no cap"}">` +
            `<b>${a.registered}</b>${a.capacity ? `<i>/${a.capacity}</i>` : ""}</span>` +
          statePill(a) +
          auditCell(a) +
          `<span class="rr-rem ${a.reminders_sent ? "has" : ""}" title="${
            a.reminders_sent
              ? `${a.reminders_sent} reminder(s) sent` +
                ((a.reminder_stages || []).length ? ` — ${a.reminder_stages.join("/")}-day` : "") +
                `, last on ${a.last_reminder}`
              : "No reminders sent yet"}">${a.last_reminder || "&mdash;"}</span>` +
          `<span class="rr-remn ${a.reminders_sent ? "has" : ""}">${a.reminders_sent || "0"}</span>`
        : "";

      const cells =
        `<span class="rr-date">${escHtml(e.date_short)}</span>
         <span class="rr-name">${escHtml(e.topic)}</span>
         <span class="rr-time">${escHtml(e.time_display)}</span>
         <span class="rr-fsr">${escHtml(e.trainer) || "FSR TBD"}</span>
         <span class="rr-loc">${escHtml(loc)}</span>
         ${opCells}`;

      // The green CTA appears only under FSR. Admin sees the same "needs
      // grading" in the audit column and gets "Open →" — they can edit the
      // class, they cannot grade it. The server refuses either way.
      const needs = FSR_ON && a && a.fsr_audit === "needs grading";
      // A cancelled class is listed so nobody wonders where it went, but an FSR
      // cannot open one: the server refuses to hand a cancelled roster to any
      // mode but admin. So under FSR it is a row, not a destination.
      if (FSR_ON && a && a.status === "ERASED") {
        return `<div class="ma-reg-row is-erased" data-id="${esc(e.event_id)}">
                  ${cells}<span class="rr-go is-dead">Cancelled</span></div>`;
      }
      const left = a ? (a.registered || 0) - (a.graded_count || 0) : 0;
      // no title="" — the native tooltip is slow, unstyled and truncates too.
      // data-id drives the hover card built in initRowCards().
      return (
        `<a class="ma-reg-row" data-id="${esc(e.event_id)}"
            href="/?event=${esc(e.event_id)}${needs ? "&view=fsr" : ""}">
           ${cells}
           <span class="${needs ? "rr-grade" : "rr-go"}"${needs
             ? ` title="${left} student${left === 1 ? "" : "s"} still ungraded"` : ""}>${
             needs ? "Grade this class &rarr;"
                   : (ADMIN_ON || FSR_ON) ? "Open &rarr;" : "Register &rarr;"}</span>
         </a>`
      );
    };

    // Clicking the "needs grading" chip under ADMIN says why, and goes nowhere.
    // Delegated, because rows are rebuilt on every render.
    let msgTimer = null;
    const sayFsrOnly = () => {
      const el = document.getElementById("reg-msg");
      if (!el) return;
      el.textContent = GRADE_FSR_ONLY;
      el.hidden = false;
      clearTimeout(msgTimer);
      msgTimer = setTimeout(() => { el.hidden = true; }, 4000);
    };
    list.addEventListener("click", (ev) => {
      if (!ADMIN_ON) return;
      const chip = ev.target.closest(".rr-audit.is-blocked, .rr-grade");
      if (!chip) return;
      ev.preventDefault();
      ev.stopPropagation();
      sayFsrOnly();
    });

    let lastLens = null;
    const render = () => {
      const src = sourceEvents();
      // rebuild the dropdowns only when the lens actually flips, so typing in
      // the search box never yanks the month/location pick out from under you
      const lens = FSR_ON ? "fsr" : (src !== events ? "admin" : "public");
      const srcIsAdmin = lens !== "public";
      if (lens !== lastLens) { refreshOptions(src); lastLens = lens; }

      const term = (q.value || "").trim().toLowerCase();
      const mk = mSel.value;
      const lk = locSel.value;
      // Everything EXCEPT the type filter. The chip counts are computed from
      // this, so each button says how many rows YOU would get right now —
      // counts that ignored the search box would just be decoration.
      const base = src.filter((e) => {
        if (lk && locLabel(e) !== lk) return false;
        if (mk && (e.event_date || "").slice(0, 7) !== mk) return false;
        if (term) {
          const hay = `${e.topic} ${e.region} ${e.state} ${e.trainer}`.toLowerCase();
          if (!hay.includes(term)) return false;
        }
        return true;
      });
      // Every filter tests the COMPUTED status, so a chip filters on today's
      // truth — never on a stored flag. See src/class_status.py.
      //
      // The server hands rows back in strict date order, and "All classes"
      // keeps exactly that: a schedule read forwards, with finished classes
      // sitting on their own dates rather than shoved into a block at the
      // bottom. The one exception is a filter that can ONLY contain finished
      // classes — there, "most recent first" is what you came to read.
      let shown = base.filter(chipTest(TYPE_FILTER));
      if (PAST_ONLY_FILTERS.has(TYPE_FILTER)) {
        shown = shown.slice().sort((a, b) =>
          (b.event_date || "").localeCompare(a.event_date || ""));
      }
      if (chipBox) {
        chipBox.hidden = !(ADMIN_ON || FSR_ON);
        if (!chipBox.hidden) drawChips(chipBox, base);
      }
      // is-admin carries the GRID (identical for both lenses); is-fsr only
      // recolours. Splitting them is what keeps the columns from drifting.
      const regMsg = document.getElementById("reg-msg");
      if (regMsg && !ADMIN_ON) regMsg.hidden = true;
      list.classList.toggle("is-admin", ADMIN_ON || FSR_ON);
      list.classList.toggle("is-fsr", FSR_ON);
      const heads = document.getElementById("reg-heads");
      if (heads) {
        heads.classList.toggle("is-admin", ADMIN_ON || FSR_ON);
        heads.classList.toggle("is-fsr", FSR_ON);
        // identical header under both lenses — same columns, same order
        heads.innerHTML =
          `<span>Date</span><span>Class</span><span>Time</span><span>FSR</span><span>Location</span>
           <span>Reg.</span><span>Status</span><span>FSR-Audit</span>
           <span>Last reminder</span><span>#</span><span>Action</span>`;
      }
      const scroll = document.getElementById("reg-scroll");
      // both lenses render the wide table, so both need the scroll affordance
      if (scroll) scroll.classList.toggle("is-admin", ADMIN_ON || FSR_ON);
      // ADD A CLASS is an Admin power; the grading queue must not offer it
      const addBox = document.getElementById("add-class-box");
      if (addBox) { addBox.hidden = !ADMIN_ON; if (ADMIN_ON) bindAddClass(); }
      if (!ADMIN_ON) {
        const nc = document.getElementById("new-class-form");
        if (nc) nc.hidden = true;
      }
      // admin lens recolours the page: heading + every class name go orange
      document.body.classList.toggle("admin-lens", ADMIN_ON);
      document.body.classList.toggle("fsr-lens", FSR_ON);
      // the page is a dealer signup page by default; under FSR-VIEW it is a work
      // queue, and "Register for a class" is the wrong instruction entirely
      const title = document.querySelector(".ma-gate-title");
      const lede = document.querySelector(".ma-gate-lede");
      const metrics = document.getElementById("ma-metrics");
      const owed = src.filter((e) => e.status === "NOT-GRADED").length;
      if (title) title.textContent = FSR_ON
        ? (FSR_BRANCH || "All branches") : (intro || "Register for a class");
      if (lede) lede.textContent = FSR_ON
        ? (owed
            ? `${owed} finished ${owed === 1 ? "class is" : "classes are"} still waiting on a grade — ${
                owed === 1 ? "it's" : "they're"} at the top.`
            : "Nothing owed a grade here. Everything coming up, and everything already settled.")
        : "Build elite technicians, protect your installs, and keep every dealer on the same playbook.";
      if (metrics) metrics.hidden = FSR_ON;
      // "nothing to grade" is a result, not a failed search — say so plainly
      const emptyMsg = FSR_ON && !src.length
        ? `No classes at ${escHtml(FSR_BRANCH || "any branch")} yet.`
        : "No classes match — try a different search or date.";
      list.innerHTML = shown.length
        ? shown.map(rowHTML).join("")
        : `<div class="ma-reg-empty">${emptyMsg}</div>`;
      countEl.textContent = `${shown.length} ${shown.length === 1 ? "class" : "classes"}` +
        (FSR_ON && owed ? ` \u00b7 ${owed} to grade` : "");
      const publicIds = new Set(events.map((e) => e.event_id));
      const printable = shown.filter((e) => publicIds.has(e.event_id));

      // Print follows the list: send the visible ids in their on-screen order so
      // the QR sheet is exactly what the user filtered/sorted down to.
      if (printBtn) printBtn.hidden = FSR_ON;
      if (printBtn && !FSR_ON) {
        // The QR sheet is a dealer-facing handout, so it only ever carries
        // classes the public feed would show — a past class printed on a wall
        // is a link that can no longer be registered against.
        const n = printable.length;
        const filtered = n !== events.length;
        if (n === 0) {
          printBtn.removeAttribute("href");
          printBtn.classList.add("is-disabled");
          printBtn.textContent = "No classes to print";
        } else {
          printBtn.classList.remove("is-disabled");
          printBtn.href = filtered
            ? "/qr-pack?events=" + printable.map((e) => encodeURIComponent(e.event_id)).join(",")
            : "/qr-pack";
          printBtn.textContent = filtered
            ? `Print ${n} QR code${n === 1 ? "" : "s"} (PDF)`
            : "Print all QR codes (PDF)";
        }
      }
    };

    q.addEventListener("input", render);
    mSel.addEventListener("change", render);
    locSel.addEventListener("change", render);
    listRender = render;
    render();
    // a getter, not the array: under ADMIN-VIEW the rows on screen include past
    // classes that were never in the public feed, and they need cards too
    initRowCards(list, sourceEvents);
    loadStats();
    bindAdminView();
    bindFsrView();
    if (ADMIN_ON) loadAdminRows();   // survives a re-render within the session
    if (FSR_ON) loadFsrRows(codeFor("fsr"), FSR_BRANCH);
  } catch (e) {
    showGate(`<div class="ma-gate-box"><h1 class="ma-gate-title">Couldn't load classes</h1><p class="ma-gate-text">${e.message} — is the server running?</p></div>`);
  }
}

// ---------- test-hub banner ----------
// A staging hub is a pixel-perfect clone of the live one, and the mistake that
// can't be undone is editing the wrong hub. So a non-production process says so
// on every page, in a bar you have to scroll past, not a subtle badge.
function showEnvBanner(env) {
  if (!env || env === "production") return;
  if (document.getElementById("ma-envbar")) return;
  const bar = document.createElement("div");
  bar.id = "ma-envbar";
  bar.className = "ma-envbar";
  bar.textContent = `${env.toUpperCase()} HUB — safe to break. Not the live site, and no email leaves this machine.`;
  document.body.prepend(bar);
  document.body.classList.add("has-envbar");
}

// ---------- class list hover card ----------
// Rows are one line, so long class names get clipped. Hovering (or tabbing to)
// a row opens a card with the FULL name and the details that don't fit —
// trainer, venue, level, and the class description in full.
function initRowCards(listEl, getEvents) {
  const lookup = (id) => (getEvents() || []).find((e) => e.event_id === id);

  let card = document.getElementById("ma-rowcard");
  if (!card) {
    card = document.createElement("div");
    card.id = "ma-rowcard";
    card.className = "ma-rowcard";
    card.hidden = true;
    document.body.appendChild(card);
  }

  let openTimer = null, current = null;

  const build = (e) => {
    const where = e.class_address || e.event_location || "";
    const loc = locLabel(e);
    const bits = [
      ["When", `${escHtml(e.weekday_display)}, ${escHtml(e.date_display)} &middot; ${escHtml(e.time_display)}`],
      ["Where", [where, loc].filter(Boolean).map(escHtml).join(" &middot; ")],
      ["Trainer", escHtml(e.trainer) || "To be assigned"],
      ["Level", escHtml(e.track) || "—"],
    ];
    return `<p class="rc-eyebrow">${escHtml(e.date_short)}</p>
      <h4 class="rc-title">${escHtml(e.topic)}</h4>
      <dl class="rc-meta">${bits.map(([k, v]) =>
        `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>
      ${e.notes ? `<div class="rc-desc">${e.notes.split(/\n+/)
        .map((p) => `<p>${escHtml(p)}</p>`).join("")}</div>` : ""}
      <p class="rc-go">${FSR_ON
        ? (e.status === "NOT-GRADED" ? "Click to grade this class" : "Click to open")
        : ADMIN_ON ? "Click to open &mdash; edit, roster, grade" : "Click to register"}</p>`;
  };

  // Prefer above the row; flip below when there isn't room. Never let the card
  // run off either edge.
  const place = (row) => {
    const r = row.getBoundingClientRect();
    card.style.visibility = "hidden";
    card.hidden = false;
    const c = card.getBoundingClientRect();
    let top = r.top - c.height - 10;
    if (top < 10) top = r.bottom + 10;
    if (top + c.height > window.innerHeight - 10) {
      top = Math.max(10, window.innerHeight - c.height - 10);
    }
    const left = Math.min(Math.max(12, r.left), window.innerWidth - c.width - 12);
    card.style.top = `${top}px`;
    card.style.left = `${left}px`;
    card.style.visibility = "visible";
  };

  const open = (row) => {
    const e = lookup(decodeURIComponent(row.dataset.id));
    if (!e) return;
    current = row;
    card.innerHTML = build(e);
    place(row);
  };

  const close = () => {
    clearTimeout(openTimer);
    current = null;
    card.hidden = true;
  };

  // small delay so scanning down the list doesn't strobe cards
  const arm = (row) => {
    clearTimeout(openTimer);
    openTimer = setTimeout(() => open(row), 140);
  };

  listEl.addEventListener("mouseover", (ev) => {
    const row = ev.target.closest(".ma-reg-row");
    if (row && row !== current) arm(row);
  });
  listEl.addEventListener("mouseout", (ev) => {
    const row = ev.target.closest(".ma-reg-row");
    if (row && !row.contains(ev.relatedTarget)) close();
  });
  listEl.addEventListener("focusin", (ev) => {
    const row = ev.target.closest(".ma-reg-row");
    if (row) open(row);              // keyboard: no delay
  });
  listEl.addEventListener("focusout", close);
  listEl.addEventListener("click", close);
  window.addEventListener("scroll", close, { passive: true });
  window.addEventListener("resize", close);
}

// ---------- ADMIN-VIEW on the master class list ----------
// Same code as the class page's Admin lens, same server-side check. Turning it
// on adds the operational columns the public list has no business showing.
function bindAdminView() {
  const btn = document.getElementById("admin-view-btn");
  if (!btn || btn.dataset.bound) return;
  btn.dataset.bound = "1";
  btn.onclick = async () => {
    if (ADMIN_ON) {                       // toggle back to the public list
      ADMIN_ON = false; ADMIN_ROWS = {}; ADMIN_LIST = []; TYPE_FILTER = "";
      btn.textContent = "ADMIN-VIEW";
      btn.classList.remove("is-on");
      if (listRender) listRender();
      return;
    }
    let code = codeFor("admin");
    if (!code) {
      code = (prompt("Enter the Admin access code:") || "").trim();
      if (!code) return;
    }
    const ok = await loadAdminRows(code);
    if (!ok) {
      sessionStorage.removeItem("maHub:admin");
      alert("That code doesn't open the Admin view.");
      return;
    }
    rememberCode("admin", code);
    setFsrView(false);                    // alternatives, not layers
    ADMIN_ON = true;
    btn.textContent = "ADMIN-VIEW ON";
    btn.classList.add("is-on");
    if (listRender) listRender();
  };
}

// ---------- FSR: pick a branch, then unlock ----------
// Branch FIRST, code second. Two reasons, both practical:
//   - branch names are already public (the dealer registration dropdown is
//     built from the same list), so asking first gives nothing away
//   - a mistyped code then costs you nothing: the branch you picked is still
//     sitting there when the error appears
//
// Clicking FSR again ALWAYS reopens the branch step — switching branch is the
// common case. The code step is skipped once the code is proven this session.
// Leaving is a separate ✕, so "switch branch" and "get me out" are never the
// same click.
function bindFsrView() {
  const btn = document.getElementById("fsr-view-btn");
  const exit = document.getElementById("fsr-exit-btn");
  const dlg = document.getElementById("fsr-dialog");
  if (!btn || !dlg || btn.dataset.bound) return;
  btn.dataset.bound = "1";

  const stepBranch = document.getElementById("fsr-step-branch");
  const stepCode = document.getElementById("fsr-step-code");
  const title = document.getElementById("fsr-dialog-title");
  const stepLabel = document.getElementById("fsr-dialog-step");
  const chosen = document.getElementById("fsr-chosen");
  const codeInput = document.getElementById("fsr-code");
  const codeErr = document.getElementById("fsr-code-err");
  const sel = document.getElementById("fsr-branch");
  const nextBtn = document.getElementById("fsr-branch-go");

  // "__none__" is the placeholder, and it is NOT a choice — ALL branches is.
  // Next stays disabled until they actually answer the question.
  const picked = () => sel.value !== "__none__";
  const branchName = () => (sel.value === "__none__" ? "" : sel.value);

  const showStep = (which) => {
    stepBranch.hidden = which !== "branch";
    stepCode.hidden = which !== "code";
    if (which === "branch") {
      title.textContent = "Which branch do you cover?";
      stepLabel.textContent = "step 1 of 2";
      sel.focus();
    } else {
      title.textContent = "Enter your access code";
      stepLabel.textContent = "step 2 of 2";
      chosen.textContent = branchName() || "ALL branches";
      codeErr.hidden = true;
      codeInput.value = "";
      codeInput.focus();
    }
  };

  const close = () => { if (dlg.open) dlg.close(); };

  // Turn the lens on with the branch already chosen. Only reached once the
  // code has been verified server-side.
  const finish = async (code) => {
    FSR_BRANCH = branchName();
    const ok = await loadFsrRows(code, FSR_BRANCH);
    if (!ok) return false;
    setAdminView(false);                       // alternatives, not layers
    setFsrView(true);
    close();
    if (listRender) listRender();
    return true;
  };

  btn.onclick = () => {
    // The branch list is public and already on the page — no request, no gate,
    // so step 1 opens instantly even before any code exists.
    fillFsrBranches(FSR_BRANCHES);
    sel.value = FSR_ON || FSR_BRANCH ? FSR_BRANCH : "__none__";
    nextBtn.disabled = !picked();
    showStep("branch");
    if (!dlg.open) dlg.showModal();
  };

  sel.onchange = () => { nextBtn.disabled = !picked(); };

  nextBtn.onclick = async () => {
    if (!picked()) return;
    const known = codeFor("fsr");
    if (known && await finish(known)) return;  // proven this session — skip step 2
    if (known) sessionStorage.removeItem("maHub:fsr");   // it stopped working
    showStep("code");
  };

  document.getElementById("fsr-code-back").onclick = () => showStep("branch");

  document.getElementById("fsr-code-go").onclick = async () => {
    const code = (codeInput.value || "").trim();
    if (!code) { codeErr.textContent = "Enter the code."; codeErr.hidden = false; return; }
    codeErr.hidden = true;
    // verified on the SERVER — the browser has never held the code list
    let ok = false;
    try {
      const res = await fetch("/api/hub/unlock", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "fsr", code }),
      });
      ok = (await res.json()).ok === true;
    } catch (e) { ok = false; }
    if (!ok) {
      codeErr.textContent = "That code doesn't open the FSR view.";
      codeErr.hidden = false;
      codeInput.select();
      return;               // stay on step 2 — the chosen branch is untouched
    }
    rememberCode("fsr", code);
    if (!await finish(code)) {
      codeErr.textContent = "Couldn't load the classes. Try again.";
      codeErr.hidden = false;
    }
  };

  dlg.querySelectorAll("[data-fsr-cancel]").forEach((b) => { b.onclick = close; });
  codeInput.onkeydown = (e) => {
    if (e.key === "Enter") { e.preventDefault(); document.getElementById("fsr-code-go").click(); }
  };
  sel.onkeydown = (e) => {
    if (e.key === "Enter" && picked()) { e.preventDefault(); nextBtn.click(); }
  };
  if (exit) exit.onclick = () => { setFsrView(false); if (listRender) listRender(); };
}

// Fill the branch picker from the whole catalog, keeping the current pick if
// that branch still exists. The placeholder is rebuilt every time so "Next"
// can stay disabled until the question is actually answered.
function fillFsrBranches(branches) {
  const sel = document.getElementById("fsr-branch");
  if (!sel) return;
  sel.innerHTML = ['<option value="__none__">Select\u2026</option>',
                   '<option value="">ALL branches</option>'].concat(
    (branches || []).map((b) => {
      const name = typeof b === "string" ? b : b.branch;
      return `<option value="${escHtml(name)}">${escHtml(name)}</option>`;
    })).join("");
}

// Turn ADMIN-VIEW off (or on) from outside its own click handler.
function setAdminView(on) {
  if (ADMIN_ON === on) return;
  ADMIN_ON = on;
  if (!on) { ADMIN_ROWS = {}; ADMIN_LIST = []; TYPE_FILTER = ""; }
  const btn = document.getElementById("admin-view-btn");
  if (btn) {
    btn.textContent = on ? "ADMIN-VIEW ON" : "ADMIN-VIEW";
    btn.classList.toggle("is-on", on);
  }
}

// The nav button says which branch you're in — the one thing you can't tell
// from the list itself once you've scrolled. Kept separate from setFsrView
// because switching branch changes the label WITHOUT changing the lens state.
function paintFsrControl() {
  const btn = document.getElementById("fsr-view-btn");
  if (btn) {
    btn.textContent = FSR_ON ? `FSR \u00b7 ${FSR_BRANCH || "ALL"}` : "FSR";
    btn.title = FSR_ON ? "Switch branch" : "Open the FSR view";
    btn.classList.toggle("is-on", FSR_ON);
  }
  const exit = document.getElementById("fsr-exit-btn");
  if (exit) exit.hidden = !FSR_ON;
}

function setFsrView(on) {
  if (FSR_ON === on) { paintFsrControl(); return; }
  FSR_ON = on;
  if (!on) { FSR_ROWS = {}; FSR_LIST = []; TYPE_FILTER = ""; }
  paintFsrControl();
}

async function loadFsrRows(code, branch) {
  try {
    const res = await fetch("/api/hub/classes?mode=fsr&code=" +
                            encodeURIComponent(code || codeFor("fsr")) +
                            "&branch=" + encodeURIComponent(branch || ""));
    const data = await res.json();
    if (!data.ok) return false;
    FSR_ROWS = {};
    FSR_LIST = data.classes || [];        // server order: what needs doing first
    FSR_LIST.forEach((c) => { FSR_ROWS[c.event_id] = c; });
    // branches come from the WHOLE catalog, never from the filtered rows —
    // otherwise picking one branch would empty the picker behind you
    FSR_BRANCHES = data.branches || FSR_BRANCHES;
    if (FSR_ON && listRender) listRender();
    return true;
  } catch (e) {
    return false;
  }
}

// ---------- ADD A CLASS ----------
// Only three answers are required — branch, name, date. Everything else
// (state, timezone, venue, host line, level, trainer) is inherited from the
// classes already running at that branch, so a new class arrives complete.
let BRANCH_OPTS = [];
const CST_STATES = ["AR","AL","MS","LA","MO","OK","TX","TN","KY","FL"];

function bindAddClass() {
  const btn = document.getElementById("add-class-btn");
  if (!btn || btn.dataset.bound) return;
  btn.dataset.bound = "1";
  btn.onclick = () => {
    const box = document.getElementById("new-class-form");
    if (!box.hidden) { box.hidden = true; return; }
    drawNewClassForm();
    box.hidden = false;
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
}

function drawNewClassForm() {
  const box = document.getElementById("new-class-form");
  const opts = BRANCH_OPTS.map((b) =>
    `<option value="${escHtml(b.branch)}"></option>`).join("");
  box.innerHTML = `
    <div class="nc-grid">
      <div class="nc-field full"><label>Branch <span class="req">*</span></label>
        <input id="nc-branch" list="nc-branch-list" autocomplete="off"
               placeholder="Pick a branch, or type a new one — e.g. Conway, AR" />
        <datalist id="nc-branch-list">${opts}</datalist>
        <p class="nc-hint" id="nc-inherit">Region, state, timezone and venue are copied from this branch.</p></div>

      <div class="nc-new" id="nc-new" hidden>
        <p class="nc-new-title">New branch — it has nothing to copy from, so set these:</p>
        <div class="nc-grid">
          <div class="nc-field"><label>Region <span class="req">*</span></label>
            <input id="nc-region" placeholder="e.g. Conway" /></div>
          <div class="nc-field"><label>State</label>
            <input id="nc-state" maxlength="2" placeholder="AR" style="text-transform:uppercase" /></div>
          <div class="nc-field"><label>Timezone <span class="req">*</span></label>
            <select id="nc-tz"><option value="">Select…</option><option>CST</option><option>EST</option></select></div>
          <div class="nc-field"><label>Venue</label>
            <input id="nc-venue" placeholder="e.g. CONWAY BRANCH" /></div>
        </div>
        <p class="nc-hint">This branch is added to the list, so dealers can pick it when they register.</p>
      </div>
      <div class="nc-field full"><label>Class name <span class="req">*</span></label>
        <input id="nc-topic" type="text" placeholder="e.g. HEAT PUMP DIAGNOSTICS" autocomplete="off" /></div>
      <div class="nc-field"><label>Date <span class="req">*</span></label>
        <input id="nc-date" type="date" min="${todayISO()}" /></div>
      <div class="nc-field"><label>Capacity</label>
        <input id="nc-cap" type="number" min="1" value="20" /></div>
      <div class="nc-field"><label>Start</label><input id="nc-start" type="time" value="09:00" /></div>
      <div class="nc-field"><label>End</label><input id="nc-end" type="time" value="12:00" /></div>
      <div class="nc-field full"><label>Trainer (FSR)</label>
        <input id="nc-trainer" type="text" placeholder="Leave blank to inherit the branch's usual trainer" /></div>
      <div class="nc-field full"><label>Class address <span class="nc-opt">· optional, overrides the branch venue</span></label>
        <input id="nc-address" type="text" placeholder="Street address if it's not at the branch" /></div>
      <div class="nc-field full"><label>Notes</label>
        <input id="nc-notes" type="text" placeholder="e.g. Alt/Rep: DAIKIN REP" /></div>
    </div>
    <div class="nc-actions">
      <button type="button" class="btn btn-primary" id="nc-create">Create class</button>
      <button type="button" class="ma-mode-cancel" id="nc-cancel">Cancel</button>
      <span class="ma-panel-msg" id="nc-msg"></span>
    </div>`;
  document.getElementById("nc-cancel").onclick = () => { box.hidden = true; };
  document.getElementById("nc-create").onclick = createClass;
  const onBranch = () => {
    const v = (document.getElementById("nc-branch").value || "").trim();
    const b = BRANCH_OPTS.find((x) => x.branch.toLowerCase() === v.toLowerCase());
    const box = document.getElementById("nc-new");
    const hint = document.getElementById("nc-inherit");
    if (b) {
      box.hidden = true;
      hint.textContent = `Inherits: ${[b.region, b.state, b.location].filter(Boolean).join(" · ")}`;
    } else if (v) {
      box.hidden = false;
      hint.textContent = "New branch — fill in the details below.";
      // pre-fill from what they typed: "Conway, AR" -> region Conway, state AR
      const m = v.match(/^(.*?),\s*([A-Za-z]{2})\s*$/);
      const reg = document.getElementById("nc-region"), st = document.getElementById("nc-state");
      const ven = document.getElementById("nc-venue"), tz = document.getElementById("nc-tz");
      if (!reg.value) reg.value = (m ? m[1] : v).replace(/^\s*\d+\s*[-–]\s*/, "").trim();
      if (!st.value && m) st.value = m[2].toUpperCase();
      if (!ven.value) ven.value = (reg.value || v).toUpperCase() + " BRANCH";
      if (!tz.value && st.value) tz.value = CST_STATES.includes(st.value.toUpperCase()) ? "CST" : "EST";
    } else {
      box.hidden = true;
      hint.textContent = "Region, state, timezone and venue are copied from this branch.";
    }
  };
  document.getElementById("nc-branch").oninput = onBranch;
  document.getElementById("nc-branch").onchange = onBranch;
}

async function createClass() {
  const val = (id) => (document.getElementById(id).value || "").trim();
  const msg = document.getElementById("nc-msg");
  const branch = val("nc-branch"), topic = val("nc-topic"), date = val("nc-date");

  if (!branch || !topic || !date) {
    msg.textContent = "Branch, class name and date are required.";
    msg.className = "ma-panel-msg error";
    return;
  }
  const b = BRANCH_OPTS.find((x) => x.branch.toLowerCase() === branch.toLowerCase()) || {};
  const isNew = !b.branch;
  if (isNew && !val("nc-tz")) {
    msg.textContent = `"${branch}" is a new branch — pick its timezone so class times show correctly.`;
    msg.className = "ma-panel-msg error";
    return;
  }
  // Refuse before the confirm dialog, not after it — the server refuses the
  // same thing anyway, this just saves a pointless "are you sure?".
  const badSlot = scheduleError(date, val("nc-start"), val("nc-end"));
  if (badSlot) {
    msg.textContent = badSlot;
    msg.className = "ma-panel-msg error";
    return;
  }
  if (!confirm(`Create "${topic}" at ${branch} on ${date}?` +
      (isNew ? `\n\n"${branch}" is a NEW branch — it will be added to the branch list so dealers can select it.` : ""))) return;

  const btn = document.getElementById("nc-create");
  btn.disabled = true; btn.textContent = "Creating…"; msg.textContent = "";
  try {
    const res = await fetch("/api/hub/create-class", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: "admin", code: codeFor("admin"),
        fields: {
          branch, topic, event_date: date,
          region: b.region || val("nc-region") || branch,
          state: b.state || val("nc-state").toUpperCase(),
          timezone: val("nc-tz"),
          event_location: val("nc-venue"),
          capacity: val("nc-cap"), start_time: val("nc-start"), end_time: val("nc-end"),
          trainer: val("nc-trainer"), notes: val("nc-notes"), class_address: val("nc-address"),
        },
      }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Couldn’t create the class.");
    msg.textContent = "✓ " + data.message;
    msg.className = "ma-panel-msg success";
    setTimeout(() => { location.href = "/?event=" + encodeURIComponent(data.class.event_id); }, 900);
  } catch (e) {
    msg.textContent = e.message; msg.className = "ma-panel-msg error";
    btn.disabled = false; btn.textContent = "Create class";
  }
}

async function loadAdminRows(code) {
  try {
    const res = await fetch("/api/hub/classes?mode=admin&code=" +
                            encodeURIComponent(code || codeFor("admin")));
    const data = await res.json();
    if (!data.ok) return false;
    ADMIN_ROWS = {};
    ADMIN_LIST = data.classes || [];      // server order: status-ranked
    ADMIN_LIST.forEach((c) => { ADMIN_ROWS[c.event_id] = c; });
    BRANCH_OPTS = data.branches || [];
    if (ADMIN_ON && listRender) listRender();
    return true;
  } catch (e) {
    return false;
  }
}

// Headline numbers come from /api/stats — computed from the live catalog, so
// they can never quietly become a lie on the public page.
async function loadStats() {
  const box = document.getElementById("ma-metrics");
  if (!box) return;
  try {
    const d = await (await fetch("/api/stats")).json();
    if (d.error) return;
    const cells = [
      ["Classes this season", d.classes],
      ["Branches", d.branches],
      ["Program dealers", d.dealers],
      ["Class topics", d.topics],
    ];
    box.innerHTML = cells.map(([label, v]) =>
      `<article class="ma-metric"><p class="mm-label">${label}</p>
        <p class="mm-value">${v}</p></article>`).join("");
  } catch (e) { /* metrics are decoration — never block the list */ }
}

function showNotActive() {
  showGate(
    `<div class="ma-gate-box">
       <p class="ma-eyebrow">M&amp;A SUPPLY · TRAINING</p>
       <h1 class="ma-gate-title">This class link is not active</h1>
       <p class="ma-gate-text">The class code in this link isn't recognized. It may have ended, or the link is incomplete.</p>
       <p><a class="btn btn-primary" href="/">See available classes</a></p>
     </div>`);
}

// ---------- fill the class page ----------
function fillEvent(ev) {
  // The hero is the ONLY place the class is stated. Everything below it is
  // action (register / edit / grade) — no repeated dates, titles or locations.
  document.getElementById("hero-eyebrow").textContent = `M&A SUPPLY · ${(ev.region || "TRAINING").toUpperCase()}`;
  document.getElementById("hero-title").textContent = titleCase(ev.topic);
  document.getElementById("hero-sub").textContent =
    `${ev.weekday_display}, ${ev.date_display} · ${ev.time_display}`;
  // class_address is the branch location unless a custom address overrides it
  document.getElementById("hero-where").textContent = ev.class_address || ev.event_location || "";

  const noteEl = document.getElementById("ev-note");
  if (ev.notes) { noteEl.textContent = ev.notes; noteEl.hidden = false; }
  else { noteEl.hidden = true; }

  document.title = `${titleCase(ev.topic)} — M&A Supply Training`;
  document.getElementById("f-event_id").value = ev.event_id;

  const one = "/qr-pack?event=" + encodeURIComponent(ev.event_id);
  const pc = document.getElementById("print-class");
  if (pc) pc.href = one;
  // the dealer-facing way to get the same sheet: flier page 1, QR + details page 2
  const share = document.getElementById("share-flier");
  if (share) share.href = one;

  initFlier(ev);
}

// ---------- custom flier ----------
// One button next to "Print this class". Closed by default; clicking it opens a
// panel that either shows the class's flier or asks whether you want to add one.
let flier = null, flierEvent = null, flierPick = null;

function initFlier(ev) {
  flierEvent = ev.event_id;
  flier = ev.flier || { has_flier: false };
  flierPick = null;
  const btn = document.getElementById("flier-btn");
  const panel = document.getElementById("flier-panel");
  if (!btn || !panel) return;
  btn.textContent = flier.has_flier ? "View custom flier" : "Add custom flier";
  panel.hidden = true;
  btn.setAttribute("aria-expanded", "false");
  btn.onclick = () => {
    const open = panel.hidden;
    panel.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
    if (open) drawFlier();
  };
}

function drawFlier() {
  const panel = document.getElementById("flier-panel");
  if (flier.has_flier) {
    const view = flier.is_pdf
      ? `<a class="ma-flier-pdf" href="${flier.url}" target="_blank" rel="noopener">Open the flier (PDF)</a>`
      : `<a href="${flier.url}" target="_blank" rel="noopener"><img class="ma-flier-img" src="${flier.url}" alt="Flier for this class" /></a>`;
    panel.innerHTML =
      `${view}
       <p class="ma-flier-meta">${flier.original} · ${flier.size_display} · added ${flier.uploaded_at}</p>
       <p class="ma-flier-ask">Replace it with a different flier?</p>
       ${pickerHTML()}
       <p class="ma-flier-actions"><button type="button" class="ma-flier-remove" id="flier-remove">Remove this flier</button></p>`;
    document.getElementById("flier-remove").onclick = removeFlier;
  } else {
    panel.innerHTML =
      `<p class="ma-flier-ask">Would you like to upload a custom flier for this class?</p>
       <p class="ma-flier-note">If the vendor sent designed artwork, add it here and it shows on this page. Staff only.</p>
       ${pickerHTML()}`;
  }
  bindPicker();
}

function pickerHTML() {
  return `<div class="ma-flier-pick">
            <input type="file" id="flier-file" accept=".jpg,.jpeg,.png,.webp,.pdf" />
            <button type="button" class="btn btn-primary" id="flier-up" disabled>Upload flier</button>
          </div>
          <p class="ma-flier-msg" id="flier-msg" hidden></p>`;
}

function bindPicker() {
  const file = document.getElementById("flier-file");
  const up = document.getElementById("flier-up");
  file.onchange = () => {
    flierPick = file.files[0] || null;
    up.disabled = !flierPick;
    flierMsg("");
  };
  up.onclick = uploadFlier;
}

function flierMsg(text, type) {
  const el = document.getElementById("flier-msg");
  if (!el) return;
  el.textContent = text || "";
  el.hidden = !text;
  el.className = "ma-flier-msg" + (type ? " " + type : "");
}

// Uploads go through the same edit-code gate as every other change. Sent as
// base64 JSON because the stdlib server has no multipart parser.
async function flierPost(body) {
  const res = await fetch("/api/hub/flier", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, mode: "admin", code: codeFor("admin") }),
  });
  return res.json();
}

async function uploadFlier() {
  if (!flierPick) return;
  const up = document.getElementById("flier-up");
  up.disabled = true; up.textContent = "Uploading…";
  try {
    const b64 = await new Promise((ok, no) => {
      const r = new FileReader();
      r.onload = () => ok(String(r.result).split(",")[1] || "");
      r.onerror = () => no(new Error("Couldn't read that file."));
      r.readAsDataURL(flierPick);
    });
    const data = await flierPost({ event_id: flierEvent, action: "upload",
                                   filename: flierPick.name, data_b64: b64 });
    if (!data) { up.disabled = false; up.textContent = "Upload flier"; return; }
    if (!data.ok) { flierMsg(data.error || "Couldn't upload that flier.", "error"); up.disabled = false; up.textContent = "Upload flier"; return; }
    flier = data; flierPick = null;
    document.getElementById("flier-btn").textContent = "View custom flier";
    drawFlier();
    flierMsg("✓ " + data.message, "success");
  } catch (e) {
    flierMsg(e.message, "error");
    up.disabled = false; up.textContent = "Upload flier";
  }
}

async function removeFlier() {
  if (!confirm("Remove the custom flier from this class?")) return;
  const data = await flierPost({ event_id: flierEvent, action: "remove" });
  if (!data) return;
  if (!data.ok) { flierMsg(data.error || "Couldn't remove it.", "error"); return; }
  flier = data; flierPick = null;
  document.getElementById("flier-btn").textContent = "Add custom flier";
  drawFlier();
  flierMsg("✓ " + data.message, "success");
}

function titleCase(s) {
  return String(s || "").toLowerCase().replace(/\b([a-z])/g, (m) => m.toUpperCase())
    .replace(/\bAnd\b/g, "and").replace(/\b&\b/g, "&");
}

// ---------- dealer typeahead ----------
// Real program dealers from /api/dealers feed the company <datalist>. When the
// typed name matches one exactly, its customer_id rides along in a hidden field
// and the server fills Account Number + Territory Manager — never asked on the form.
let dealersByName = new Map();

async function loadDealers() {
  try {
    const res = await fetch("/api/dealers");
    const data = await res.json();
    const listEl = document.getElementById("dealer-options");
    (data.dealers || []).forEach((d) => {
      dealersByName.set(d.company_name.toLowerCase(), d.customer_id);
      const o = document.createElement("option");
      o.value = d.company_name;
      listEl.appendChild(o);
    });
    const company = document.getElementById("company_name");
    const hidden = document.getElementById("f-customer_id");
    const hint = document.getElementById("company-hint");
    company.addEventListener("input", () => {
      const id = dealersByName.get(company.value.trim().toLowerCase()) || "";
      hidden.value = id;
      hint.hidden = !id;
    });
  } catch (e) { /* typeahead is sugar — form still works without it */ }
}

function fillBranches(branches) {
  (branches || []).forEach((b) => {
    const o = document.createElement("option");
    o.value = b; o.textContent = b;
    branchSelect.appendChild(o);
  });
}

function revealClassPage() {
  gate.hidden = true;
  classPage.hidden = false;
}

async function loadEvent(eventId) {
  try {
    const res = await fetch("/api/event?id=" + encodeURIComponent(eventId));
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    if (!data.found) { showNotActive(); return; }
    revealClassPage();
    bindForm();
    fillEvent(data);
    fillBranches(data.branches);
    loadDealers();
    addRow(false); // Attendee 1
    bindModeLock();
    // Explicitly land in USER. Don't rely on the markup's default — this is the
    // one call that guarantees a dealer never sees the staff tools.
    applyMode("user");
  } catch (e) {
    showGate(`<div class="ma-gate-box"><h1 class="ma-gate-title">Something went wrong</h1><p class="ma-gate-text">${e.message} — is the server running?</p></div>`);
  }
}

// ---------- dynamic attendees ----------
function makeRow() {
  const row = document.createElement("div");
  row.className = "ma-attendee-row";
  const opts = ['<option value="">Role…</option>'].concat(ROLES.map((r) => `<option>${r}</option>`)).join("");
  row.innerHTML =
    `<input type="text" class="att-name" placeholder="Full name" autocomplete="off" />` +
    `<select class="att-role">${opts}</select>` +
    `<button type="button" class="att-remove" aria-label="Remove attendee" title="Remove">✕</button>`;
  return row;
}
function rows() { return Array.from(list.querySelectorAll(".ma-attendee-row")); }
function refresh() {
  const all = rows();
  all.forEach((r) => { r.querySelector(".att-remove").hidden = all.length <= 1; });
  const n = all.length;
  counter.textContent = `Total attending: ${n} ${n === 1 ? "person" : "people"}`;
}
function addRow(focus) {
  const row = makeRow();
  list.appendChild(row);
  refresh();
  if (focus) row.querySelector(".att-name").focus();
}

// ---------- validate + submit ----------
function setMsg(text, type) { msg.textContent = text; msg.className = "ma-form-msg" + (type ? " " + type : ""); }

function collectAttendees() {
  const empties = [], parts = [], list = [];
  rows().forEach((r) => {
    const nameEl = r.querySelector(".att-name");
    const name = nameEl.value.trim();
    const role = r.querySelector(".att-role").value;
    if (!name) { empties.push(nameEl); return; }
    parts.push(role ? `${name} (${role})` : name);
    list.push({ name, role });
  });
  return { count: parts.length, joined: parts.join(", "), list, empties };
}

function validate(att) {
  const email = form.contact_email.value.trim();
  const checks = [
    [form.contact_email, !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)],
    [form.company_name, !form.company_name.value.trim()],
    [form.branch, !form.branch.value],
  ];
  let ok = true;
  checks.forEach(([el, bad]) => { el.classList.toggle("invalid", bad); if (bad) ok = false; });
  att.empties.forEach((el) => el.classList.add("invalid"));
  let attMsg = "";
  if (att.count === 0) { ok = false; attMsg = "Add at least one attendee with a name."; }
  else if (att.empties.length) { ok = false; attMsg = "Enter a name for every attendee row (or remove the empty ones)."; }
  return { ok, attMsg };
}

function bindForm() {
  form = document.getElementById("register-form");
  msg = document.getElementById("form-msg");
  submitBtn = document.getElementById("submit-btn");
  branchSelect = document.getElementById("branch");
  list = document.getElementById("attendees-list");
  counter = document.getElementById("attendee-counter");
  addBtn = document.getElementById("add-attendee");

  addBtn.addEventListener("click", () => addRow(true));
  list.addEventListener("click", (e) => {
    if (e.target.classList.contains("att-remove") && rows().length > 1) {
      e.target.closest(".ma-attendee-row").remove();
      refresh();
    }
  });
  list.addEventListener("input", (e) => {
    if (e.target.classList.contains("att-name")) e.target.classList.remove("invalid");
  });
  form.addEventListener("input", (e) => {
    if (e.target.classList.contains("invalid") && !e.target.classList.contains("att-name")) {
      e.target.classList.remove("invalid");
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const att = collectAttendees();
    const { ok, attMsg } = validate(att);
    if (!ok) { setMsg(attMsg || "Please complete the highlighted fields.", "error"); return; }

    submitBtn.disabled = true;
    submitBtn.textContent = "Submitting…";
    setMsg("");

    const payload = {};
    new FormData(form).forEach((v, k) => { payload[k] = typeof v === "string" ? v.trim() : v; });
    payload.attending_count = String(att.count);
    payload.attendees = att.joined;        // snapshot string (fallback)
    payload.attendees_list = att.list;     // structured: [{name, role}, ...]

    try {
      const res = await fetch("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      // Read as TEXT first. res.json() on a proxy's HTML error page throws a
      // parser error, and that parser error used to be what the dealer read —
      // so a 502 from the edge looked identical to a bad form. Parse after we
      // know we have a body, and keep the status for the message.
      const body = await res.text();
      let data = {};
      try { data = body ? JSON.parse(body) : {}; } catch (_) { data = {}; }
      if (!res.ok || data.error) {
        throw new Error(data.error
          || `The server couldn't complete the signup (error ${res.status}).`);
      }
      setMsg("✓ " + data.message, "success");
      list.innerHTML = ""; addRow(false);
      form.contact_email.focus();
    } catch (err) {
      // A dropped connection reaches here as a TypeError — Safari words it
      // "Load failed", Chrome "Failed to fetch". Neither means anything to a
      // dealer on a phone, and both used to be shown verbatim. Say what
      // actually happened and what to do, and never claim the seat is lost:
      // the request may well have landed before the connection dropped.
      const offline = err instanceof TypeError
        || /load failed|failed to fetch|networkerror/i.test(err.message || "");
      setMsg(offline
        ? "Couldn't reach the server, so we can't confirm this signup. Check your "
          + "connection and try again — if it went through twice, your M&A branch can fix it."
        : err.message + " If this keeps happening, contact your M&A branch.",
        "error");
      console.error("register failed:", err);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Submit Registration";
    }
  });
}

// ================= HUB MODES =================
// One class page, three lenses. USER is open; ADMIN and FSR need a code that is
// checked on the SERVER — the browser never holds the code list, and a locked
// mode is never sent the roster in the first place.
//
// Accepted codes live in sessionStorage (not localStorage) on purpose: elevated
// access dies with the browser session instead of persisting on a shared laptop.

// No emoji anywhere in this UI — colour and type carry the meaning.
// Blue = user, orange = admin, green = FSR (the swatch is the icon).
const MODE_META = {
  user:  { label: "User",  sub: "Register",       cls: "is-user"  },
  admin: { label: "Admin", sub: "Edit · roster",  cls: "is-admin" },
  fsr:   { label: "FSR",   sub: "Roster · grade", cls: "is-fsr"   },
};
const LOCK_SVG = '<svg class="ma-mode-lock-ico" viewBox="0 0 24 24" width="12" height="12" ' +
  'aria-hidden="true"><path fill="currentColor" d="M17 9V7a5 5 0 0 0-10 0v2H5v12h14V9h-2zM9 7a3 3 0 0 1 6 0v2H9V7z"/></svg>';
const MODE_ORDER = ["user", "admin", "fsr"];

let ADMIN_ON = false;      // ADMIN-VIEW active on the master class list
let ADMIN_ROWS = {};       // event_id -> row, for lookups from the public list
let ADMIN_LIST = [];       // the same rows IN SERVER ORDER (status-ranked)
let FSR_ON = false;        // FSR view active: one branch's whole ledger
let FSR_ROWS = {};         // same shape, fetched with the FSR code
let FSR_LIST = [];
let FSR_BRANCH = "";       // "" = every branch
let FSR_BRANCHES = [];     // the whole catalog's branches, for the picker
let listRender = null;     // re-render hook for the class list

let currentMode = "user";
let pendingMode = null;
let modeData = {};

const codeFor = (m) => sessionStorage.getItem("maHub:" + m) || "";
const rememberCode = (m, c) => sessionStorage.setItem("maHub:" + m, c);

function buildModeSwitch() {
  // Dealers never see a mode picker. Once staff unlock a lens, a small bar
  // says which one they're in and offers the way back.
  const bar = document.getElementById("ma-modes");
  if (!bar) return;
  if (currentMode === "user") { bar.hidden = true; bar.innerHTML = ""; return; }
  const meta = MODE_META[currentMode];
  const other = currentMode === "admin" ? "fsr" : "admin";
  bar.hidden = false;
  bar.innerHTML =
    `<span class="ma-modebar ${meta.cls}">
       <span class="ma-mode-swatch" aria-hidden="true"></span>
       <b>${meta.label} view</b><small>${meta.sub}</small>
     </span>
     <button type="button" class="ma-modebar-alt" data-mode="${other}">
       Switch to ${MODE_META[other].label}</button>
     <button type="button" class="ma-modebar-exit" data-mode="user">Back to registration</button>`;
  bar.querySelectorAll("[data-mode]").forEach((b) => {
    b.onclick = () => requestMode(b.dataset.mode);
  });
}


function requestMode(mode) {
  if (mode === currentMode) return;
  if (mode === "user") { applyMode("user"); return; }
  if (codeFor(mode)) { loadMode(mode); return; }
  promptForCode(mode);
}

function promptForCode(mode) {
  pendingMode = mode || "admin";
  const box = document.getElementById("staff-gate");
  const link = document.getElementById("staff-link");
  if (!box) return;
  box.hidden = false;
  if (link) link.setAttribute("aria-expanded", "true");
  document.getElementById("mode-err").hidden = true;
  document.getElementById("mode-code").focus();
}

function closeCodePrompt() {
  pendingMode = null;
  const box = document.getElementById("staff-gate");
  const link = document.getElementById("staff-link");
  if (box) box.hidden = true;
  if (link) link.setAttribute("aria-expanded", "false");
}

// Ask the server to load this class through this lens. A 403 means the code was
// wrong (or expired) — we drop it and re-prompt rather than showing a stale view.
async function loadMode(mode) {
  const url = `/api/hub/class?event_id=${encodeURIComponent(flierEvent)}` +
              `&mode=${mode}&code=${encodeURIComponent(codeFor(mode))}`;
  try {
    const res = await fetch(url);
    const data = await res.json();
    if (!data.ok) {
      if (data.need_code) {
        sessionStorage.removeItem("maHub:" + mode);
        buildModeSwitch();
        promptForCode(mode);
        return;
      }
      throw new Error(data.error || "Couldn't open that view.");
    }
    modeData[mode] = data;
    applyMode(mode);
  } catch (e) {
    const err = document.getElementById("mode-err");
    err.textContent = e.message; err.hidden = false;
  }
}

function applyMode(mode) {
  currentMode = mode;
  closeCodePrompt();
  document.getElementById("mode-user").hidden = mode !== "user";
  document.getElementById("mode-admin").hidden = mode !== "admin";
  document.getElementById("mode-fsr").hidden = mode !== "fsr";
  document.querySelectorAll("#ma-modes [data-mode]").forEach((b) => {
    b.setAttribute("aria-selected", String(b.dataset.mode === mode));
  });
  document.body.classList.toggle("hub-restricted", mode !== "user");
  // print + flier upload are staff tools — a dealer never sees them
  const tools = document.getElementById("staff-tools");
  if (tools) tools.hidden = mode === "user";
  const slink = document.getElementById("staff-link");
  if (slink) slink.hidden = mode !== "user";
  if (mode === "user") document.getElementById("flier-panel").hidden = true;
  if (mode === "admin") renderAdmin(modeData.admin);
  if (mode === "fsr") renderFSR(modeData.fsr);
  buildModeSwitch();
  document.querySelectorAll("#ma-modes [data-mode]").forEach((b) => {
    b.setAttribute("aria-selected", String(b.dataset.mode === mode));
  });
}

function bindModeLock() {
  const link = document.getElementById("staff-link");
  const form = document.getElementById("staff-gate");
  if (!form) return;

  if (link) link.onclick = () => {
    if (form.hidden) promptForCode("admin"); else closeCodePrompt();
  };
  const cancel = document.getElementById("mode-cancel");
  if (cancel) cancel.onclick = closeCodePrompt;
  const rb = document.getElementById("roster-btn");
  if (rb) rb.onclick = printRoster;

  // whichever button was pressed decides the lens
  form.querySelectorAll(".ma-staff-go").forEach((b) => {
    b.addEventListener("click", () => { pendingMode = b.dataset.mode; });
  });

  form.onsubmit = async (e) => {
    e.preventDefault();
    const mode = pendingMode || "admin";
    const code = document.getElementById("mode-code").value.trim();
    const err = document.getElementById("mode-err");
    if (!code) { err.textContent = "Enter the staff code."; err.hidden = false; return; }
    form.querySelectorAll(".ma-staff-go").forEach((b) => { b.disabled = true; });
    try {
      const res = await fetch("/api/hub/unlock", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, code }),
      });
      const data = await res.json();
      if (!data.ok) { err.textContent = data.error; err.hidden = false; return; }
      rememberCode(mode, code);
      document.getElementById("mode-code").value = "";
      await loadMode(mode);
    } catch (ex) {
      err.textContent = ex.message; err.hidden = false;
    } finally {
      form.querySelectorAll(".ma-staff-go").forEach((b) => { b.disabled = false; });
    }
  };
}

// ---------- ADMIN view ----------
const ADMIN_FIELDS = [
  ["topic", "Topic", "text"], ["region", "Region", "text"],
  ["event_date", "Date", "date"], ["capacity", "Capacity", "number"],
  ["start_time", "Start", "time"], ["end_time", "End", "time"],
  ["trainer", "Trainer (FSR)", "text"],
];

function renderAdmin(d) {
  const box = document.getElementById("mode-admin");
  const e = d.edit, s = d.seats;
  const branchOpts = (d.branches || []).map((b) =>
    `<option value="${escHtml(b)}"${b === e.branch ? " selected" : ""}>${escHtml(b)}</option>`).join("");
  box.innerHTML = `
    <div class="ma-panel-head is-admin">
      <h2>Admin — ${escHtml(d.event.topic)}</h2>
      <p>Edit the class, watch the seats, see everyone who's registered.</p>
    </div>
    ${d.cancelled ? `<div class="ma-cancelled-banner">
      <span aria-hidden="true">⛔</span>
      <span><b>This class is cancelled.</b> Dealers can't see it or register.
        Everyone already registered is still listed below — reinstating puts
        the class back exactly as it was.</span></div>` : ""}
    <div class="ma-seatbar">
      <b>${s.taken}<span>/${s.capacity || "∞"}</span></b>
      <div class="ma-seatbar-track"><i style="width:${s.capacity ? Math.min(100, s.taken / s.capacity * 100) : 0}%"></i></div>
      <span>${s.left === null ? "no cap set" : s.left + " seats open"}</span>
    </div>
    <div class="ma-admin-grid">
      ${ADMIN_FIELDS.map(([k, label, type]) =>
        `<div class="ma-field"><label>${label}</label>
           <input data-af="${k}" type="${type}"${k === "event_date" ? ` min="${todayISO()}"` : ""}
                  value="${escHtml(e[k])}" /></div>`).join("")}
      <div class="ma-field full"><label>Branch <em>· from the tables</em></label>
        <select data-af="branch">${branchOpts}</select></div>
      <div class="ma-field full"><label>Class address <em>· floating, never edits the table</em></label>
        <input data-af="class_address" value="${escHtml(e.class_address)}"
               placeholder="${escHtml(e.event_location) || "Street address"}" />
        <p class="ma-field-hint" style="display:block">${e.class_address
          ? `Overriding <b>${escHtml(e.event_location)}</b> — clear it to go back.`
          : `Empty = using <b>${escHtml(e.event_location) || "—"}</b>.`}</p></div>
      <div class="ma-field full"><label>Notes</label>
        <textarea data-af="notes">${escHtml(e.notes)}</textarea></div>
    </div>
    <div class="ma-panel-actions">
      <button type="button" class="btn btn-primary" id="admin-save">Save changes</button>
      <button type="button" class="btn ${d.cancelled ? "btn-primary" : "btn-danger"}"
              id="admin-active">${d.cancelled ? "Reinstate class" : "Cancel class"}</button>
      <span class="ma-panel-msg" id="admin-msg"></span>
    </div>
    <div class="ma-confirm" id="admin-confirm" hidden></div>
    <h3 class="ma-panel-sub">Who's registered (${d.roster.length})</h3>
    ${rosterTable(d.roster, false)}

    <div class="ma-remind-box">
      <p class="ma-remind-title">Reminders</p>
      <p class="ma-remind-note">Email the "class is coming up" reminder now, or print
        one letter per student. Both count as a reminder sent.</p>
      <div class="ma-panel-actions">
        <button type="button" class="btn-remind" id="admin-email-remind">
          <span aria-hidden="true">📨</span> Email reminder now</button>
        <button type="button" class="btn-remind" id="admin-remind">
          <span aria-hidden="true">✉️</span> Send reminders (PDF)</button>
        <span class="ma-panel-msg" id="remind-msg"></span>
      </div>
    </div>`;
  // snapshot the class exactly as loaded — this is what a save is diffed against
  adminOriginal = {};
  box.querySelectorAll("[data-af]").forEach((el) => {
    adminOriginal[el.dataset.af] = String(el.value ?? "").trim();
  });
  document.getElementById("admin-save").onclick = saveAdmin;
  document.getElementById("admin-active").onclick = () => confirmSetActive(!!d.cancelled, d.roster.length);
  document.getElementById("admin-remind").onclick = generateReminders;
  document.getElementById("admin-email-remind").onclick = emailReminders;
  // typing again after a diff was shown invalidates it — recompute on next save
  box.querySelectorAll("[data-af]").forEach((el) => {
    el.addEventListener("input", () => {
      const c = document.getElementById("admin-confirm");
      if (c && !c.hidden) c.hidden = true;
    });
  });
}

// What the class looked like when the panel was drawn. Every save is diffed
// against this, so we only ever send fields that genuinely changed.
let adminOriginal = {};

const FIELD_LABELS = {
  topic: "Topic", region: "Region", event_date: "Date", capacity: "Capacity",
  start_time: "Start time", end_time: "End time", trainer: "Trainer (FSR)",
  branch: "Branch", class_address: "Class address", notes: "Notes",
};

// Compare what's on screen with what we loaded. Returns only real edits.
function adminDiff() {
  const box = document.getElementById("mode-admin");
  const out = [];
  box.querySelectorAll("[data-af]").forEach((el) => {
    const k = el.dataset.af;
    const now = String(el.value ?? "").trim();
    const was = String(adminOriginal[k] ?? "").trim();
    if (now !== was) out.push({ key: k, label: FIELD_LABELS[k] || k, from: was, to: now });
  });
  return out;
}

// Step 1 of saving: show exactly what will change and ask for the code again.
// Re-entering it is the point — it stops an unlocked laptop from being used to
// silently rewrite a live class.
function saveAdmin() {
  const msg = document.getElementById("admin-msg");
  const changes = adminDiff();

  if (!changes.length) {
    msg.textContent = "No changes to save — nothing is different from the saved class.";
    msg.className = "ma-panel-msg";
    document.getElementById("admin-confirm").hidden = true;
    return;
  }

  // Same refusal the server makes, made here so the admin sees it against the
  // field instead of after typing their code into the confirm box. A date that
  // is ALREADY past is fine to leave alone — only a date being MOVED into the
  // past is refused, which is why this reads adminDiff() and not the raw value.
  const dateChange = changes.find((c) => c.key === "event_date");
  const el = (k) => document.querySelector(`#mode-admin [data-af="${k}"]`);
  const nowStart = (el("start_time") || {}).value || "";
  const nowEnd = (el("end_time") || {}).value || "";
  // A past date is no longer a flat refusal: it is refused UNLESS the admin
  // says this class really happened then. So only the unfixable problems stop
  // us here; the past-date case opens the confirm box with a checkbox on it.
  const movingToPast = dateChange && scheduleError(dateChange.to, "", "") === ERR_PAST_DATE;
  const badSlot = dateChange
    ? (movingToPast ? "" : scheduleError(dateChange.to, nowStart, nowEnd))
    : (nowStart && nowEnd && nowEnd <= nowStart ? ERR_END_BEFORE_START : "");
  if (badSlot) {
    msg.textContent = badSlot;
    msg.className = "ma-panel-msg error";
    document.getElementById("admin-confirm").hidden = true;
    return;
  }
  // ...and moving a FINISHED class forward needs to say what it costs, because
  // the only way back is the checkbox above and an admin who doesn't know that
  // has just made the move permanent.
  const wasPast = dateChange && dateChange.from && dateChange.from < todayISO();
  const movingToFuture = dateChange && !movingToPast;

  msg.textContent = "";
  const box = document.getElementById("admin-confirm");
  box.innerHTML = `
    <p class="ma-confirm-lead">You're about to change <b>${changes.length}
      ${changes.length === 1 ? "field" : "fields"}</b> on this live class:</p>
    <div class="ma-diff">
      ${changes.map((c) => `<div class="ma-diff-row">
         <span class="k">${escHtml(c.label)}</span>
         <span class="v"><span class="from">${escHtml(c.from) || "(empty)"}</span>
           <span class="arr">&rarr;</span>
           <span class="to">${escHtml(c.to) || "(empty)"}</span></span>
       </div>`).join("")}
    </div>
    ${wasPast && movingToFuture ? `<p class="ma-confirm-warn">
      <b>This moves the class out of the archive.</b> Putting it back to a past
      date later needs <em>Restore historical date</em> on this same box.</p>` : ""}
    ${movingToPast ? `<label class="ma-confirm-restore">
      <input type="checkbox" id="admin-restore" />
      <span><b>Restore historical date.</b> Tick this to confirm the class really
        happened on ${escHtml(dateChange.to)}. Without it a past date is refused.</span>
      </label>` : ""}
    <label class="ma-confirm-label" for="admin-pw">Enter the Admin access code to apply these changes</label>
    <div class="ma-confirm-row">
      <input type="password" id="admin-pw" autocomplete="off" placeholder="Access code" />
      <button type="button" class="btn btn-primary" id="admin-confirm-go">Confirm &amp; save</button>
      <button type="button" class="ma-mode-cancel" id="admin-confirm-cancel">Cancel</button>
    </div>
    <p class="ma-panel-msg error" id="admin-confirm-err" hidden></p>`;
  box.hidden = false;

  const pw = document.getElementById("admin-pw");
  pw.focus();
  pw.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); applyAdmin(changes); } };
  document.getElementById("admin-confirm-go").onclick = () => applyAdmin(changes);
  document.getElementById("admin-confirm-cancel").onclick = () => { box.hidden = true; };
}

// Step 2: send ONLY the changed fields, authorised by the code just typed.
async function applyAdmin(changes) {
  const err = document.getElementById("admin-confirm-err");
  const code = document.getElementById("admin-pw").value.trim();
  if (!code) { err.textContent = "Enter the access code."; err.hidden = false; return; }

  const fields = {};
  changes.forEach((c) => { fields[c.key] = c.to; });

  const go = document.getElementById("admin-confirm-go");
  go.disabled = true; go.textContent = "Saving…"; err.hidden = true;
  try {
    const res = await fetch("/api/hub/save-class", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_id: flierEvent, mode: "admin", code, fields,
        // only ever true when the admin ticked the box on this same dialog
        allow_past_restore: !!(document.getElementById("admin-restore") || {}).checked }),
    });
    const data = await res.json();
    if (!data.ok && data.need_code) {
      err.textContent = "That code isn't right. Nothing was changed.";
      err.hidden = false;
      return;
    }
    if (!data.ok) throw new Error(data.error || "Couldn't save.");
    rememberCode("admin", code);              // it was valid — keep the session
    document.getElementById("admin-confirm").hidden = true;
    await loadMode("admin");                  // redraw from the server's truth
    const msg = document.getElementById("admin-msg");
    msg.textContent = "✓ " + data.message;
    msg.className = "ma-panel-msg success";
  } catch (e) {
    err.textContent = e.message; err.hidden = false;
  } finally {
    go.disabled = false; go.textContent = "Confirm & save";
  }
}

// ---------- cancel / reinstate a class ----------
// Same two-pass shape as a field edit: say exactly what will happen, then make
// them re-enter the code. Cancelling is reversible, but it takes a live class
// away from dealers, so it never fires on a single click.
function confirmSetActive(isCancelled, registered) {
  const box = document.getElementById("admin-confirm");
  const active = isCancelled;                 // reinstating if it's cancelled now
  const who = registered === 1 ? "1 dealer is" : `${registered} dealers are`;
  box.innerHTML = `
    <p class="ma-confirm-lead">${active
      ? "You're about to <b>reinstate this class</b>."
      : "You're about to <b>cancel this class</b>."}</p>
    <div class="ma-diff">
      <div class="ma-diff-row"><span class="k">Dealers</span><span class="v">${active
        ? "see it again and can register"
        : "stop seeing it — no new registrations"}</span></div>
      <div class="ma-diff-row"><span class="k">Reminder emails</span><span class="v">${active
        ? "resume" : "stop going out"}</span></div>
      <div class="ma-diff-row"><span class="k">Who's registered</span><span class="v">${
        registered ? `${who} registered — kept, not deleted` : "nobody registered yet"}</span></div>
    </div>
    ${!active && registered
      ? `<p class="ma-confirm-lead">Cancelling does <b>not</b> email anyone. Tell
           the ${registered === 1 ? "dealer" : "dealers"} below yourself.</p>` : ""}
    <label class="ma-confirm-label" for="active-pw">Enter the Admin access code to
      ${active ? "reinstate" : "cancel"} this class</label>
    <div class="ma-confirm-row">
      <input type="password" id="active-pw" autocomplete="off" placeholder="Access code" />
      <button type="button" class="btn ${active ? "btn-primary" : "btn-danger"}"
              id="active-go">${active ? "Confirm & reinstate" : "Confirm & cancel"}</button>
      <button type="button" class="ma-mode-cancel" id="active-back">Never mind</button>
    </div>
    <p class="ma-panel-msg error" id="active-err" hidden></p>`;
  box.hidden = false;

  const pw = document.getElementById("active-pw");
  pw.focus();
  pw.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); applySetActive(active); } };
  document.getElementById("active-go").onclick = () => applySetActive(active);
  document.getElementById("active-back").onclick = () => { box.hidden = true; };
}

async function applySetActive(active) {
  const err = document.getElementById("active-err");
  const code = document.getElementById("active-pw").value.trim();
  if (!code) { err.textContent = "Enter the access code."; err.hidden = false; return; }

  const go = document.getElementById("active-go");
  const label = go.textContent;
  go.disabled = true; go.textContent = "Working…"; err.hidden = true;
  try {
    const res = await fetch("/api/hub/set-active", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_id: flierEvent, mode: "admin", code, active }),
    });
    const data = await res.json();
    if (!data.ok && data.need_code) {
      err.textContent = "That code isn't right. Nothing was changed.";
      err.hidden = false;
      return;
    }
    if (!data.ok) throw new Error(data.error || "Couldn't update the class.");
    rememberCode("admin", code);
    document.getElementById("admin-confirm").hidden = true;
    await loadMode("admin");                  // redraw — banner and button flip
    const msg = document.getElementById("admin-msg");
    msg.textContent = "✓ " + data.message;
    msg.className = "ma-panel-msg success";
  } catch (e) {
    err.textContent = e.message; err.hidden = false;
  } finally {
    go.disabled = false; go.textContent = label;
  }
}

// ---------- email the reminder now ----------
// Sends the same "class is coming up" mail the 7/3/1-day schedule would send,
// but on demand. The server picks the stage nearest today and refuses anyone
// who already heard from us today, so a second click is a no-op, not a second
// email. One confirm is enough — this is reversible in the sense that nothing
// is destroyed, but it does reach real dealers, so it never fires silently.
async function emailReminders() {
  const roster = (modeData.admin && modeData.admin.roster) || [];
  const companies = new Set(roster.map((r) => r.company_name).filter(Boolean));
  const n = companies.size || roster.length;
  if (!n) { alert("Nobody is registered for this class yet."); return; }

  if (!confirm(`Email the "class is coming up" reminder to ${n} registered ` +
               `${n === 1 ? "dealer" : "dealers"} now?\n\n` +
               "Anyone who already got a reminder today is skipped.")) return;

  const btn = document.getElementById("admin-email-remind");
  const msg = document.getElementById("remind-msg");
  const label = btn.innerHTML;
  btn.disabled = true; btn.textContent = "Sending…"; msg.textContent = "";
  try {
    const res = await fetch("/api/hub/email-reminders", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_id: flierEvent, mode: "admin", code: codeFor("admin") }),
    });
    const data = await res.json();
    if (!data.ok && data.need_code) throw new Error("Your session expired — reopen the Admin view.");
    if (!data.ok) throw new Error(data.error || "Couldn't send the reminders.");
    msg.textContent = (data.sent ? "✓ " : "") + data.message;
    msg.className = "ma-panel-msg " + (data.failed && !data.sent ? "error" : "success");
    if (ADMIN_ROWS && Object.keys(ADMIN_ROWS).length) loadAdminRows();
  } catch (e) {
    msg.textContent = e.message; msg.className = "ma-panel-msg error";
  } finally {
    btn.disabled = false; btn.innerHTML = label;
  }
}

// ---------- reminder letters ----------
// One PDF per student, opened in its own tab. Popup blockers stop a burst of
// window.open() calls, so every letter is also listed as a link.
async function generateReminders() {
  const roster = (modeData.admin && modeData.admin.roster) || [];
  const marked = roster.filter((r) => r.attended !== null);
  const targets = marked.length ? roster.filter((r) => r.attended === 1) : roster;
  const n = targets.length;
  if (!n) { alert("Nobody is registered for this class yet."); return; }

  const who = n === 1 ? "1 student" : `${n} students`;
  // 1) are you sure
  if (!confirm(`Send reminders to ${who}?`)) return;
  // 2) and you know what happens next
  if (!confirm(`This will download ${n} PDF${n === 1 ? "" : "s"} — one letter per student.\n\nContinue?`)) return;

  const btn = document.getElementById("admin-remind");
  const msg = document.getElementById("remind-msg");
  btn.disabled = true; btn.textContent = "Sending…"; msg.textContent = "";

  try {
    const res = await fetch("/api/hub/reminders", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_id: flierEvent, mode: "admin",
                             code: codeFor("admin"), only_attending: true }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Couldn’t generate letters.");

    // Downloads, not tabs: a download isn't a popup, so nothing gets blocked
    // and staff ends up with N files instead of N windows to close.
    data.letters.forEach((l, i) => {
      setTimeout(() => {
        const a = document.createElement("a");
        a.href = l.url;
        a.download = `Reminder-${l.name}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
      }, i * 250);          // stagger: browsers drop a burst of simultaneous downloads
    });

    msg.textContent = "✓ " + data.message;
    msg.className = "ma-panel-msg success";
    if (ADMIN_ROWS && Object.keys(ADMIN_ROWS).length) loadAdminRows();
  } catch (e) {
    msg.textContent = e.message; msg.className = "ma-panel-msg error";
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span aria-hidden="true">✉️</span> Send reminders (PDF)';
  }
}

// ---------- FSR view ----------
function renderFSR(d) {
  const box = document.getElementById("mode-fsr");
  const ev = d.event, s = d.seats, st = d.status;
  const roster = d.roster;
  const locked = st.grading === "graded";
  const closed = st.closed_at;

  // Grading opens only once the class has happened — same rule the Admin Hub
  // grade sheet used. Today = live roster, upcoming = preview.
  const gate = {
    past:     "",
    today:    "This class is running today — live roster. Grading opens once the class day is over.",
    upcoming: "Upcoming class — roster preview. Grading opens after class day.",
  }[st.timing];

  box.innerHTML = `
    <div class="ma-panel-head is-fsr">
      <h2>FSR — ${escHtml(ev.topic)}</h2>
      <p>${escHtml(ev.weekday_display)}, ${escHtml(ev.date_display)} &middot; ${escHtml(ev.time_display)} &middot;
         ${escHtml(ev.class_address || ev.event_location)}</p>
    </div>
    <div class="ma-fsr-stats">
      <div><b>${s.taken}</b><span>students</span></div>
      <div><b>${st.graded_count}</b><span>graded</span></div>
      <div><b>${Math.max(0, st.graded_total - st.graded_count)}</b><span>to grade</span></div>
      <div><b>${escHtml(ev.trainer) || "\u2014"}</b><span>trainer</span></div>
      <div><b class="fsr-state ${st.grading}">${
        st.grading === "graded" ? "Complete" :
        st.grading === "needs_grading" ? "Needs grading" : statusWord(st.timing)}</b><span>status</span></div>
    </div>
    ${ev.notes ? `<p class="ma-card-note">${escHtml(ev.notes)}</p>` : ""}
    ${gate ? `<p class="ma-gate-note">${gate}</p>` : ""}

    <h3 class="ma-panel-sub">${st.can_grade ? "Grade sheet" : "Roster"}</h3>
    ${closed ? `<p class="ma-gate-note">This class is closed &mdash; grades are final.
      Reopen it below to change anything.</p>` : ""}
    ${st.can_grade && !closed ? `<div class="ma-bulk">
      <span>Mark everyone:</span>
      <button type="button" class="ma-bulk-btn" data-bulk="1">Here</button>
      <button type="button" class="ma-bulk-btn" data-bulk="0">No-show</button>
      <button type="button" class="ma-bulk-btn is-clear" data-bulk="">Clear</button>
    </div>` : ""}
    ${roster.length
      ? rosterTable(roster, st.can_grade && !closed)
      : '<p class="ma-empty">Nobody is registered for this class yet.</p>'}

    ${st.can_grade ? `
    <div class="ma-steps-box">
      <p class="ma-steps-title">Close out this class &mdash; 2 steps</p>

      <div class="ma-step">
        <button type="button" class="btn btn-primary" id="fsr-save"${
          (locked || closed) ? " disabled" : ""}>
          ${closed ? "Closed \u2014 reopen to edit"
            : locked ? "Class info submitted \u2014 locked" : "1. Submit class info"}</button>
        <p class="ma-step-note" id="fsr-save-note">${closed
          ? "The class is closed. Reopen it to change a grade."
          : locked
          ? "Attendance and grades are saved and locked. Change any grade below to re-submit."
          : "Mark who was here, add pass/fail and scores, then submit."}</p>
      </div>

      <div class="ma-step">
        <button type="button" class="btn btn-primary" id="fsr-close"${(!locked || closed) ? " disabled" : ""}>
          ${closed ? "Class closed" : "2. Close class"}</button>
        <p class="ma-step-note">${closed
          ? `Closed ${escHtml(closed)}. Attendance and grades are final.`
          : locked
          ? "Locks attendance, pass/fail and scores as final. This is the last step."
          : "Unlocks after step 1."}</p>
        ${closed ? `<button type="button" class="ma-linkbtn" id="fsr-reopen">Reopen to fix a grade</button>` : ""}
      </div>

      <p class="ma-panel-msg" id="fsr-msg"></p>
      <div id="fsr-sent"></div>
    </div>` : ""}`;

  if (st.can_grade) {
    // Bulk marking is what a checkbox grid was really for — 18 students and
    // two of them missing. It stays EXPLICIT: the trainer chooses "everyone
    // here", it is never what happens by not choosing.
    box.querySelectorAll("[data-bulk]").forEach((b) => {
      b.onclick = () => {
        box.querySelectorAll(".g-att").forEach((sel) => { sel.value = b.dataset.bulk; });
        unlockResubmit();
      };
    });
    document.getElementById("fsr-save").onclick = saveGrades;
    const closeBtn = document.getElementById("fsr-close");
    if (closeBtn) closeBtn.onclick = closeClass;
    const reopen = document.getElementById("fsr-reopen");
    if (reopen) reopen.onclick = reopenClass;
    // editing a locked sheet re-arms Submit, exactly like the old grade sheet
    box.querySelectorAll(".g-att, .g-score, .g-pass, .g-note").forEach((el) => {
      el.addEventListener("input", unlockResubmit);
      el.addEventListener("change", unlockResubmit);
    });
  }
}

function statusWord(t) { return t === "today" ? "Running today" : "Upcoming"; }

function unlockResubmit() {
  const b = document.getElementById("fsr-save");
  if (!b || !b.disabled) return;
  b.disabled = false;
  b.textContent = "Re-submit updated grades";
  document.getElementById("fsr-save-note").textContent =
    "You changed a grade \u2014 submit again to save and re-lock the class.";
}

async function closeClass() {
  await fsrAction("/api/hub/close-class", "fsr-close", "2. Close class");
}
async function reopenClass() {
  await fsrAction("/api/hub/reopen-class", "fsr-reopen", "Reopen to fix a grade");
}

async function fsrAction(url, btnId, label) {
  const btn = document.getElementById(btnId);
  const msg = document.getElementById("fsr-msg");
  btn.disabled = true; btn.textContent = "Working\u2026"; msg.textContent = "";
  try {
    const res = await fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_id: flierEvent, mode: "fsr", code: codeFor("fsr") }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "That didn\u2019t work.");
    await loadMode("fsr");
    const m = document.getElementById("fsr-msg");
    m.textContent = "\u2713 " + data.message; m.className = "ma-panel-msg success";
  } catch (e) {
    msg.textContent = e.message; msg.className = "ma-panel-msg error";
    btn.disabled = false; btn.textContent = label;
  }
}

function rosterTable(roster, gradable) {
  if (!roster.length) return '<p class="ma-empty">Nobody is registered yet.</p>';
  const head = gradable
    ? "<th>Student</th><th>Company</th><th>Branch</th><th>Here?</th><th>Pass / Fail</th><th>Score</th><th>Note</th>"
    : "<th>Student</th><th>Company</th><th>Contact</th><th>Result</th>";
  const pf = (v) => `<select class="g-pass">
      <option value=""${v == null ? " selected" : ""}>&mdash;</option>
      <option value="1"${v === 1 ? " selected" : ""}>Pass</option>
      <option value="0"${v === 0 ? " selected" : ""}>Fail</option>
    </select>`;
  return `<div class="ma-table-wrap"><table class="ma-roster"><thead><tr>${head}</tr></thead><tbody>
    ${roster.map((r) => gradable ? `
      <tr data-aid="${r.attendee_id}">
        <td data-label="Student"><b>${escHtml(r.name)}</b>${r.role ? `<small>${escHtml(r.role)}</small>` : ""}</td>
        <td data-label="Company">${escHtml(r.company_name)}</td>
        <td data-label="Branch">${escHtml(r.branch)}</td>
        <td data-label="Here?"><select class="g-att">
          <option value=""${r.attended === null ? " selected" : ""}>&mdash;</option>
          <option value="1"${r.attended === 1 ? " selected" : ""}>Here</option>
          <option value="0"${r.attended === 0 ? " selected" : ""}>No-show</option>
        </select></td>
        <td data-label="Pass/Fail">${pf(r.passed)}</td>
        <td data-label="Score"><input type="number" class="g-score" min="0" max="100" value="${r.score === null ? "" : r.score}" placeholder="&mdash;" /></td>
        <td data-label="Note"><input type="text" class="g-note" value="${escHtml(r.comment)}" placeholder="optional" /></td>
      </tr>` : `
      <tr>
        <td data-label="Student"><b>${escHtml(r.name)}</b>${r.role ? `<small>${escHtml(r.role)}</small>` : ""}</td>
        <td data-label="Company">${escHtml(r.company_name)}</td>
        <td data-label="Contact">${escHtml(r.contact_email)}</td>
        <td data-label="Result">${resultTag(r)}</td>
      </tr>`).join("")}
  </tbody></table></div>`;
}

function resultTag(r) {
  if (r.attended === null) return '<span class="ma-pill">not graded</span>';
  if (r.attended === 0) return '<span class="ma-pill no">no show</span>';
  if (r.score === null) return '<span class="ma-pill ok">attended</span>';
  return `<span class="ma-pill ${r.passed ? "ok" : "no"}">${r.passed ? "passed" : "failed"} · ${r.score}</span>`;
}

async function saveGrades() {
  const rows = Array.from(document.querySelectorAll("#mode-fsr tr[data-aid]"));
  // Attendance is a THREE-state choice — "—" / Here / No-show — not a checkbox.
  // A checkbox has no way to say "I haven't decided": an untouched one reads
  // false, which the server took as "absent", so opening a grade sheet and
  // pressing Submit used to mark the whole class a no-show and report the
  // class fully graded. "" means untouched and leaves the student ungraded.
  const grades = rows.map((tr) => {
    const pass = tr.querySelector(".g-pass");
    return {
      attendee_id: Number(tr.dataset.aid),
      attended: tr.querySelector(".g-att").value,   // "" | "1" | "0"
      passed: pass && pass.value !== "" ? Number(pass.value) : null,
      score: tr.querySelector(".g-score").value,
      comment: tr.querySelector(".g-note").value,
    };
  });
  // Nothing decided yet? Then there is nothing to submit, and saying so beats
  // writing a sheet full of blanks and calling the class graded.
  if (grades.length && grades.every((g) => g.attended === "")) {
    const m = document.getElementById("fsr-msg");
    m.textContent = "Mark who was here first — nobody has been marked yet.";
    m.className = "ma-panel-msg error";
    return;
  }
  const msg = document.getElementById("fsr-msg");
  const btn = document.getElementById("fsr-save");
  btn.disabled = true; btn.textContent = "Saving\u2026"; msg.textContent = "";
  try {
    const res = await fetch("/api/hub/grade", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_id: flierEvent, mode: "fsr", code: codeFor("fsr"),
                             graded_by: "FSR", grades }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Couldn\u2019t save grades.");
    await loadMode("fsr");                       // redraw from the server's truth
    const m = document.getElementById("fsr-msg");
    m.textContent = "\u2713 " + data.message; m.className = "ma-panel-msg success";
  } catch (e) {
    msg.textContent = e.message; msg.className = "ma-panel-msg error";
    btn.disabled = false; btn.textContent = "1. Submit class info";
  }
}

// ---------- Print roster ----------
// Built from the roster already loaded for the active mode. Nothing is fetched
// and no student data ever rides in a URL — the sheet is composed in-page and
// handed to a new window for printing.
function printRoster() {
  const d = modeData[currentMode];
  if (!d || !d.roster) { alert("Open Admin or FSR first — the roster loads with it."); return; }
  const ev = d.event, roster = d.roster;
  const when = `${ev.weekday_display}, ${ev.date_display} · ${ev.time_display}`;
  const where = ev.class_address || ev.event_location || "";

  const rows = roster.length
    ? roster.map((r, i) => `<tr>
        <td class="n">${i + 1}</td>
        <td><b>${escHtml(r.name)}</b></td>
        <td>${escHtml(r.company_name)}</td>
        <td>${escHtml(r.role)}</td>
        <td class="sig"></td>
      </tr>`).join("")
    : `<tr><td colspan="5" class="empty">No one is registered for this class yet.</td></tr>`;

  // a few blank lines so walk-ins can be added by hand on the printed sheet
  const spare = roster.length
    ? Array.from({ length: 4 }, (_, i) => `<tr class="spare">
        <td class="n">${roster.length + i + 1}</td><td></td><td></td><td></td><td class="sig"></td>
      </tr>`).join("")
    : "";

  const doc = `<!doctype html><html lang="en"><head><meta charset="utf-8" />
<title>Roster — ${escHtml(ev.topic)} — ${escHtml(ev.date_display)}</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,system-ui,sans-serif;color:#16222f;padding:26px}
  .hd{border-bottom:3px solid #1d6fc2;padding-bottom:12px;margin-bottom:6px}
  .eyebrow{font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:#1d6fc2;font-weight:700}
  h1{font-size:1.45rem;text-transform:uppercase;color:#0a2540;margin:4px 0 6px}
  .meta{color:#56697a;font-size:.95rem;line-height:1.5}
  .meta b{color:#16222f}
  .counts{display:flex;gap:26px;margin:14px 0 18px;font-size:.85rem;color:#56697a}
  .counts b{display:block;font-size:1.5rem;color:#0a2540;line-height:1.1}
  table{width:100%;border-collapse:collapse}
  th{font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;color:#56697a;text-align:left;
     padding:8px 10px;background:#f3f7fb;border:1px solid #d9e2ec}
  td{padding:11px 10px;border:1px solid #d9e2ec;font-size:.92rem;vertical-align:middle}
  td.n{width:34px;text-align:center;color:#8fa3b5;font-weight:700}
  td.sig{width:210px}
  tr.spare td{height:38px;background:#fcfdfe}
  .empty{text-align:center;color:#8fa3b5;padding:26px}
  .ft{margin-top:16px;display:flex;justify-content:space-between;gap:20px;font-size:.8rem;color:#56697a}
  .btn{background:#1d6fc2;color:#fff;border:0;padding:9px 18px;font-size:.92rem;cursor:pointer;margin-top:16px}
  @page{margin:0}
  @media print{body{padding:12mm}.btn{display:none}thead{display:table-header-group}tr{break-inside:avoid}}
</style></head><body>
  <div class="hd">
    <p class="eyebrow">M&amp;A Supply &middot; Class Roster</p>
    <h1>${escHtml(ev.topic)}</h1>
    <p class="meta"><b>${escHtml(when)}</b><br />${escHtml(where)}${
      ev.trainer ? ` &middot; Trainer: ${escHtml(ev.trainer)}` : ""}</p>
  </div>
  <div class="counts">
    <span><b>${d.seats ? d.seats.taken : roster.length}</b>registered</span>
    <span><b>${d.seats && d.seats.capacity ? d.seats.capacity : "—"}</b>capacity</span>
    <span><b>${new Set(roster.map((r) => r.company_name)).size}</b>companies</span>
  </div>
  <table>
    <thead><tr><th></th><th>Student</th><th>Company</th><th>Role</th><th>Signature</th></tr></thead>
    <tbody>${rows}${spare}</tbody>
  </table>
  <div class="ft"><span>Printed from the M&amp;A Training Hub</span>
    <span>Trainer signature: ______________________</span></div>
  <button class="btn" onclick="window.print()">Print / Save as PDF</button>
</body></html>`;

  const w = window.open("", "_blank");
  if (!w) { alert("Allow pop-ups for this site to print the roster."); return; }
  w.document.write(doc);
  w.document.close();
}

function escHtml(s) {
  return String(s == null ? "" : s)
    .replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// ---------- boot ----------
const eventId = (new URLSearchParams(location.search).get("event") || "").trim();
if (!eventId) {
  showIndex();
} else {
  gate.hidden = true;        // class link: never show the "Training classes" band
  // ADMIN-VIEW belongs to the master class list only. On a class page the three
  // mode buttons are the way in, and two "admin" entry points read as a conflict.
  const av = document.getElementById("admin-view-btn");
  if (av) av.hidden = true;
  const fv = document.getElementById("fsr-view-btn");
  if (fv) fv.hidden = true;
  // ?view=fsr is how the grading queue hands a class over: land straight in the
  // FSR lens instead of making them find the code prompt again. The code is
  // still checked server-side — the parameter asks, it does not authorise.
  const wanted = (new URLSearchParams(location.search).get("view") || "").trim().toLowerCase();
  loadEvent(eventId).then(() => {
    if (wanted === "fsr" || wanted === "admin") requestMode(wanted);
  });
}

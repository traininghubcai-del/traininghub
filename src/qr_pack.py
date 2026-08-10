"""Print-friendly QR sheet: active classes with details + a QR + the register link.

John opens /qr-pack and does Print -> Save as PDF. Pass only_id for a single-class
flyer. QRs encode whatever host the page was opened on, so once hosted at a real
domain the printed codes point there automatically.
"""
import segno

from src.catalog import public_events


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def qr_pack_html(base_url, only_id=None, only_ids=None):
    events = public_events()
    if only_id:
        events = [e for e in events if e["event_id"] == only_id]
    elif only_ids:
        # The index page sends the ids exactly as the user filtered and sorted
        # them, so we keep that order — the printed sheet matches the screen.
        by_id = {e["event_id"]: e for e in events}
        events = [by_id[i] for i in only_ids if i in by_id]
    else:
        # No selection: date order, the same default the index page shows
        # (public_events sorts by event_id, which reads location-first).
        events = sorted(events, key=lambda e: (e.get("event_date") or "", e["event_id"]))
    single = events[0] if (only_id and events) else None

    # A single class with a custom flier prints as TWO pages: the vendor artwork
    # alone on page 1, the QR + details on page 2. Sized to fit one sheet exactly
    # so "print page 1 only" gives a clean flier with nothing else on it.
    flier_page = ""
    flier_note = ""
    if single:
        from src.fliers import get_flier
        f = get_flier(single["event_id"])
        if f.get("has_flier"):
            if f.get("is_pdf"):
                # a PDF can't be inlined into this print sheet — point at it instead
                flier_note = (f'<p class="qp-flier-note">📄 This class has a custom flier '
                              f'(PDF): <span>{_esc(base_url)}{_esc(f["url"])}</span></p>')
            else:
                flier_page = (f'  <section class="qp-flier-page">\n'
                              f'    <img class="qp-flier-img" src="{_esc(f["url"])}" '
                              f'alt="Flier for {_esc(single["topic"])}" />\n'
                              f'  </section>')
    title = (f"{single['topic']} — {single['date_display']} — Register"
             if single else "M&A Supply — Training Registration QR Codes")
    cards = []
    for ev in events:
        url = f"{base_url}/?event={ev['event_id']}"
        qr_uri = segno.make(url, error="m").svg_data_uri(scale=4, border=2, dark="#0a2540")
        cards.append(f"""    <article class="qp-card">
      <img class="qp-qr" src="{qr_uri}" alt="QR code to register for {_esc(ev['topic'])}" />
      <img class="qp-logo" src="/static/logos/ma-logo-stacked.png?v=4" alt="M&amp;A Supply Company Inc." />
      <div class="qp-info">
        <p class="qp-region">{_esc(ev['region'])} &middot; {_esc(ev['event_location'])}</p>
        <h2 class="qp-topic">{_esc(ev['topic'])}</h2>
        <p class="qp-when">{_esc(ev['weekday_display'])}, {_esc(ev['date_display'])} &middot; {_esc(ev['time_display'])}</p>
        <p class="qp-host">{_esc(ev['host_label'])}</p>
        <p class="qp-scan">Scan to register &mdash; or go to:</p>
        <p class="qp-url">{_esc(url)}</p>
      </div>
    </article>""")
    if single:
        # single-class flyer: the workflow block the TM hands out — everything a
        # dealer needs to know on one printed page
        cards.append("""    <section class="qp-flyer">
      <p class="qp-free">★ FREE EVENT ★</p>
      <p class="qp-big">HANDS-ON TRAINING <span>·</span> LUNCH ON US</p>
      <div class="qp-chips">
        <span>🛠 REAL EQUIPMENT</span><span>🏅 EARN BADGES L1→L3</span>
        <span>🎁 REWARDS &amp; MASTER CLASSES</span><span>📈 FEWER CALLBACKS</span>
      </div>
      <ol class="qp-steps">
        <li><b>SCAN &amp; REGISTER</b> — under a minute</li>
        <li><b>SHOW UP</b> — lunch is counted on your seat</li>
        <li><b>DO THE QUIZZES</b> — end of class + Day 1 · 7 · 30 · 90 → badges &amp; rewards</li>
      </ol>
      <p class="qp-note">✋ <b>Confirming or dropping out: 48–24 hrs notice required.</b>
         We'll notify you about your seat — please make sure your <b>email and phone are
         correct</b> when you register.</p>
      <p class="qp-cta">SEATS ARE LIMITED — REGISTER NOW</p>
    </section>""")
    if flier_note:
        cards.append(f"    {flier_note}")
    if cards:
        body = "\n".join(cards)
    elif only_id:
        body = "<p>This class link is not active.</p>"
    elif only_ids:
        body = "<p>None of the selected classes are active.</p>"
    else:
        body = "<p>No active classes in the catalog.</p>"
    heading = _esc(single["topic"]) if single else "M&amp;A Supply — Training Registration"
    if single:
        hint = "Scan the QR code below to register for this class."
    elif only_ids:
        n = len(events)
        hint = f"{n} selected {'class' if n == 1 else 'classes'} — scan a QR code to register."
    else:
        hint = "Scan a class's QR code to register."
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{_esc(title)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, system-ui, sans-serif; color: #16222f; margin: 0; padding: 28px; background: #fff; }}
  .qp-head {{ border-bottom: 3px solid #1d6fc2; padding-bottom: 14px; margin-bottom: 22px; }}
  .qp-head h1 {{ font-size: 1.5rem; margin: 0 0 6px; color: #0a2540; text-transform: uppercase; }}
  .qp-head p {{ margin: 0; color: #56697a; }}
  .qp-print {{ background: #1d6fc2; color: #fff; border: 0; border-radius: 4px; padding: 8px 16px; font-size: 0.95rem; cursor: pointer; margin-left: 8px; }}
  .qp-card {{ display: flex; gap: 22px; align-items: center; border: 1px solid #d9e2ec; border-left: 6px solid #1d6fc2; border-radius: 6px; padding: 20px; margin-bottom: 16px; page-break-inside: avoid; }}
  .qp-qr {{ width: 150px; height: 150px; flex: none; }}
  .qp-logo {{ height: 110px; flex: none; }}
  .qp-flyer {{ border: 3px solid #0a2540; border-radius: 10px; padding: 20px 26px; margin-top: 8px; text-align: center; page-break-inside: avoid; }}
  .qp-free {{ margin: 0 0 6px; font-size: 1.05rem; font-weight: 900; letter-spacing: 0.35em; color: #0a2540; }}
  .qp-big {{ margin: 0; font-size: 1.7rem; font-weight: 900; color: #0a2540; letter-spacing: 0.02em; }}
  .qp-big span {{ color: #0a2540; }}
  .qp-chips {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; max-width: 540px; margin: 16px auto; }}
  .qp-chips span {{ border: 2px solid #0a2540; border-radius: 8px; padding: 11px 10px; font-weight: 800; font-size: 0.95rem; color: #0a2540; text-align: center; }}
  .qp-steps {{ list-style: none; margin: 18px auto 0; padding: 0; max-width: 540px; counter-reset: st; text-align: left; }}
  .qp-steps li {{ counter-increment: st; font-size: 1.15rem; line-height: 1.5; display: flex; align-items: center; gap: 16px; padding: 16px 0; border-bottom: 1.5px solid #d9e2ec; }}
  .qp-steps li:last-child {{ border-bottom: none; }}
  .qp-steps li::before {{ content: counter(st); flex: none; width: 46px; height: 46px; border-radius: 50%; background: #0a2540; color: #fff; font-weight: 900; font-size: 1.5rem; text-align: center; line-height: 46px; }}
  .qp-steps b {{ color: #0a2540; }}
  .qp-note {{ margin: 16px auto 0; max-width: 540px; text-align: left; font-size: 0.95rem; border: 1.5px dashed #0a2540; border-radius: 8px; padding: 10px 14px; }}
  .qp-cta {{ margin: 14px 0 0; font-size: 0.95rem; font-weight: 800; color: #0a2540; letter-spacing: 0.08em; border-top: 1.5px solid #0a2540; padding-top: 10px; }}
  .qp-region {{ font-size: 0.8rem; letter-spacing: 0.08em; text-transform: uppercase; color: #1d6fc2; font-weight: 700; margin: 0 0 4px; }}
  .qp-topic {{ font-size: 1.3rem; margin: 0 0 6px; color: #0a2540; text-transform: uppercase; }}
  .qp-when {{ margin: 0 0 4px; font-weight: 600; }}
  .qp-host {{ margin: 0 0 12px; color: #56697a; }}
  .qp-scan {{ margin: 0; font-size: 0.85rem; color: #56697a; }}
  .qp-url {{ margin: 2px 0 0; font-family: ui-monospace, monospace; font-size: 0.9rem; color: #155a9f; word-break: break-all; }}
  /* page 1: the custom flier, alone. max-height keeps it on ONE sheet (letter
     279mm / A4 297mm, minus the 12mm print padding top and bottom). */
  .qp-flier-page {{ text-align: center; margin-bottom: 26px; }}
  .qp-flier-img {{ display: block; margin: 0 auto; max-width: 100%; max-height: 245mm;
    object-fit: contain; border: 1px solid #d9e2ec; }}
  .qp-flier-note {{ border: 1.5px dashed #1d6fc2; border-radius: 8px; padding: 12px 16px;
    margin: 16px 0 0; font-size: 0.92rem; color: #0a2540; }}
  .qp-flier-note span {{ font-family: ui-monospace, monospace; color: #155a9f; word-break: break-all; }}
  @page {{ margin: 0; }}  /* zero page margin = browser drops its date/URL header & footer */
  @media print {{
    body {{ padding: 12mm; }}
    .qp-print, .qp-hint, .qp-screen-only {{ display: none; }}
    .qp-card {{ break-inside: avoid; }}
    /* the flier owns page 1 outright; everything else starts on page 2 */
    .qp-flier-page {{ break-after: page; page-break-after: always; margin-bottom: 0; }}
    .qp-flier-img {{ border: none; }}
  }}
</style></head>
<body>
{flier_page}
  <header class="qp-head">
    <h1>{heading}</h1>
    <p class="qp-hint">{hint}
      <button class="qp-print" onclick="window.print()">Print / Save as PDF</button></p>
  </header>
{body}
</body></html>"""

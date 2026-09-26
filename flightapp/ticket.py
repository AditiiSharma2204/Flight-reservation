"""E-ticket HTML, used inside the app and as a downloadable, printable file."""

import datetime as dt
from html import escape

from .core import CABINS, CITIES, clock, duration_text, money

TICKET_CSS = """
.ticket { font-family: 'Segoe UI', system-ui, sans-serif; color: #0f172a; max-width: 760px;
          border-radius: 18px; overflow: hidden; border: 1px solid #dbeafe;
          box-shadow: 0 10px 30px rgba(30, 64, 175, .12); background: #fff; margin: 0 auto; }
.ticket-head { background: linear-gradient(115deg, #1e3a8a, #2563eb 60%, #38bdf8);
               color: #fff; padding: 18px 24px; display: flex; justify-content: space-between;
               align-items: center; }
.ticket-head .brand { font-size: 1.15rem; font-weight: 700; letter-spacing: .3px; }
.ticket-head .pnr { text-align: right; }
.ticket-head .pnr small { display: block; opacity: .8; font-size: .72rem; letter-spacing: 1px; }
.ticket-head .pnr b { font-size: 1.5rem; letter-spacing: 3px; }
.status { display: inline-block; margin-top: 4px; padding: 1px 10px; border-radius: 999px;
          font-size: .72rem; font-weight: 700; background: #dcfce7; color: #166534; }
.status.cancelled { background: #fee2e2; color: #991b1b; }
.leg { display: grid; grid-template-columns: 1fr auto 1fr; gap: 12px; align-items: center;
       padding: 18px 24px; border-bottom: 1px dashed #cbd5e1; }
.leg .label { grid-column: 1 / -1; font-size: .72rem; font-weight: 700; color: #2563eb;
              letter-spacing: 1px; text-transform: uppercase; }
.end .code { font-size: 1.9rem; font-weight: 800; line-height: 1; }
.end .time { font-size: 1.05rem; font-weight: 600; margin-top: 4px; }
.end .city { font-size: .8rem; color: #64748b; }
.end.right { text-align: right; }
.mid { text-align: center; color: #64748b; font-size: .78rem; min-width: 150px; }
.mid .line { border-top: 2px dotted #93c5fd; margin: 6px 0; position: relative; }
.mid .plane { color: #2563eb; font-size: 1.1rem; }
.info { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px;
        padding: 16px 24px; background: #f8fafc; }
.info small { display: block; color: #64748b; font-size: .72rem; text-transform: uppercase;
              letter-spacing: .6px; }
.info span { font-weight: 600; }
.pax { padding: 12px 24px 18px; }
.pax table { width: 100%; border-collapse: collapse; font-size: .9rem; }
.pax th { text-align: left; color: #64748b; font-weight: 600; font-size: .72rem;
          text-transform: uppercase; letter-spacing: .6px; padding: 6px 0; }
.pax td { padding: 6px 0; border-top: 1px solid #e2e8f0; }
.foot { padding: 12px 24px; font-size: .75rem; color: #64748b; background: #f8fafc; }
"""


def _date(iso):
    return dt.date.fromisoformat(iso).strftime("%a, %d %b %Y")


def _leg(label, f):
    arrive = clock(f.arrive_min) + (" <sup>+1</sup>" if f.next_day else "")
    return f"""
    <div class="leg">
      <div class="label">{label} · {_date(f.date)} · {escape(f.airline)} {escape(f.number)}</div>
      <div class="end"><div class="code">{f.origin}</div><div class="time">{clock(f.depart_min)}</div>
        <div class="city">{CITIES[f.origin][0]}</div></div>
      <div class="mid"><span class="plane">✈</span><div class="line"></div>{duration_text(f.duration_min)} · Non-stop</div>
      <div class="end right"><div class="code">{f.destination}</div><div class="time">{arrive}</div>
        <div class="city">{CITIES[f.destination][0]}</div></div>
    </div>"""


def ticket_html(booking):
    flights = booking.flight_objects()
    cancelled = booking.status != "CONFIRMED"
    legs = "".join(_leg(label, f) for label, f in zip(["Outbound", "Return"], flights))
    rows = "".join(
        f"<tr><td>{i}</td><td>{escape(t['first'])} {escape(t['last'])}</td><td>{booking.cabin}</td></tr>"
        for i, t in enumerate(booking.travellers, 1)
    )
    return f"""
<div class="ticket">
  <div class="ticket-head">
    <div><div class="brand">✈ SkyWay · E-Ticket</div>
      <span class="status {'cancelled' if cancelled else ''}">{escape(booking.status)}</span></div>
    <div class="pnr"><small>PNR</small><b>{escape(booking.pnr)}</b></div>
  </div>
  {legs}
  <div class="info">
    <div><small>Class</small><span>{booking.cabin}</span></div>
    <div><small>Baggage</small><span>{CABINS[booking.cabin]['baggage']}</span></div>
    <div><small>Total paid</small><span>{money(booking.fare['total'])}</span></div>
    <div><small>Payment</small><span>{escape(booking.payment)}</span></div>
  </div>
  <div class="pax"><table><tr><th>#</th><th>Passenger</th><th>Class</th></tr>{rows}</table></div>
  <div class="foot">Contact: {escape(booking.mobile)}{' · ' + escape(booking.email) if booking.email else ''} ·
    Booked on {_date(booking.booked_on)} · Carry a government photo ID. Check-in closes 45 minutes before departure.</div>
</div>"""


def ticket_document(booking):
    """Standalone HTML file for download / printing."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>E-ticket {escape(booking.pnr)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body {{ background: #eff6ff; padding: 32px 16px; margin: 0; }} {TICKET_CSS}
@media print {{ body {{ background: #fff; padding: 0; }} .ticket {{ box-shadow: none; }} }}</style>
</head><body>{ticket_html(booking)}</body></html>"""

"""SkyWay - flight reservation web app (Streamlit).

Run with:  streamlit run streamlit_app.py
"""

import datetime as dt

import streamlit as st

from flightapp import store
from flightapp.core import (
    CABINS,
    CITIES,
    MAX_TRAVELLERS,
    Booking,
    Flight,
    cancellation_quote,
    city_label,
    clean_mobile,
    clean_name,
    clock,
    duration_text,
    fare_breakdown,
    last_bookable_day,
    luhn_valid,
    money,
    new_pnr,
    search_flights,
    today,
    valid_cvv,
    valid_email,
    valid_expiry,
    valid_upi,
)
from flightapp.ticket import TICKET_CSS, ticket_document, ticket_html

st.set_page_config(page_title="SkyWay Flight Booking", page_icon="✈️", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 2rem; max-width: 1200px; }
      .hero { background: linear-gradient(115deg, #1e3a8a 0%, #2563eb 55%, #38bdf8 100%);
              color: #fff; border-radius: 18px; padding: 1.6rem 2rem; margin-bottom: .6rem; }
      .hero h1 { color: #fff; margin: 0; font-size: 2.1rem; }
      .hero p { margin: .3rem 0 0; opacity: .92; }
      .steps { display: flex; gap: .4rem; flex-wrap: wrap; margin: .6rem 0 1rem; }
      .step { padding: .25rem .8rem; border-radius: 999px; font-size: .82rem; font-weight: 600;
              background: #e2e8f0; color: #475569; }
      .step.done { background: #dbeafe; color: #1d4ed8; }
      .step.now { background: #2563eb; color: #fff; }
      .airline { display: flex; align-items: center; gap: .6rem; }
      .logo { width: 38px; height: 38px; border-radius: 10px; color: #fff; font-weight: 800;
              display: flex; align-items: center; justify-content: center; font-size: .85rem; }
      .airline b { display: block; line-height: 1.1; }
      .airline small { color: #64748b; }
      .times { display: flex; align-items: center; gap: .8rem; }
      .times .t { font-size: 1.35rem; font-weight: 700; line-height: 1.1; }
      .times .c { font-size: .78rem; color: #64748b; }
      .times .dur { flex: 1; text-align: center; font-size: .78rem; color: #64748b; min-width: 90px; }
      .times .dur hr { margin: .2rem 0; border: 0; border-top: 2px dotted #93c5fd; }
      .fare { font-size: 1.35rem; font-weight: 800; color: #1e3a8a; line-height: 1.1; }
      .fare small { display: block; font-size: .72rem; font-weight: 500; color: #64748b; }
      .badge { display: inline-block; padding: .05rem .5rem; border-radius: 999px; font-size: .7rem;
               font-weight: 700; margin-right: .3rem; }
      .b-cheap { background: #dcfce7; color: #166534; }
      .b-fast { background: #e0f2fe; color: #075985; }
      .b-seats { background: #fef3c7; color: #92400e; }
      .summary-row { display: flex; justify-content: space-between; margin: .15rem 0; }
      .summary-total { display: flex; justify-content: space-between; font-weight: 800;
                       font-size: 1.15rem; border-top: 1px solid #e2e8f0; margin-top: .4rem; padding-top: .4rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

STEPS = ["Search", "Choose flights", "Passengers", "Payment", "Confirmed"]
state = st.session_state
state.setdefault("step", 0)
state.setdefault("search", None)
state.setdefault("chosen", {})       # leg index -> flight dict
state.setdefault("passengers", None)
state.setdefault("confirmed_pnr", None)


def reset_booking():
    for key in ("search", "passengers", "confirmed_pnr"):
        state[key] = None
    state.chosen = {}
    state.step = 0


def go(step):
    state.step = step


def fmt_date(d):
    return d.strftime("%a, %d %b %Y")


def show_ticket(booking):
    st.html(f"<style>{TICKET_CSS}</style>{ticket_html(booking)}")


# ----------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------

st.markdown(
    """
    <div class="hero">
      <h1>✈️ SkyWay</h1>
      <p>Search flights between 16 Indian cities, compare fares, and book in a few clicks.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption("Demo project - flights, fares and payments are simulated. No real bookings or charges are made.")

tab_book, tab_manage, tab_about = st.tabs(["✈️ Book a flight", "🎫 Manage booking", "ℹ️ About"])

# ----------------------------------------------------------------------
# Book: search
# ----------------------------------------------------------------------


def search_panel():
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 1.3, 1])
        trip = c1.radio("Trip", ["One way", "Round trip"], horizontal=True, key="trip")
        cabin = c2.selectbox("Class", list(CABINS), key="cabin")
        travellers = c3.number_input("Travellers", 1, MAX_TRAVELLERS, 1, key="travellers")

        codes = list(CITIES)
        c1, c2, c3, c4 = st.columns(4)
        origin = c1.selectbox("From", codes, index=codes.index("DEL"), format_func=city_label, key="origin")
        dest = c2.selectbox("To", codes, index=codes.index("BOM"), format_func=city_label, key="dest")
        first, last = today(), last_bookable_day()
        depart = c3.date_input(
            "Departure", value=first + dt.timedelta(days=14), min_value=first, max_value=last, key="depart",
            format="DD/MM/YYYY",
        )
        ret = None
        if trip == "Round trip":
            ret = c4.date_input(
                "Return", value=min(depart + dt.timedelta(days=5), last), min_value=first, max_value=last,
                key="return", format="DD/MM/YYYY",
            )

        if st.button("🔍 Search flights", type="primary", key="search_btn"):
            if origin == dest:
                st.error("Departure and destination cities must be different.")
            elif ret is not None and ret < depart:
                st.error("The return date can't be before the departure date.")
            else:
                state.search = {
                    "origin": origin, "dest": dest, "depart": depart, "ret": ret,
                    "travellers": int(travellers), "cabin": cabin,
                }
                state.chosen = {}
                go(1)
                st.rerun()


def legs():
    s = state.search
    out = [("Outbound", s["origin"], s["dest"], s["depart"])]
    if s["ret"]:
        out.append(("Return", s["dest"], s["origin"], s["ret"]))
    return out


def chosen_flights():
    return [Flight(**state.chosen[i]) for i in sorted(state.chosen)]


def flight_card(f, leg, badges, seats_left, selected):
    s = state.search
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.5, 2.6, 1.2, 1])
        c1.markdown(
            f"""<div class="airline"><div class="logo" style="background:{f.color}">{f.code}</div>
            <div><b>{f.airline}</b><small>{f.number}</small></div></div>""",
            unsafe_allow_html=True,
        )
        plus = " <sup>+1</sup>" if f.next_day else ""
        c2.markdown(
            f"""<div class="times">
              <div><div class="t">{clock(f.depart_min)}</div><div class="c">{f.origin}</div></div>
              <div class="dur">{duration_text(f.duration_min)}<hr>Non-stop</div>
              <div><div class="t">{clock(f.arrive_min)}{plus}</div><div class="c">{f.destination}</div></div>
            </div>""",
            unsafe_allow_html=True,
        )
        tags = "".join(badges)
        if seats_left <= 9:
            tags += f'<span class="badge b-seats">{seats_left} seat{"s" if seats_left != 1 else ""} left</span>'
        c3.markdown(
            f'<div class="fare">{money(f.cabin_fare(s["cabin"]))}<small>per traveller</small></div>{tags}',
            unsafe_allow_html=True,
        )
        if seats_left < s["travellers"]:
            c4.button("Sold out", key=f"sel_{leg}_{f.number}", disabled=True, use_container_width=True)
        elif c4.button(
            "✓ Selected" if selected else "Select",
            key=f"sel_{leg}_{f.number}",
            type="primary" if selected else "secondary",
            use_container_width=True,
        ):
            state.chosen[leg] = f.to_dict()
            ret = state.chosen.get(1)
            if leg == 0 and ret and ret["date"] == f.date and ret["depart_min"] < f.arrive_min + 60:
                del state.chosen[1]  # the chosen return no longer leaves after this flight lands
            st.rerun()


def fare_summary(show_continue):
    s = state.search
    flights = chosen_flights()
    with st.container(border=True):
        st.markdown("#### Your trip")
        st.caption(f"{s['travellers']} traveller{'s' if s['travellers'] > 1 else ''} · {s['cabin']}")
        for (label, a, b, date), i in zip(legs(), range(2)):
            f = state.chosen.get(i)
            detail = f"{f['airline']} {f['number']} · {clock(f['depart_min'])}" if f else "_Not selected yet_"
            st.markdown(f"**{label}** · {CITIES[a][0]} → {CITIES[b][0]}  \n{fmt_date(date)}  \n{detail}")
        if len(flights) == len(legs()):
            fare = fare_breakdown(flights, s["cabin"], s["travellers"])
            st.markdown(
                f"""<div class="summary-row"><span>Base fare ({money(fare['per_seat'])} × {s['travellers']})</span>
                <span>{money(fare['base'])}</span></div>
                <div class="summary-row"><span>GST @ {CABINS[s['cabin']]['gst']}%</span><span>{money(fare['gst'])}</span></div>
                <div class="summary-total"><span>Total</span><span>{money(fare['total'])}</span></div>""",
                unsafe_allow_html=True,
            )
            if show_continue:
                st.write("")
                if st.button("Continue to passengers →", type="primary", use_container_width=True, key="to_pax"):
                    go(2)
                    st.rerun()
        if st.button("↺ Start over", use_container_width=True, key="start_over"):
            reset_booking()
            st.rerun()


def select_step():
    s = state.search
    booked = store.seats_booked()
    left, right = st.columns([2.4, 1], gap="large")
    with right:
        fare_summary(show_continue=True)
    with left:
        sort = st.radio("Sort by", ["Cheapest", "Earliest", "Fastest"], horizontal=True, key="sort")
        for i, (label, a, b, date) in enumerate(legs()):
            flights = search_flights(a, b, date)
            if i == 1 and 0 in state.chosen:
                # A same-day return must leave at least an hour after the outbound flight lands.
                out = Flight(**state.chosen[0])
                if date.isoformat() == out.date:
                    flights = [f for f in flights if f.depart_min >= out.arrive_min + 60]
            st.markdown(f"### {label}: {CITIES[a][0]} → {CITIES[b][0]}")
            st.caption(f"{fmt_date(date)} · {len(flights)} flights")
            if not flights:
                st.info("No return flights leave late enough on this day. Try a later return date.")
                continue
            cheapest = min(flights, key=lambda f: (f.fare, f.depart_min)).number
            fastest = min(flights, key=lambda f: (f.duration_min, f.fare)).number
            key = {"Cheapest": lambda f: f.fare, "Earliest": lambda f: f.depart_min,
                   "Fastest": lambda f: f.duration_min}[sort]
            for f in sorted(flights, key=key):
                badges = []
                if f.number == cheapest:
                    badges.append('<span class="badge b-cheap">Cheapest</span>')
                if f.number == fastest:
                    badges.append('<span class="badge b-fast">Fastest</span>')
                seats_left = max(0, f.seats - booked.get(f.key, 0))
                selected = state.chosen.get(i, {}).get("number") == f.number
                flight_card(f, i, badges, seats_left, selected)


# ----------------------------------------------------------------------
# Book: passengers and payment
# ----------------------------------------------------------------------


def passengers_step():
    s = state.search
    left, right = st.columns([2.4, 1], gap="large")
    with right:
        fare_summary(show_continue=False)
    with left:
        st.markdown("### Passenger details")
        st.caption("Enter names exactly as they appear on a government photo ID.")
        saved = state.passengers or {}
        with st.form("pax_form"):
            names = []
            for i in range(s["travellers"]):
                c1, c2 = st.columns(2)
                prev = saved.get("travellers", [{}] * s["travellers"])
                prev = prev[i] if i < len(prev) else {}
                first = c1.text_input(f"Traveller {i + 1} · First name", prev.get("first", ""), key=f"first_{i}")
                last = c2.text_input(f"Traveller {i + 1} · Last name", prev.get("last", ""), key=f"last_{i}")
                names.append((first, last))
            st.markdown("**Contact**")
            c1, c2 = st.columns(2)
            mobile = c1.text_input("Mobile number", saved.get("mobile", ""), placeholder="98765 43210", key="mobile")
            email = c2.text_input("Email (optional)", saved.get("email", ""), placeholder="you@example.com", key="email")
            c1, c2 = st.columns(2)
            back = c1.form_submit_button("← Back to flights", use_container_width=True)
            submitted = c2.form_submit_button("Continue to payment →", type="primary", use_container_width=True)

        if back:
            go(1)
            st.rerun()
        if submitted:
            errors, travellers = [], []
            for i, (first, last) in enumerate(names, 1):
                f, l = clean_name(first), clean_name(last)
                if not f or not l:
                    errors.append(f"Traveller {i}: enter a first and last name using letters only.")
                travellers.append({"first": f or first, "last": l or last})
            mob = clean_mobile(mobile)
            if not mob:
                errors.append("Enter a valid 10-digit Indian mobile number.")
            if email.strip() and not valid_email(email):
                errors.append("Enter a valid email address or leave it blank.")
            if errors:
                for e in errors:
                    st.error(e)
            else:
                state.passengers = {"travellers": travellers, "mobile": mob, "email": email.strip()}
                go(3)
                st.rerun()


def payment_step():
    s = state.search
    flights = chosen_flights()
    fare = fare_breakdown(flights, s["cabin"], s["travellers"])
    left, right = st.columns([2.4, 1], gap="large")
    with right:
        fare_summary(show_continue=False)
    with left:
        st.markdown(f"### Payment · {money(fare['total'])}")
        method = st.radio("Pay with", ["UPI", "Credit / debit card", "Paytm wallet"], horizontal=True, key="method")
        with st.form("pay_form"):
            if method == "UPI":
                upi = st.text_input("UPI ID", placeholder="name@okbank", key="upi")
            elif method == "Credit / debit card":
                card = st.text_input("Card number", placeholder="4111 1111 1111 1111", key="card")
                c1, c2 = st.columns(2)
                expiry = c1.text_input("Expiry (MM/YY)", placeholder="12/28", key="expiry")
                cvv = c2.text_input("CVV", type="password", max_chars=4, key="cvv")
            else:
                st.info(f"The Paytm wallet linked to {state.passengers['mobile']} will be charged.")
            with st.expander("Boarding rules and cancellation policy"):
                st.markdown(
                    "- Check-in closes 45 minutes before departure. Carry a printed or digital ticket.\n"
                    "- Carry an Aadhaar card or another government photo ID.\n"
                    "- Sharp objects are not allowed on board. Switch phones to flight mode.\n"
                    f"- Cancellation fee: {money(3000)} per traveller per flight; the rest is refunded."
                )
            agree = st.checkbox("I have read and accept the boarding rules and cancellation policy", key="agree")
            c1, c2 = st.columns(2)
            back = c1.form_submit_button("← Back to passengers", use_container_width=True)
            pay = c2.form_submit_button(f"Pay {money(fare['total'])}", type="primary", use_container_width=True)

        if back:
            go(2)
            st.rerun()
        if pay:
            errors = []
            if not agree:
                errors.append("Please accept the boarding rules and cancellation policy.")
            if method == "UPI":
                if not valid_upi(upi):
                    errors.append("Enter a valid UPI ID, e.g. name@okbank.")
                payment = f"UPI ({upi.strip()})"
            elif method == "Credit / debit card":
                digits = "".join(ch for ch in card if ch.isdigit())
                if not luhn_valid(card):
                    errors.append("Enter a valid card number.")
                if not valid_expiry(expiry):
                    errors.append("Enter a valid, unexpired expiry date as MM/YY.")
                if not valid_cvv(cvv):
                    errors.append("CVV must be 3 or 4 digits.")
                payment = f"Card ending {digits[-4:]}"  # the full number and CVV are never stored
            else:
                payment = f"Paytm wallet ({state.passengers['mobile']})"

            booked = store.seats_booked()
            for f in flights:
                if f.seats - booked.get(f.key, 0) < s["travellers"]:
                    errors.append(f"Sorry, {f.airline} {f.number} no longer has enough seats. Please pick another flight.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                booking = Booking(
                    pnr=new_pnr(store.taken_pnrs()),
                    status="CONFIRMED",
                    cabin=s["cabin"],
                    travellers=state.passengers["travellers"],
                    flights=[f.to_dict() for f in flights],
                    mobile=state.passengers["mobile"],
                    email=state.passengers["email"],
                    payment=payment,
                    fare=fare,
                )
                store.save(booking)
                state.confirmed_pnr = booking.pnr
                go(4)
                st.rerun()


def confirmed_step():
    booking = store.find(state.confirmed_pnr, state.passengers["travellers"][0]["last"])
    st.success(f"Payment successful - your booking is confirmed. PNR **{booking.pnr}**.", icon="🎉")
    show_ticket(booking)
    st.write("")
    c1, c2, _ = st.columns([1, 1, 2])
    c1.download_button(
        "⬇️ Download e-ticket", ticket_document(booking), f"eticket-{booking.pnr}.html", "text/html",
        use_container_width=True,
    )
    if c2.button("Book another flight", use_container_width=True, key="again"):
        reset_booking()
        st.rerun()


with tab_book:
    step = state.step
    st.markdown(
        '<div class="steps">'
        + "".join(
            f'<span class="step {"now" if i == step else "done" if i < step else ""}">{i + 1}. {name}</span>'
            for i, name in enumerate(STEPS)
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    if step <= 1:
        search_panel()
    if step == 1 and state.search:
        select_step()
    elif step == 2:
        passengers_step()
    elif step == 3:
        payment_step()
    elif step == 4:
        confirmed_step()

# ----------------------------------------------------------------------
# Manage booking
# ----------------------------------------------------------------------

with tab_manage:
    st.markdown("### Find your booking")
    with st.form("lookup_form"):
        c1, c2, c3 = st.columns([1, 1.5, 1])
        pnr = c1.text_input("PNR", max_chars=6, placeholder="e.g. K7MX2P", key="lookup_pnr")
        last = c2.text_input("Lead passenger's last name", key="lookup_last")
        c3.write("")
        found = c3.form_submit_button("Find booking", type="primary", use_container_width=True)
    if found:
        state.lookup = (pnr, last)

    if state.get("lookup"):
        booking = store.find(*state.lookup)
        if not booking:
            st.error("No booking matches that PNR and last name.")
        else:
            show_ticket(booking)
            st.write("")
            st.download_button(
                "⬇️ Download e-ticket", ticket_document(booking), f"eticket-{booking.pnr}.html", "text/html",
                key="manage_download",
            )
            first_flight = booking.flight_objects()[0]
            if booking.status == "CONFIRMED":
                if dt.date.fromisoformat(first_flight.date) < today():
                    st.info("This trip has already started and can no longer be cancelled.")
                else:
                    quote = cancellation_quote(booking.fare["total"], len(booking.travellers), len(booking.flights))
                    with st.container(border=True):
                        st.markdown("#### Cancel this booking")
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Paid", money(booking.fare["total"]))
                        c2.metric("Cancellation fee", money(quote["fee"]))
                        c3.metric("Refund", money(quote["refund"]))
                        sure = st.checkbox("Yes, I want to cancel all flights on this booking", key="cancel_sure")
                        if st.button("Cancel booking", disabled=not sure, key="cancel_btn"):
                            booking.status = "CANCELLED"
                            store.save(booking)
                            st.toast(f"Booking {booking.pnr} cancelled. {money(quote['refund'])} will be refunded.")
                            st.rerun()

# ----------------------------------------------------------------------
# About
# ----------------------------------------------------------------------

with tab_about:
    st.markdown(
        """
        ### About this project

        SkyWay is the web version of a **C++ console flight reservation system** (`flight.cpp` in this
        repository), rebuilt with Python and Streamlit.

        - **Flight search:** durations and base fares come from real great-circle distances between airports.
          Fares rise closer to departure and on weekends. The same search always shows the same flights.
        - **Fares:** three cabin classes with different fare multipliers and GST (5% or 12%).
        - **Validation:** names, Indian mobile numbers, UPI IDs, and card numbers (Luhn check plus expiry date).
          Only the last four card digits are kept, and the CVV is never stored.
        - **Bookings:** each booking gets a 6-character PNR and is stored in SQLite.
          Seats left go down as seats are booked. Tickets can be downloaded as printable HTML.
        - **Manage booking:** look up a booking by PNR and last name, then cancel it with an automatic refund
          calculation.

        Flights, fares and payments are simulated for demonstration only.
        """
    )

#!/bin/sh
# Scripted end-to-end test. Phase 1 books flights; phase 2 restarts the
# program and views/cancels the booking by PNR (checks persistence).
# Usage: tests/smoke_test.sh ./flight
set -u
BIN=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
TESTS=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK" || exit 1
export FLIGHT_TODAY=2026-09-26 FLIGHT_SEED=42
fail=0

check() {  # check <output> <expected text>
    if printf '%s' "$1" | grep -qF -- "$2"; then
        echo "PASS: $2"
    else
        echo "FAIL: expected output containing: $2"
        fail=1
    fi
}

OUT=$("$BIN" < "$TESTS/book.txt" 2>&1)
check "$OUT" "Departure and destination cities must be different."
check "$OUT" "Enter a real date as DD/MM/YYYY"
check "$OUT" "Date must be between 26 Sep 2026 and 26 Sep 2027."
check "$OUT" "Date must be between 15 Dec 2026 and 26 Sep 2027."
check "$OUT" "Passenger  : Aditi Sharma"
check "$OUT" "Travellers : 3"
check "$OUT" "Class      : Business"
check "$OUT" "Flights from New Delhi to Mumbai on 15 Dec 2026"
check "$OUT" "Flights from Mumbai to New Delhi on 20 Dec 2026"
check "$OUT" "GST @ 12%"
check "$OUT" "Enter a valid 10-digit Indian mobile number."
check "$OUT" "Invalid card number."
check "$OUT" "This card has expired."
check "$OUT" "Card ending 1111"
check "$OUT" "Payment successful! Your flight is booked."
check "$OUT" "You must accept the terms to book. Booking cancelled."
check "$OUT" "UPI (ravi@okaxis)"
check "$OUT" "Mobile     : 9123456789"
check "$OUT" "GST @ 5%"

PNR=$(printf '%s' "$OUT" | sed -n 's/.*PNR        : \([A-Z0-9]\{6\}\).*/\1/p' | head -n 1)
[ -n "$PNR" ] && echo "PASS: got PNR $PNR" || { echo "FAIL: no PNR found"; fail=1; }
[ -s bookings.tsv ] && echo "PASS: bookings.tsv written" || { echo "FAIL: bookings.tsv missing"; fail=1; }
[ -s tickets.txt ] && echo "PASS: tickets.txt written" || { echo "FAIL: tickets.txt missing"; fail=1; }

OUT=$(printf '2\n%s\nSHARMA\n\n3\n%s\nwrongname\n\n3\n%s\nsharma\n1\n\n3\n%s\nsharma\n\n4\n' \
      "$(printf '%s' "$PNR" | tr 'A-Z' 'a-z')" "$PNR" "$PNR" "$PNR" | "$BIN" 2>&1)
check "$OUT" "(CONFIRMED)"
check "$OUT" "No booking found with that PNR and last name."
check "$OUT" "Cancellation fee : Rs. 18,000"
check "$OUT" "Booking $PNR cancelled."
check "$OUT" "This booking is already cancelled."
check "$OUT" "Goodbye!"

[ "$fail" -eq 0 ] && echo "All checks passed." || echo "Some checks failed."
exit "$fail"

# Flight Reservation System

A console flight-booking simulator written in C++17. You can search flights, pick a cabin class, pay, get an e-ticket with a PNR, and later view or cancel the booking.

## Features

- **One-way and round-trip bookings** for 1–9 travellers.
- **Real date validation:** leap years and days per month are checked. Travel must be within the next 365 days, and the return date can't be before departure. A same-day return must leave at least an hour after the outbound flight lands.
- **Three cabin classes:** Economy, Premium Economy and Business, each with its own fare multiplier and GST rate (5% or 12%).
- **Flight search:** five airlines with flight numbers, departure and arrival times, duration and fare. The same route and date always shows the same flights.
- **Review and edit** name, travellers, route, dates or class before choosing a flight.
- **Fare breakdown:** base fare × travellers, GST, and total payable.
- **Payment:**
  - UPI, with the UPI ID checked.
  - Paytm wallet.
  - Credit or debit card: the card number is checked with the Luhn algorithm and the expiry date is checked. Only the last 4 digits are kept, and the CVV is never stored.
- **E-ticket** with a 6-character PNR, printed on screen and appended to `tickets.txt`.
- **View or cancel a booking** using the PNR and last name. Cancelling shows the fee and refund.
- **Saved bookings:** bookings are kept in `bookings.tsv` between runs.

## Build and run

You need a C++17 compiler (GCC 8+, Clang 7+ or MSVC 2019+).

```sh
make          # builds ./flight
make run      # builds and starts the program
make test     # runs the end-to-end smoke test
```

Without `make`:

```sh
g++ -std=c++17 -Wall -Wextra -O2 flight.cpp -o flight
./flight
```

It works on Windows, Linux and macOS.

On Windows with MinGW, add `-static` to the command. Otherwise the program may load a different `libstdc++-6.dll`, such as the one bundled with Git for Windows, and crash. The Makefile does this automatically.

## Fares

| Class           | Fare multiplier | GST |
|-----------------|-----------------|-----|
| Economy         | 1.0×            | 5%  |
| Premium Economy | 1.6×            | 12% |
| Business        | 2.8×            | 12% |

Cancellation fee: ₹3,000 per traveller per flight (capped at the amount paid).

## Testing

`tests/smoke_test.sh` runs two scripted sessions:

1. The first books a round trip, with deliberate invalid input at each step, plus a declined booking and a one-way UPI booking.
2. The second restarts the program and views and cancels the booking by PNR, which checks that bookings are saved between runs.

Two environment variables make runs reproducible:

| Variable | Purpose |
|---|---|
| `FLIGHT_TODAY=YYYY-MM-DD` | Pretend today is this date |
| `FLIGHT_SEED=<number>` | Make generated PNRs reproducible |

GitHub Actions builds and tests on Linux and Windows on every push.

## Limitations

This is a learning project. No real flights are searched and no real payments are made; all flight data is simulated.

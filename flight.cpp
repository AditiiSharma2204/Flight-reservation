// Flight Reservation System - a console flight booking simulator in C++17.
//
// Features: one-way and round-trip bookings for up to 9 travellers,
// validated calendar dates, three cabin classes, flight search with
// fares and GST, review-and-edit before booking, UPI / card / wallet
// payment with validation, PNR generation, and booking lookup and
// cancellation. Bookings are saved to bookings.tsv and every ticket
// is appended to tickets.txt.
//
// Environment variables (useful for testing):
//   FLIGHT_TODAY=YYYY-MM-DD   pretend today is this date
//   FLIGHT_SEED=<number>      make generated PNRs reproducible

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <random>
#include <regex>
#include <sstream>
#include <string>
#include <vector>

namespace {

constexpr const char *BOOKINGS_FILE = "bookings.tsv";
constexpr const char *TICKETS_FILE = "tickets.txt";
constexpr int MAX_TRAVELLERS = 9;
constexpr int BOOKING_WINDOW_DAYS = 365;
constexpr long long CANCEL_FEE_PER_SEAT = 3000;  // rupees, per traveller per leg

// ------------------------------------------------------------------
// Dates
// ------------------------------------------------------------------

struct Date {
    int d = 0, m = 0, y = 0;
};

bool is_leap(int y) { return (y % 4 == 0 && y % 100 != 0) || y % 400 == 0; }

int days_in_month(int m, int y)
{
    static const int days[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    return m == 2 && is_leap(y) ? 29 : days[m - 1];
}

bool valid_date(const Date &dt)
{
    return dt.y >= 1900 && dt.m >= 1 && dt.m <= 12 && dt.d >= 1 && dt.d <= days_in_month(dt.m, dt.y);
}

// Days since 1970-01-01 (Howard Hinnant's days_from_civil).
long serial(const Date &dt)
{
    int y = dt.m <= 2 ? dt.y - 1 : dt.y;
    int era = (y >= 0 ? y : y - 399) / 400;
    int yoe = y - era * 400;
    int doy = (153 * (dt.m + (dt.m > 2 ? -3 : 9)) + 2) / 5 + dt.d - 1;
    int doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return static_cast<long>(era) * 146097 + doe - 719468;
}

Date from_serial(long z)
{
    z += 719468;
    long era = (z >= 0 ? z : z - 146096) / 146097;
    long doe = z - era * 146097;
    long yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    long doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    long mp = (5 * doy + 2) / 153;
    Date dt;
    dt.d = static_cast<int>(doy - (153 * mp + 2) / 5 + 1);
    dt.m = static_cast<int>(mp < 10 ? mp + 3 : mp - 9);
    dt.y = static_cast<int>(yoe + era * 400 + (dt.m <= 2 ? 1 : 0));
    return dt;
}

std::string format_date(const Date &dt)
{
    static const char *months[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
    std::ostringstream os;
    os << std::setw(2) << std::setfill('0') << dt.d << ' ' << months[dt.m - 1] << ' ' << dt.y;
    return os.str();
}

std::string iso_date(const Date &dt)
{
    char buf[48];
    std::snprintf(buf, sizeof buf, "%04d-%02d-%02d", dt.y, dt.m, dt.d);
    return buf;
}

std::optional<Date> parse_iso_date(const std::string &s)
{
    Date dt;
    char extra;
    if (std::sscanf(s.c_str(), "%d-%d-%d%c", &dt.y, &dt.m, &dt.d, &extra) != 3 || !valid_date(dt))
        return std::nullopt;
    return dt;
}

// Accepts DD/MM/YYYY or DD-MM-YYYY.
std::optional<Date> parse_user_date(const std::string &s)
{
    Date dt;
    char sep1, sep2, extra;
    if (std::sscanf(s.c_str(), "%d%c%d%c%d%c", &dt.d, &sep1, &dt.m, &sep2, &dt.y, &extra) != 5)
        return std::nullopt;
    if (sep1 != sep2 || (sep1 != '/' && sep1 != '-') || !valid_date(dt))
        return std::nullopt;
    return dt;
}

Date today()
{
    if (const char *env = std::getenv("FLIGHT_TODAY"))
        if (auto dt = parse_iso_date(env))
            return *dt;
    std::time_t t = std::time(nullptr);
    std::tm *lt = std::localtime(&t);
    return Date{lt->tm_mday, lt->tm_mon + 1, lt->tm_year + 1900};
}

// ------------------------------------------------------------------
// Flights, cabins and fares
// ------------------------------------------------------------------

struct Cabin {
    const char *name;
    double fare_multiplier;
    int gst_percent;
};

const Cabin CABINS[] = {
    {"Economy", 1.0, 5},
    {"Premium Economy", 1.6, 12},
    {"Business", 2.8, 12},
};
constexpr int NUM_CABINS = sizeof CABINS / sizeof CABINS[0];

struct Airline {
    const char *name;
    const char *code;
    int base_fare;  // rupees, economy
};

const Airline AIRLINES[] = {
    {"IndiGo", "6E", 4800},
    {"Air India", "AI", 5600},
    {"Akasa Air", "QP", 4500},
    {"SpiceJet", "SG", 4300},
    {"Air India Express", "IX", 4100},
};

struct Flight {
    std::string airline;
    std::string number;
    int depart_min = 0;    // minutes after midnight
    int duration_min = 0;
    long long fare = 0;    // economy fare per seat, rupees
};

std::string clock_time(int minutes)
{
    char buf[48];
    std::snprintf(buf, sizeof buf, "%02d:%02d", (minutes / 60) % 24, minutes % 60);
    std::string s = buf;
    if (minutes >= 24 * 60)
        s += " (+1)";
    return s;
}

std::string duration_text(int minutes)
{
    char buf[48];
    std::snprintf(buf, sizeof buf, "%dh %02dm", minutes / 60, minutes % 60);
    return buf;
}

// FNV-1a: a stable hash so the same search always shows the same flights.
std::uint32_t fnv1a(const std::string &s)
{
    std::uint32_t h = 2166136261u;
    for (unsigned char c : s) {
        h ^= c;
        h *= 16777619u;
    }
    return h;
}

std::string lower(std::string s)
{
    for (char &c : s)
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

std::vector<Flight> search_flights(const std::string &from, const std::string &to, const Date &date)
{
    // Route duration is the same in both directions.
    std::string a = lower(from), b = lower(to);
    std::mt19937 route_rng(fnv1a(std::min(a, b) + "|" + std::max(a, b)));
    int route_minutes = std::uniform_int_distribution<int>(12, 42)(route_rng) * 5;  // 1h to 3h30

    std::mt19937 rng(fnv1a(a + "|" + b + "|" + iso_date(date)));
    std::uniform_int_distribution<int> slot(60, 22 * 12 - 1);  // 05:00 to 22:55
    std::uniform_int_distribution<int> jitter(-3, 3);
    std::uniform_real_distribution<double> price_factor(0.85, 1.35);
    std::uniform_int_distribution<int> flight_no(100, 9899);

    std::vector<Flight> flights;
    for (const Airline &al : AIRLINES) {
        Flight f;
        f.airline = al.name;
        f.number = std::string(al.code) + " " + std::to_string(flight_no(rng));
        f.depart_min = slot(rng) * 5;
        f.duration_min = route_minutes + jitter(rng) * 5;
        f.fare = static_cast<long long>(al.base_fare * price_factor(rng) / 10.0 + 0.5) * 10;
        flights.push_back(f);
    }
    std::sort(flights.begin(), flights.end(),
              [](const Flight &x, const Flight &y) { return x.depart_min < y.depart_min; });
    return flights;
}

// Formats rupees with Indian digit grouping, e.g. 1234567 -> "Rs. 12,34,567".
std::string money(long long rupees)
{
    std::string digits = std::to_string(rupees < 0 ? -rupees : rupees);
    std::string out;
    int n = static_cast<int>(digits.size());
    for (int i = 0; i < n; i++) {
        int left = n - i;
        if (i > 0 && (left == 3 || (left > 3 && (left - 3) % 2 == 0)))
            out += ',';
        out += digits[static_cast<size_t>(i)];
    }
    return (rupees < 0 ? "-Rs. " : "Rs. ") + out;
}

// ------------------------------------------------------------------
// Bookings
// ------------------------------------------------------------------

struct Booking {
    std::string pnr;
    std::string status = "CONFIRMED";
    std::string first_name, last_name;
    int travellers = 1;
    std::string from, to;
    bool round_trip = false;
    Date depart, ret;
    int cabin = 0;
    Flight outbound, inbound;
    std::string mobile;
    std::string payment;
    long long base_fare = 0, gst = 0, total = 0;
};

void compute_fare(Booking &b)
{
    const Cabin &c = CABINS[b.cabin];
    long long per_seat = static_cast<long long>(b.outbound.fare * c.fare_multiplier + 0.5);
    if (b.round_trip)
        per_seat += static_cast<long long>(b.inbound.fare * c.fare_multiplier + 0.5);
    b.base_fare = per_seat * b.travellers;
    b.gst = (b.base_fare * c.gst_percent + 50) / 100;
    b.total = b.base_fare + b.gst;
}

std::vector<Booking> bookings;

std::string flight_to_tsv(const Flight &f)
{
    return f.airline + '\t' + f.number + '\t' + std::to_string(f.depart_min) + '\t' +
           std::to_string(f.duration_min) + '\t' + std::to_string(f.fare);
}

void save_bookings()
{
    std::ofstream out(BOOKINGS_FILE, std::ios::trunc);
    if (!out) {
        std::cout << "Warning: could not save bookings to " << BOOKINGS_FILE << ".\n";
        return;
    }
    for (const Booking &b : bookings) {
        out << b.pnr << '\t' << b.status << '\t' << b.first_name << '\t' << b.last_name << '\t'
            << b.travellers << '\t' << b.from << '\t' << b.to << '\t' << (b.round_trip ? 1 : 0) << '\t'
            << iso_date(b.depart) << '\t' << (b.round_trip ? iso_date(b.ret) : "-") << '\t' << b.cabin << '\t'
            << flight_to_tsv(b.outbound) << '\t' << flight_to_tsv(b.inbound) << '\t' << b.mobile << '\t'
            << b.payment << '\t' << b.base_fare << '\t' << b.gst << '\t' << b.total << '\n';
    }
}

void load_bookings()
{
    std::ifstream in(BOOKINGS_FILE);
    std::string line;
    while (std::getline(in, line)) {
        std::vector<std::string> f;
        std::stringstream ss(line);
        std::string field;
        while (std::getline(ss, field, '\t'))
            f.push_back(field);
        if (f.size() != 26)
            continue;
        try {
            Booking b;
            size_t i = 0;
            b.pnr = f[i++];
            b.status = f[i++];
            b.first_name = f[i++];
            b.last_name = f[i++];
            b.travellers = std::stoi(f[i++]);
            b.from = f[i++];
            b.to = f[i++];
            b.round_trip = f[i++] == "1";
            auto dep = parse_iso_date(f[i++]);
            auto ret = parse_iso_date(f[i++]);
            b.cabin = std::stoi(f[i++]);
            for (Flight *fl : {&b.outbound, &b.inbound}) {
                fl->airline = f[i++];
                fl->number = f[i++];
                fl->depart_min = std::stoi(f[i++]);
                fl->duration_min = std::stoi(f[i++]);
                fl->fare = std::stoll(f[i++]);
            }
            b.mobile = f[i++];
            b.payment = f[i++];
            b.base_fare = std::stoll(f[i++]);
            b.gst = std::stoll(f[i++]);
            b.total = std::stoll(f[i++]);
            if (!dep || (b.round_trip && !ret) || b.cabin < 0 || b.cabin >= NUM_CABINS)
                continue;
            b.depart = *dep;
            if (ret)
                b.ret = *ret;
            bookings.push_back(b);
        } catch (const std::exception &) {
            // skip corrupt line
        }
    }
}

Booking *find_booking(const std::string &pnr, const std::string &last_name)
{
    for (Booking &b : bookings)
        if (b.pnr == pnr && lower(b.last_name) == lower(last_name))
            return &b;
    return nullptr;
}

std::mt19937 &pnr_rng()
{
    static std::mt19937 rng = [] {
        if (const char *env = std::getenv("FLIGHT_SEED"))
            return std::mt19937(static_cast<std::uint32_t>(std::strtoul(env, nullptr, 10)));
        std::random_device rd;
        return std::mt19937(rd());
    }();
    return rng;
}

// Airline PNRs are 6 characters; ambiguous letters (I, O) and digits (0, 1) are left out.
std::string new_pnr()
{
    static const std::string chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    std::uniform_int_distribution<size_t> pick(0, chars.size() - 1);
    for (;;) {
        std::string pnr;
        for (int i = 0; i < 6; i++)
            pnr += chars[pick(pnr_rng())];
        bool taken = std::any_of(bookings.begin(), bookings.end(),
                                 [&](const Booking &b) { return b.pnr == pnr; });
        if (!taken)
            return pnr;
    }
}

// ------------------------------------------------------------------
// Input helpers
// ------------------------------------------------------------------

std::string trim(const std::string &s)
{
    size_t start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos)
        return "";
    size_t end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

std::string read_line(const std::string &prompt)
{
    std::cout << prompt << std::flush;
    std::string s;
    if (!std::getline(std::cin, s)) {
        std::cout << "\nInput closed. Goodbye!\n";
        std::exit(0);
    }
    return trim(s);
}

int read_int(const std::string &prompt, int lo, int hi)
{
    for (;;) {
        std::string s = read_line(prompt);
        try {
            size_t used;
            int v = std::stoi(s, &used);
            if (used == s.size() && v >= lo && v <= hi)
                return v;
        } catch (const std::exception &) {
        }
        std::cout << "  Please enter a number between " << lo << " and " << hi << ".\n";
    }
}

int read_choice(int max) { return read_int("Enter your choice: ", 1, max); }

void pause_screen() { read_line("\nPress ENTER to continue..."); }

std::string title_case(std::string s)
{
    bool start = true;
    for (char &c : s) {
        unsigned char u = static_cast<unsigned char>(c);
        c = static_cast<char>(start ? std::toupper(u) : std::tolower(u));
        start = c == ' ' || c == '-' || c == '\'';
    }
    return s;
}

// Letters with single spaces, hyphens, apostrophes or dots between them.
std::string read_words(const std::string &prompt, const std::string &what, size_t max_len)
{
    static const std::regex pattern(R"([A-Za-z]+([ .'-]+[A-Za-z]+)*\.?)");
    for (;;) {
        std::string s = read_line(prompt);
        if (!s.empty() && s.size() <= max_len && std::regex_match(s, pattern))
            return title_case(s);
        std::cout << "  Please enter a valid " << what << " (letters only, up to " << max_len
                  << " characters).\n";
    }
}

Date read_date(const std::string &prompt, const Date &earliest, const Date &latest)
{
    for (;;) {
        std::string s = read_line(prompt);
        auto dt = parse_user_date(s);
        if (!dt) {
            std::cout << "  Enter a real date as DD/MM/YYYY (e.g. 15/12/2026).\n";
        } else if (serial(*dt) < serial(earliest) || serial(*dt) > serial(latest)) {
            std::cout << "  Date must be between " << format_date(earliest) << " and "
                      << format_date(latest) << ".\n";
        } else {
            return *dt;
        }
    }
}

std::string digits_only(const std::string &s)
{
    std::string out;
    for (char c : s)
        if (std::isdigit(static_cast<unsigned char>(c)))
            out += c;
        else if (c != ' ' && c != '-')
            return "";
    return out;
}

// Indian mobile number: 10 digits starting with 6-9, optional +91 prefix.
std::string read_mobile()
{
    for (;;) {
        std::string s = read_line("Mobile number: ");
        if (s.rfind("+91", 0) == 0)
            s = s.substr(3);
        std::string d = digits_only(s);
        if (d.size() == 10 && d[0] >= '6')
            return d;
        std::cout << "  Enter a valid 10-digit Indian mobile number.\n";
    }
}

bool luhn_valid(const std::string &digits)
{
    int sum = 0;
    bool dbl = false;
    for (auto it = digits.rbegin(); it != digits.rend(); ++it) {
        int d = *it - '0';
        if (dbl && (d *= 2) > 9)
            d -= 9;
        sum += d;
        dbl = !dbl;
    }
    return sum % 10 == 0;
}

// ------------------------------------------------------------------
// Booking flow
// ------------------------------------------------------------------

void print_summary(const Booking &b)
{
    std::cout << "\n------------------- Booking Details -------------------\n"
              << "Passenger  : " << b.first_name << ' ' << b.last_name << '\n'
              << "Travellers : " << b.travellers << '\n'
              << "Route      : " << b.from << " -> " << b.to << '\n'
              << "Trip       : " << (b.round_trip ? "Round trip" : "One way") << '\n'
              << "Departure  : " << format_date(b.depart) << '\n';
    if (b.round_trip)
        std::cout << "Return     : " << format_date(b.ret) << '\n';
    std::cout << "Class      : " << CABINS[b.cabin].name << '\n'
              << "-------------------------------------------------------\n";
}

int read_cabin()
{
    std::cout << "\nChoose your class:\n";
    for (int i = 0; i < NUM_CABINS; i++)
        std::cout << "  " << i + 1 << ". " << CABINS[i].name << '\n';
    return read_choice(NUM_CABINS) - 1;
}

void read_route(Booking &b)
{
    for (;;) {
        b.from = read_words("Flying from (city): ", "city name", 30);
        b.to = read_words("Flying to (city): ", "city name", 30);
        if (lower(b.from) != lower(b.to))
            return;
        std::cout << "  Departure and destination cities must be different.\n";
    }
}

void read_dates(Booking &b)
{
    Date t = today();
    Date last = from_serial(serial(t) + BOOKING_WINDOW_DAYS);
    b.depart = read_date("Departure date (DD/MM/YYYY): ", t, last);
    if (b.round_trip)
        b.ret = read_date("Return date (DD/MM/YYYY): ", b.depart, last);
}

// Returns false if the user chose to cancel.
bool review_and_edit(Booking &b)
{
    for (;;) {
        print_summary(b);
        std::cout << "1. Continue to flight selection\n"
                     "2. Change passenger name\n"
                     "3. Change number of travellers\n"
                     "4. Change route\n"
                     "5. Change dates\n"
                     "6. Change class\n"
                     "7. Cancel and return to main menu\n";
        switch (read_choice(7)) {
        case 1: return true;
        case 2:
            b.first_name = read_words("First name: ", "first name", 40);
            b.last_name = read_words("Last name: ", "last name", 40);
            break;
        case 3: b.travellers = read_int("Number of travellers (1-9): ", 1, MAX_TRAVELLERS); break;
        case 4: read_route(b); break;
        case 5: read_dates(b); break;
        case 6: b.cabin = read_cabin(); break;
        case 7: return false;
        }
    }
}

Flight choose_flight(const std::string &from, const std::string &to, const Date &date, int cabin)
{
    std::vector<Flight> flights = search_flights(from, to, date);
    std::cout << "\nFlights from " << from << " to " << to << " on " << format_date(date) << " ("
              << CABINS[cabin].name << ", fare per traveller):\n\n";
    std::cout << "    " << std::left << std::setw(19) << "Airline" << std::setw(9) << "Flight"
              << std::setw(8) << "Departs" << std::setw(15) << "Arrives" << std::setw(10) << "Duration"
              << std::right << std::setw(12) << "Fare" << '\n';
    for (size_t i = 0; i < flights.size(); i++) {
        const Flight &f = flights[i];
        long long fare = static_cast<long long>(f.fare * CABINS[cabin].fare_multiplier + 0.5);
        std::cout << ' ' << i + 1 << ". " << std::left << std::setw(19) << f.airline << std::setw(9)
                  << f.number << std::setw(8) << clock_time(f.depart_min) << std::setw(15)
                  << clock_time(f.depart_min + f.duration_min) << std::setw(10)
                  << duration_text(f.duration_min) << std::right << std::setw(12) << money(fare) << '\n';
    }
    std::cout << '\n';
    return flights[static_cast<size_t>(read_choice(static_cast<int>(flights.size())) - 1)];
}

void print_fare(const Booking &b)
{
    auto row = [](const std::string &label, long long amount) {
        std::cout << std::left << std::setw(36) << label << std::right << std::setw(16) << money(amount) << '\n';
    };
    std::cout << "\n----------------------- Fare -----------------------\n";
    row("Base fare (" + std::to_string(b.travellers) + " traveller" + (b.travellers > 1 ? "s)" : ")"), b.base_fare);
    row("GST @ " + std::to_string(CABINS[b.cabin].gst_percent) + "%", b.gst);
    row("Total payable", b.total);
    std::cout << "----------------------------------------------------\n";
}

bool accept_terms()
{
    std::cout << "\nBefore continuing, please read and accept the following terms.\n\n"
                 "INSTRUCTIONS BEFORE BOARDING:\n"
                 "  1. Cabin baggage must not exceed 7 kg; check-in baggage must not exceed 15 kg.\n"
                 "  2. Sharp objects are not allowed on board.\n"
                 "  3. Carry a printed or digital copy of your ticket.\n"
                 "  4. Switch your mobile phone to flight mode on board.\n\n"
                 "DOCUMENTS REQUIRED:\n"
                 "  1. Aadhaar card or another government photo ID\n"
                 "  2. One passport-size photograph\n\n"
                 "CANCELLATION:\n"
                 "  A fee of " << money(CANCEL_FEE_PER_SEAT)
              << " per traveller per flight applies; the rest is refunded.\n\n"
                 "1. I agree\n2. I do not agree (cancel booking)\n";
    return read_choice(2) == 1;
}

// Returns a description of the payment, or empty if the user cancelled.
std::string take_payment(const Booking &b)
{
    std::cout << "\nAmount to pay: " << money(b.total) << "\n\nPayment method:\n"
                 "1. UPI\n2. Paytm wallet\n3. Credit or debit card\n4. Cancel booking\n";
    switch (read_choice(4)) {
    case 1: {
        static const std::regex vpa(R"([A-Za-z0-9._-]{2,256}@[A-Za-z]{2,64})");
        for (;;) {
            std::string id = read_line("UPI ID (e.g. name@okbank): ");
            if (std::regex_match(id, vpa))
                return "UPI (" + id + ")";
            std::cout << "  Invalid UPI ID.\n";
        }
    }
    case 2:
        return "Paytm wallet (" + b.mobile + ")";
    case 3: {
        std::string card;
        for (;;) {
            card = digits_only(read_line("Card number: "));
            if (card.size() >= 13 && card.size() <= 19 && luhn_valid(card))
                break;
            std::cout << "  Invalid card number.\n";
        }
        Date t = today();
        for (;;) {
            int mm, yy;
            char slash, extra;
            std::string exp = read_line("Expiry (MM/YY): ");
            if (std::sscanf(exp.c_str(), "%d%c%d%c", &mm, &slash, &yy, &extra) == 3 && slash == '/' &&
                mm >= 1 && mm <= 12 && yy >= 0 && yy <= 99) {
                int year = 2000 + yy;
                if (year > t.y || (year == t.y && mm >= t.m))
                    break;
                std::cout << "  This card has expired.\n";
            } else {
                std::cout << "  Enter expiry as MM/YY.\n";
            }
        }
        for (;;) {
            std::string cvv = read_line("CVV: ");
            if ((cvv.size() == 3 || cvv.size() == 4) && digits_only(cvv) == cvv)
                break;
            std::cout << "  CVV must be 3 or 4 digits.\n";
        }
        // Only the last four digits are kept; the CVV is never stored.
        return "Card ending " + card.substr(card.size() - 4);
    }
    default:
        return "";
    }
}

void print_leg(std::ostream &os, const char *label, const Date &date, const Flight &f)
{
    os << "  " << label << format_date(date) << "  " << f.airline << ' ' << f.number << "  Departs "
       << clock_time(f.depart_min) << "  Arrives " << clock_time(f.depart_min + f.duration_min) << '\n';
}

void print_ticket(std::ostream &os, const Booking &b)
{
    os << "==================== E-TICKET ====================\n"
       << "  PNR        : " << b.pnr << "   (" << b.status << ")\n"
       << "  Passenger  : " << b.first_name << ' ' << b.last_name;
    if (b.travellers > 1)
        os << " + " << b.travellers - 1 << " more";
    os << "\n  Mobile     : " << b.mobile << '\n'
       << "  Route      : " << b.from << " -> " << b.to << (b.round_trip ? " (round trip)" : "") << '\n'
       << "  Class      : " << CABINS[b.cabin].name << "\n\n";
    print_leg(os, "Outbound : ", b.depart, b.outbound);
    if (b.round_trip)
        print_leg(os, "Return   : ", b.ret, b.inbound);
    os << "\n  Base fare  : " << money(b.base_fare) << "\n  GST        : " << money(b.gst)
       << "\n  Total paid : " << money(b.total) << "  via " << b.payment << '\n'
       << "==================================================\n";
}

void book_flight()
{
    Booking b;
    std::cout << "\n===== Book a Flight =====\n\n1. One way\n2. Round trip\n";
    b.round_trip = read_choice(2) == 2;
    b.first_name = read_words("First name: ", "first name", 40);
    b.last_name = read_words("Last name: ", "last name", 40);
    b.travellers = read_int("Number of travellers (1-9): ", 1, MAX_TRAVELLERS);
    read_route(b);
    read_dates(b);
    b.cabin = read_cabin();

    if (!review_and_edit(b)) {
        std::cout << "Booking cancelled.\n";
        return;
    }

    b.outbound = choose_flight(b.from, b.to, b.depart, b.cabin);
    if (b.round_trip) {
        for (;;) {
            b.inbound = choose_flight(b.to, b.from, b.ret, b.cabin);
            // A same-day return must leave after the outbound flight lands.
            if (serial(b.ret) > serial(b.depart) ||
                b.inbound.depart_min >= b.outbound.depart_min + b.outbound.duration_min + 60)
                break;
            std::cout << "  That return flight leaves before (or within an hour of) your outbound\n"
                         "  flight landing. Please choose a later flight.\n";
        }
    }
    compute_fare(b);
    print_fare(b);

    if (!accept_terms()) {
        std::cout << "You must accept the terms to book. Booking cancelled.\n";
        return;
    }
    std::cout << '\n';
    b.mobile = read_mobile();
    b.payment = take_payment(b);
    if (b.payment.empty()) {
        std::cout << "Payment cancelled. No booking was made.\n";
        return;
    }

    b.pnr = new_pnr();
    bookings.push_back(b);
    save_bookings();
    std::ofstream tickets(TICKETS_FILE, std::ios::app);
    print_ticket(tickets, b);
    tickets << '\n';

    std::cout << "\nPayment successful! Your flight is booked.\n\n";
    print_ticket(std::cout, b);
    std::cout << "A copy of this ticket was saved to " << TICKETS_FILE << ".\n";
}

Booking *lookup_prompt()
{
    std::string pnr = read_line("PNR: ");
    std::transform(pnr.begin(), pnr.end(), pnr.begin(),
                   [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
    std::string last = read_line("Last name: ");
    Booking *b = find_booking(pnr, last);
    if (!b)
        std::cout << "No booking found with that PNR and last name.\n";
    return b;
}

void view_booking()
{
    std::cout << "\n===== View Booking =====\n\n";
    if (Booking *b = lookup_prompt()) {
        std::cout << '\n';
        print_ticket(std::cout, *b);
    }
}

void cancel_booking()
{
    std::cout << "\n===== Cancel Booking =====\n\n";
    Booking *b = lookup_prompt();
    if (!b)
        return;
    if (b->status == "CANCELLED") {
        std::cout << "This booking is already cancelled.\n";
        return;
    }
    if (serial(b->depart) < serial(today())) {
        std::cout << "This flight has already departed and cannot be cancelled.\n";
        return;
    }
    int legs = b->round_trip ? 2 : 1;
    long long fee = std::min(b->total, CANCEL_FEE_PER_SEAT * b->travellers * legs);
    std::cout << "\nTotal paid       : " << money(b->total) << "\nCancellation fee : " << money(fee)
              << "\nRefund           : " << money(b->total - fee) << "\n\n1. Confirm cancellation\n2. Keep booking\n";
    if (read_choice(2) == 1) {
        b->status = "CANCELLED";
        save_bookings();
        std::cout << "Booking " << b->pnr << " cancelled. " << money(b->total - fee)
                  << " will be refunded to " << b->payment << ".\n";
    } else {
        std::cout << "Your booking has not been changed.\n";
    }
}

}  // namespace

int main()
{
    load_bookings();
    for (;;) {
        std::cout << "\n========== Flight Reservation System ==========\n\n"
                     "1. Book a flight\n2. View a booking\n3. Cancel a booking\n4. Exit\n";
        switch (read_choice(4)) {
        case 1: book_flight(); break;
        case 2: view_booking(); break;
        case 3: cancel_booking(); break;
        case 4:
            std::cout << "Thank you for flying with us. Goodbye!\n";
            return 0;
        }
        pause_screen();
    }
}

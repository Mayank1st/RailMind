import io
import os
import qrcode
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

WIDTH, HEIGHT = A4  # 595.27 x 841.89 points

# ── Colors ──
DARK_BG = HexColor("#0A0F1A")
GREEN_PRIMARY = HexColor("#10B981")
GREEN_LIGHT = HexColor("#34D399")
GREEN_DARK = HexColor("#059669")
GREEN_PALE = HexColor("#ECFDF5")
GRAY_50 = HexColor("#F9FAFB")
GRAY_200 = HexColor("#E5E7EB")
GRAY_300 = HexColor("#D1D5DB")
GRAY_400 = HexColor("#9CA3AF")
GRAY_500 = HexColor("#6B7280")
GRAY_600 = HexColor("#4B5563")
GRAY_700 = HexColor("#374151")
GRAY_800 = HexColor("#1F2937")
GRAY_900 = HexColor("#111827")
WHITE = white
BLACK = black
RED_STATUS = HexColor("#EF4444")
AMBER_STATUS = HexColor("#F59E0B")
BLUE_INFO = HexColor("#3B82F6")

# ── Asset Paths ──
ASSETS_DIR = Path(__file__).resolve().parent / "app" / "assets"
LOGO_PATH = ASSETS_DIR / "images" / "logo.png"
FONT_DIR = ASSETS_DIR / "fonts"


# ── Font Names (set during registration) ──
FONT_REGULAR = "NotoSans"
FONT_BOLD = "NotoSans-Bold"

_fonts_registered = False


def register_fonts():
    """Register NotoSans fonts once. Falls back to Helvetica if .ttf files are missing."""
    global _fonts_registered, FONT_REGULAR, FONT_BOLD
    if _fonts_registered:
        return

    regular_path = FONT_DIR / "NotoSans-Regular.ttf"
    bold_path = FONT_DIR / "NotoSans-Bold.ttf"

    if regular_path.exists():
        pdfmetrics.registerFont(TTFont("NotoSans", str(regular_path)))
        FONT_REGULAR = "NotoSans"
    else:
        FONT_REGULAR = "Helvetica"

    if bold_path.exists():
        pdfmetrics.registerFont(TTFont("NotoSans-Bold", str(bold_path)))
        FONT_BOLD = "NotoSans-Bold"
    elif regular_path.exists():
        # If only regular exists, reuse it for bold
        FONT_BOLD = "NotoSans"
    else:
        FONT_BOLD = "Helvetica-Bold"

    _fonts_registered = True


# ── Sample Ticket Data (matches PRD schema) ──
ticket = {
    "pnr_number": "452-187-6390",
    "booking_status": "CONFIRMED",
    "booked_at": "15 Apr 2026, 10:32 AM",
    "journey_date": "22 Apr 2026",
    "journey_day": "Wednesday",
    "train_number": "12301",
    "train_name": "HOWRAH RAJDHANI EXPRESS",
    "train_type": "RAJDHANI",
    "train_class": "AC 2-Tier (2A)",
    "quota": "GENERAL (GN)",
    "source_station": "NDLS",
    "source_name": "New Delhi",
    "departure_time": "16:55",
    "dest_station": "HWH",
    "dest_name": "Howrah Junction",
    "arrival_time": "09:55",
    "arrival_day": "+1",
    "duration": "17h 00m",
    "distance_km": "1,451",
    "coach": "A1",
    "boarding_station": "NDLS - New Delhi",
    "chart_status": "CHART NOT PREPARED",
    "passengers": [
        {
            "name": "RAHUL SHARMA",
            "age": 32,
            "gender": "M",
            "seat": "24 / LB",
            "status": "CNF",
            "fare": 2245.00,
            "id_type": "Aadhaar",
            "id_number": "XXXX-XXXX-4521",
        },
        {
            "name": "PRIYA SHARMA",
            "age": 28,
            "gender": "F",
            "seat": "25 / UB",
            "status": "CNF",
            "fare": 2245.00,
            "id_type": "Aadhaar",
            "id_number": "XXXX-XXXX-7834",
        },
        {
            "name": "ARJUN SHARMA",
            "age": 8,
            "gender": "M",
            "seat": "26 / MB",
            "status": "CNF",
            "fare": 1120.00,
            "id_type": "—",
            "id_number": "—",
        },
    ],
    "fare_breakdown": {
        "base_fare": 4290.00,
        "reservation_charge": 120.00,
        "superfast_charge": 90.00,
        "gst": 270.00,
        "insurance": 2.90,
        "total_fare": 5610.00,
    },
    "payment": {
        "txn_id": "RM-PAY-20260415-7823",
        "method": "UPI (PhonePe)",
        "status": "SUCCESS",
    },
    "user": {
        "name": "Rahul Sharma",
        "email": "rahul.sharma@email.com",
        "phone": "+91-98765-43210",
    },
}


def draw_rounded_rect(c, x, y, w, h, r, fill=None, stroke=None, stroke_width=0.5):
    p = c.beginPath()
    p.moveTo(x + r, y)
    p.lineTo(x + w - r, y)
    p.arcTo(x + w - r, y, x + w, y + r, r)
    p.lineTo(x + w, y + h - r)
    p.arcTo(x + w, y + h - r, x + w - r, y + h, r)
    p.lineTo(x + r, y + h)
    p.arcTo(x + r, y + h, x, y + h - r, r)
    p.lineTo(x, y + r)
    p.arcTo(x, y + r, x + r, y, r)
    p.close()
    if fill:
        c.setFillColor(fill)
    if stroke:
        c.setStrokeColor(stroke)
        c.setLineWidth(stroke_width)
    if fill and stroke:
        c.drawPath(p, fill=1, stroke=1)
    elif fill:
        c.drawPath(p, fill=1, stroke=0)
    elif stroke:
        c.drawPath(p, fill=0, stroke=1)


def draw_status_badge(c, x, y, text, color):
    tw = c.stringWidth(text, FONT_BOLD, 9) + 16
    draw_rounded_rect(c, x, y, tw, 18, 9, fill=color)
    c.setFillColor(WHITE)
    c.setFont(FONT_BOLD, 9)
    c.drawString(x + 8, y + 5, text)
    return tw


def generate_qr(data):
    qr_img = qrcode.make(data, box_size=10, border=1)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def build_ticket_pdf(output_path):
    register_fonts()

    c = canvas.Canvas(output_path, pagesize=A4)
    c.setTitle("RailMind E-Ticket")
    c.setAuthor("RailMind")

    margin = 36
    content_w = WIDTH - 2 * margin
    cursor_y = HEIGHT - margin

    # ═══════════════════════════════════════════
    # HEADER BAR
    # ═══════════════════════════════════════════
    header_h = 56
    cursor_y -= header_h
    draw_rounded_rect(c, margin, cursor_y, content_w, header_h, 6, fill=DARK_BG)

    # Logo — embed PNG image directly
    if LOGO_PATH.exists():
        logo_img = ImageReader(str(LOGO_PATH))
        print("logo_img=====================>", logo_img)
        logo_h = header_h - 12  # 44pt with 6pt padding top+bottom
        logo_w = logo_h * 3.64  # maintain aspect ratio ≈ 160pt
        c.drawImage(
            logo_img,
            margin + 10,
            cursor_y + 6,
            width=logo_w,
            height=logo_h,
            mask="auto",
        )
    else:
        # Fallback text if logo file is missing
        c.setFillColor(GREEN_LIGHT)
        c.setFont(FONT_BOLD, 20)
        c.drawString(margin + 16, cursor_y + 20, "RAILMIND")
        c.setFillColor(GRAY_400)
        c.setFont(FONT_REGULAR, 8)
        c.drawString(margin + 16, cursor_y + 9, "AI-POWERED RAILWAYS")

    # E-Ticket label (right side)
    c.setFillColor(WHITE)
    c.setFont(FONT_BOLD, 11)
    c.drawRightString(margin + content_w - 16, cursor_y + 32, "E-TICKET / RESERVATION")
    c.setFillColor(GRAY_400)
    c.setFont(FONT_REGULAR, 8)
    c.drawRightString(
        margin + content_w - 16, cursor_y + 20, f"Booked: {ticket['booked_at']}"
    )
    c.setFont(FONT_REGULAR, 7)
    c.drawRightString(
        margin + content_w - 16,
        cursor_y + 9,
        "This is a computer-generated document. No signature required.",
    )

    cursor_y -= 10

    # ═══════════════════════════════════════════
    # PNR + STATUS ROW
    # ═══════════════════════════════════════════
    row_h = 50
    cursor_y -= row_h
    draw_rounded_rect(
        c,
        margin,
        cursor_y,
        content_w,
        row_h,
        6,
        fill=GREEN_PALE,
        stroke=GREEN_PRIMARY,
        stroke_width=1,
    )

    c.setFillColor(GRAY_500)
    c.setFont(FONT_REGULAR, 8)
    c.drawString(margin + 14, cursor_y + 32, "PNR NUMBER")
    c.setFillColor(GRAY_900)
    c.setFont(FONT_BOLD, 18)
    c.drawString(margin + 14, cursor_y + 10, ticket["pnr_number"])

    status = ticket["booking_status"]
    status_color = (
        GREEN_PRIMARY
        if status == "CONFIRMED"
        else AMBER_STATUS if status == "WAITLISTED" else BLUE_INFO
    )
    draw_status_badge(c, margin + 220, cursor_y + 16, status, status_color)

    c.setFillColor(GRAY_500)
    c.setFont(FONT_REGULAR, 8)
    c.drawRightString(margin + content_w - 14, cursor_y + 32, "CLASS / QUOTA")
    c.setFillColor(GRAY_800)
    c.setFont(FONT_BOLD, 11)
    c.drawRightString(
        margin + content_w - 14,
        cursor_y + 14,
        f"{ticket['train_class']}  |  {ticket['quota']}",
    )

    cursor_y -= 10

    # ═══════════════════════════════════════════
    # JOURNEY SECTION
    # ═══════════════════════════════════════════
    section_h = 130
    cursor_y -= section_h
    draw_rounded_rect(
        c,
        margin,
        cursor_y,
        content_w,
        section_h,
        6,
        fill=WHITE,
        stroke=GRAY_200,
        stroke_width=0.5,
    )

    draw_rounded_rect(
        c, margin, cursor_y + section_h - 30, content_w, 30, 0, fill=GRAY_50
    )

    c.setFillColor(GRAY_800)
    c.setFont(FONT_BOLD, 11)
    c.drawString(
        margin + 14,
        cursor_y + section_h - 20,
        f"{ticket['train_number']}  —  {ticket['train_name']}",
    )
    c.setFillColor(GRAY_500)
    c.setFont(FONT_REGULAR, 8)
    c.drawRightString(
        margin + content_w - 14,
        cursor_y + section_h - 18,
        f"Journey Date: {ticket['journey_date']} ({ticket['journey_day']})",
    )

    route_y = cursor_y + 30
    left_x = margin + 40
    right_x = margin + content_w - 40
    mid_x = (left_x + right_x) / 2

    # Source
    c.setFillColor(GREEN_PRIMARY)
    c.circle(left_x, route_y + 30, 6, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.circle(left_x, route_y + 30, 3, fill=1, stroke=0)
    c.setFillColor(GRAY_900)
    c.setFont(FONT_BOLD, 16)
    c.drawString(left_x + 16, route_y + 25, ticket["source_station"])
    c.setFillColor(GRAY_500)
    c.setFont(FONT_REGULAR, 9)
    c.drawString(left_x + 16, route_y + 12, ticket["source_name"])
    c.setFillColor(GRAY_800)
    c.setFont(FONT_BOLD, 13)
    c.drawString(left_x + 16, route_y + 45, ticket["departure_time"])

    # Destination
    c.setFillColor(RED_STATUS)
    c.circle(right_x, route_y + 30, 6, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.circle(right_x, route_y + 30, 3, fill=1, stroke=0)
    c.setFillColor(GRAY_900)
    c.setFont(FONT_BOLD, 16)
    c.drawRightString(right_x - 16, route_y + 25, ticket["dest_station"])
    c.setFillColor(GRAY_500)
    c.setFont(FONT_REGULAR, 9)
    c.drawRightString(right_x - 16, route_y + 12, ticket["dest_name"])
    c.setFillColor(GRAY_800)
    c.setFont(FONT_BOLD, 13)
    arr_text = ticket["arrival_time"]
    if ticket.get("arrival_day"):
        arr_text += f"  ({ticket['arrival_day']})"
    c.drawRightString(right_x - 16, route_y + 45, arr_text)

    # Dashed connector
    c.setStrokeColor(GRAY_300)
    c.setLineWidth(1.5)
    c.setDash(4, 3)
    c.line(left_x + 10, route_y + 30, right_x - 10, route_y + 30)
    c.setDash()

    # Duration pill
    draw_rounded_rect(
        c,
        mid_x - 50,
        route_y + 20,
        100,
        22,
        11,
        fill=WHITE,
        stroke=GRAY_300,
        stroke_width=0.5,
    )
    c.setFillColor(GRAY_700)
    c.setFont(FONT_BOLD, 9)
    c.drawCentredString(
        mid_x, route_y + 26, f"{ticket['duration']}  |  {ticket['distance_km']} km"
    )

    c.setFillColor(GRAY_500)
    c.setFont(FONT_REGULAR, 8)
    c.drawString(
        left_x + 16,
        route_y - 2,
        f"Coach: {ticket['coach']}  |  Boarding: {ticket['boarding_station']}",
    )

    cursor_y -= 8

    # ═══════════════════════════════════════════
    # PASSENGER TABLE
    # ═══════════════════════════════════════════
    c.setFillColor(GRAY_800)
    c.setFont(FONT_BOLD, 10)
    cursor_y -= 16
    c.drawString(margin + 4, cursor_y, "PASSENGER DETAILS")
    cursor_y -= 6

    table_h = 22
    cursor_y -= table_h
    draw_rounded_rect(c, margin, cursor_y, content_w, table_h, 0, fill=GRAY_800)

    cols = [
        ("S.No", 28),
        ("Passenger Name", 120),
        ("Age/Gender", 58),
        ("Seat / Berth", 68),
        ("Status", 50),
        ("ID Type", 48),
        ("ID Number", 88),
        ("Fare", 55),
    ]
    c.setFillColor(WHITE)
    c.setFont(FONT_BOLD, 7.5)
    col_x = margin + 8
    for label, w in cols:
        c.drawString(col_x, cursor_y + 7, label)
        col_x += w

    for i, p in enumerate(ticket["passengers"]):
        row_h = 24
        cursor_y -= row_h
        bg = WHITE if i % 2 == 0 else GRAY_50
        draw_rounded_rect(c, margin, cursor_y, content_w, row_h, 0, fill=bg)

        col_x = margin + 8

        c.setFillColor(GRAY_600)
        c.setFont(FONT_REGULAR, 8)
        c.drawString(col_x, cursor_y + 8, str(i + 1))
        col_x += cols[0][1]

        c.setFillColor(GRAY_900)
        c.setFont(FONT_BOLD, 8)
        c.drawString(col_x, cursor_y + 8, p["name"])
        col_x += cols[1][1]

        c.setFont(FONT_REGULAR, 8)
        c.setFillColor(GRAY_700)
        c.drawString(col_x, cursor_y + 8, f"{p['age']} / {p['gender']}")
        col_x += cols[2][1]

        c.drawString(col_x, cursor_y + 8, p["seat"])
        col_x += cols[3][1]

        st_color = (
            GREEN_PRIMARY
            if p["status"] == "CNF"
            else AMBER_STATUS if p["status"] == "WL" else BLUE_INFO
        )
        draw_status_badge(c, col_x, cursor_y + 4, p["status"], st_color)
        col_x += cols[4][1]

        c.setFillColor(GRAY_600)
        c.setFont(FONT_REGULAR, 7.5)
        c.drawString(col_x, cursor_y + 8, p["id_type"])
        col_x += cols[5][1]

        c.drawString(col_x, cursor_y + 8, p["id_number"])
        col_x += cols[6][1]

        c.setFillColor(GRAY_800)
        c.setFont(FONT_BOLD, 8)
        c.drawRightString(col_x + cols[7][1] - 8, cursor_y + 8, f"Rs {p['fare']:,.2f}")

    c.setStrokeColor(GRAY_200)
    c.setLineWidth(0.5)
    c.line(margin, cursor_y, margin + content_w, cursor_y)

    cursor_y -= 14

    # ═══════════════════════════════════════════
    # FARE BREAKDOWN + QR CODE
    # ═══════════════════════════════════════════
    bottom_section_h = 155
    cursor_y -= bottom_section_h

    fare_w = content_w * 0.55
    qr_w = content_w * 0.45

    draw_rounded_rect(
        c,
        margin,
        cursor_y,
        fare_w - 6,
        bottom_section_h,
        6,
        fill=WHITE,
        stroke=GRAY_200,
        stroke_width=0.5,
    )

    c.setFillColor(GRAY_800)
    c.setFont(FONT_BOLD, 10)
    fy = cursor_y + bottom_section_h - 18
    c.drawString(margin + 14, fy, "FARE BREAKDOWN")
    fy -= 6
    c.setStrokeColor(GRAY_200)
    c.line(margin + 14, fy, margin + fare_w - 20, fy)

    fare_items = [
        ("Base Fare", ticket["fare_breakdown"]["base_fare"]),
        ("Reservation Charge", ticket["fare_breakdown"]["reservation_charge"]),
        ("Superfast Charge", ticket["fare_breakdown"]["superfast_charge"]),
        ("GST (5%)", ticket["fare_breakdown"]["gst"]),
        ("Travel Insurance", ticket["fare_breakdown"]["insurance"]),
    ]

    fy -= 16
    for label, amount in fare_items:
        c.setFillColor(GRAY_600)
        c.setFont(FONT_REGULAR, 8.5)
        c.drawString(margin + 14, fy, label)
        c.setFillColor(GRAY_800)
        c.setFont(FONT_REGULAR, 8.5)
        c.drawRightString(margin + fare_w - 20, fy, f"Rs {amount:,.2f}")
        fy -= 16

    fy -= 2
    c.setStrokeColor(GRAY_300)
    c.setLineWidth(0.5)
    c.line(margin + 14, fy + 10, margin + fare_w - 20, fy + 10)
    c.setFillColor(GRAY_900)
    c.setFont(FONT_BOLD, 11)
    c.drawString(margin + 14, fy - 4, "TOTAL")
    c.setFillColor(GREEN_DARK)
    c.setFont(FONT_BOLD, 13)
    c.drawRightString(
        margin + fare_w - 20,
        fy - 4,
        f"Rs {ticket['fare_breakdown']['total_fare']:,.2f}",
    )

    fy -= 20
    c.setFillColor(GRAY_500)
    c.setFont(FONT_REGULAR, 7)
    c.drawString(
        margin + 14,
        fy,
        f"Txn: {ticket['payment']['txn_id']}  |  "
        f"{ticket['payment']['method']}  |  {ticket['payment']['status']}",
    )

    # QR Code
    qr_x = margin + fare_w + 6
    draw_rounded_rect(
        c,
        qr_x,
        cursor_y,
        qr_w - 6,
        bottom_section_h,
        6,
        fill=GRAY_50,
        stroke=GRAY_200,
        stroke_width=0.5,
    )

    qr_data = (
        f"RAILMIND|PNR:{ticket['pnr_number']}|TRAIN:{ticket['train_number']}"
        f"|DATE:{ticket['journey_date']}|STATUS:{ticket['booking_status']}"
    )
    qr_buf = generate_qr(qr_data)
    qr_img = ImageReader(qr_buf)
    qr_size = 95
    qr_cx = qr_x + (qr_w - 6) / 2 - qr_size / 2
    qr_cy = cursor_y + bottom_section_h - qr_size - 20
    c.drawImage(qr_img, qr_cx, qr_cy, width=qr_size, height=qr_size)

    c.setFillColor(GRAY_700)
    c.setFont(FONT_BOLD, 8)
    c.drawCentredString(
        qr_x + (qr_w - 6) / 2, cursor_y + bottom_section_h - 14, "SCAN FOR VERIFICATION"
    )
    c.setFillColor(GRAY_500)
    c.setFont(FONT_REGULAR, 7)
    c.drawCentredString(qr_x + (qr_w - 6) / 2, qr_cy - 10, "Show this QR to the TTE")
    c.drawCentredString(
        qr_x + (qr_w - 6) / 2, qr_cy - 20, "along with a valid photo ID"
    )

    cursor_y -= 10

    # ═══════════════════════════════════════════
    # IMPORTANT INFORMATION
    # ═══════════════════════════════════════════
    info_h = 85
    cursor_y -= info_h
    draw_rounded_rect(
        c,
        margin,
        cursor_y,
        content_w,
        info_h,
        6,
        fill=HexColor("#FFFBEB"),
        stroke=HexColor("#FDE68A"),
        stroke_width=0.5,
    )

    c.setFillColor(HexColor("#92400E"))
    c.setFont(FONT_BOLD, 9)
    iy = cursor_y + info_h - 16
    c.drawString(margin + 14, iy, "IMPORTANT INFORMATION")
    iy -= 14

    notices = [
        "Carry a valid photo ID (Aadhaar / PAN / Passport / Voter ID) during the journey.",
        "E-ticket passengers must carry a printout of this ticket or show it on a mobile device.",
        "Chart status will be updated 4 hours before departure. Check PNR for final berth allotment.",
        "For cancellation, visit railmind.app/bookings or contact support at help@railmind.app.",
        "Partially confirmed e-tickets: only confirmed passengers should travel.",
    ]

    c.setFillColor(HexColor("#78350F"))
    c.setFont(FONT_REGULAR, 7)
    for notice in notices:
        c.drawString(margin + 14, iy, f"  {notice}")
        iy -= 11

    cursor_y -= 8

    # ═══════════════════════════════════════════
    # FOOTER
    # ═══════════════════════════════════════════
    footer_h = 28
    cursor_y -= footer_h
    draw_rounded_rect(c, margin, cursor_y, content_w, footer_h, 6, fill=GRAY_800)

    c.setFillColor(GRAY_400)
    c.setFont(FONT_REGULAR, 7)
    c.drawString(
        margin + 14,
        cursor_y + 10,
        "RailMind  |  AI-Powered Railway Reservation System  |  railmind.app  |  help@railmind.app",
    )
    c.drawRightString(
        margin + content_w - 14,
        cursor_y + 10,
        f"Passenger: {ticket['user']['name']}  |  {ticket['user']['phone']}",
    )

    c.save()
    print(f"PDF generated: {output_path}")


if __name__ == "__main__":
    build_ticket_pdf("railmind_eticket.pdf")

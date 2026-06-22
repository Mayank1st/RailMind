from uuid import UUID

from app.db.models.train import SeatInventories

BOOKINGS_URL = "/api/v1/bookings/"


async def test_list_bookings_requires_auth(client):
    """Without a logged-in user, the bookings endpoint is rejected (401)."""
    response = await client.get(BOOKINGS_URL)

    assert response.status_code == 401


async def test_list_bookings_empty_for_new_user(auth_client):
    """A freshly faked user has no bookings — a clean, empty list."""
    response = await auth_client.get(BOOKINGS_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == []
    assert body["meta"]["total"] == 0


async def test_create_booking_unknown_train_404(auth_client):
    """
    POST happy-path needs heavy seed data; here we only prove the write endpoint
    is reachable + authenticated. create_booking validates the train FIRST, so a
    non-existent train_number short-circuits to 404 before any seed is needed.
    """
    payload = {
        "train_number": "00000",  # does not exist in the (empty) test DB
        "journey_date": "2026-12-01",
        "from_station": "NDLS",
        "to_station": "BCT",
        "train_class": "SL",
        "quota": "GN",
        "passengers": [{"passenger_id": "11111111-1111-1111-1111-111111111111"}],
    }

    response = await auth_client.post(BOOKINGS_URL, json=payload)

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["errors"][0]["code"] == "RM-TRN-001"


async def test_create_waitlist_booking_happy_path(auth_client, booking_world):
    """Full happy path: a seeded journey with no confirmed/RAC seats produces a
    waitlisted booking with a PNR."""
    payload = {
        "train_number": booking_world["train_number"],
        "journey_date": booking_world["journey_date"],
        "from_station": booking_world["from_station"],
        "to_station": booking_world["to_station"],
        "train_class": booking_world["train_class"],
        "quota": booking_world["quota"],
        "passengers": [{"passenger_id": booking_world["passenger_id"]}],
    }

    response = await auth_client.post(BOOKINGS_URL, json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["availability"] == "WL"
    assert data["pnr_number"]
    assert data["passengers"][0]["passenger_status"] == "WL"


async def test_create_available_booking_confirms_seat(
    auth_client, available_world, db_session
):
    """With confirmed seats free, the passenger is allotted a real seat (CNF)
    and the inventory's confirmed counter drops by one."""
    payload = {
        "train_number": available_world["train_number"],
        "journey_date": available_world["journey_date"],
        "from_station": available_world["from_station"],
        "to_station": available_world["to_station"],
        "train_class": available_world["train_class"],
        "quota": available_world["quota"],
        "passengers": [{"passenger_id": available_world["passenger_id"]}],
    }

    response = await auth_client.post(BOOKINGS_URL, json=payload)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["availability"] == "AVAILABLE"
    passenger = data["passengers"][0]
    assert passenger["passenger_status"] == "CNF"
    assert passenger["seat_number"] is not None
    assert passenger["allotted_berth"] in ("LB", "UB")

    # Inventory decremented: 2 confirmed seats → 1 left after one booking.
    inventory = await db_session.get(
        SeatInventories, UUID(available_world["inventory_id"])
    )
    assert inventory.available_confirmed_seats == 1


async def test_last_seat_cannot_be_oversold(auth_client, single_seat_world, db_session):
    """The double-booking guard: with one confirmed seat, the first booking
    confirms it and the second must fall through to the waitlist — never a
    second confirmation on the same seat."""
    payload = {
        "train_number": single_seat_world["train_number"],
        "journey_date": single_seat_world["journey_date"],
        "from_station": single_seat_world["from_station"],
        "to_station": single_seat_world["to_station"],
        "train_class": single_seat_world["train_class"],
        "quota": single_seat_world["quota"],
        "passengers": [{"passenger_id": single_seat_world["passenger_id"]}],
    }

    first = await auth_client.post(BOOKINGS_URL, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["data"]["availability"] == "AVAILABLE"

    second = await auth_client.post(BOOKINGS_URL, json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["data"]["availability"] == "WL"

    # Only the one real seat was ever handed out.
    inventory = await db_session.get(
        SeatInventories, UUID(single_seat_world["inventory_id"])
    )
    assert inventory.available_confirmed_seats == 0

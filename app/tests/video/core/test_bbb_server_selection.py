import pytest

from eventyay.base.models import BBBCall, BBBServer, Event, Room
from eventyay.base.services.bbb import choose_server
from eventyay.features.live.exceptions import ConsumerException


@pytest.fixture
def event(db):
    return Event.objects.create(slug="test-event", name="Test Event", timezone="UTC")


@pytest.fixture
def room(event):
    return Room.objects.create(
        event=event,
        name="Test Room",
        module_config=[
            {
                "type": "call.bigbluebutton",
                "config": {},
            }
        ],
    )


@pytest.fixture
def clean_bbb_servers(db):
    BBBServer.objects.all().delete()


@pytest.mark.django_db
def test_prefer_server_active(event, room, clean_bbb_servers):
    server_a = BBBServer.objects.create(
        active=True, url="https://a.example.com", secret="secret_a", cost=50
    )
    BBBServer.objects.create(
        active=True, url="https://b.example.com", secret="secret_b", cost=10
    )

    server = choose_server(
        event=event, room=room, prefer_server="https://a.example.com"
    )
    assert server.pk == server_a.pk
    assert server.url == "https://a.example.com"


@pytest.mark.django_db
def test_prefer_server_inactive(event, room, clean_bbb_servers):
    BBBServer.objects.create(
        active=False, url="https://a.example.com", secret="secret_a", cost=10
    )
    BBBServer.objects.create(
        active=True, url="https://b.example.com", secret="secret_b", cost=50
    )

    with pytest.raises(ConsumerException) as exc_info:
        choose_server(event=event, room=room, prefer_server="https://a.example.com")

    assert exc_info.value.code == "bbb.prefer_server.unavailable"


@pytest.mark.django_db
def test_prefer_server_missing(event, room, clean_bbb_servers):
    BBBServer.objects.create(
        active=True, url="https://a.example.com", secret="secret_a", cost=10
    )
    BBBServer.objects.create(
        active=True, url="https://b.example.com", secret="secret_b", cost=50
    )

    with pytest.raises(ConsumerException) as exc_info:
        choose_server(event=event, room=room, prefer_server="https://c.example.com")

    assert exc_info.value.code == "bbb.prefer_server.unavailable"


@pytest.mark.django_db
def test_prefer_server_unset_fallback(event, room, clean_bbb_servers):
    server_a = BBBServer.objects.create(
        active=True, url="https://a.example.com", secret="secret_a", cost=10
    )
    BBBServer.objects.create(
        active=True, url="https://b.example.com", secret="secret_b", cost=50
    )

    server = choose_server(event=event, room=room, prefer_server=None)
    assert server.pk == server_a.pk
    assert server.url == "https://a.example.com"


@pytest.mark.django_db
def test_deterministic_selection_same_cost(event, room, clean_bbb_servers):
    BBBServer.objects.create(
        active=True, url="https://c.example.com", secret="secret_c", cost=10
    )
    BBBServer.objects.create(
        active=True, url="https://a.example.com", secret="secret_a", cost=10
    )
    BBBServer.objects.create(
        active=True, url="https://b.example.com", secret="secret_b", cost=10
    )

    server = choose_server(event=event, room=room, prefer_server=None)
    assert server.url == "https://a.example.com"


@pytest.mark.django_db
def test_no_servers_available(event, room, clean_bbb_servers):
    BBBServer.objects.create(
        active=False, url="https://a.example.com", secret="secret_a", cost=10
    )
    BBBServer.objects.create(
        active=False, url="https://b.example.com", secret="secret_b", cost=50
    )

    with pytest.raises(ConsumerException) as exc_info:
        choose_server(event=event, room=room, prefer_server=None)

    assert exc_info.value.code == "bbb.no_servers_available"


@pytest.mark.django_db
def test_no_servers_exist(event, room, clean_bbb_servers):
    with pytest.raises(ConsumerException) as exc_info:
        choose_server(event=event, room=room, prefer_server=None)

    assert exc_info.value.code == "bbb.no_servers_available"


@pytest.mark.django_db
def test_event_exclusive_server_preferred(event, room, clean_bbb_servers):
    other_event = Event.objects.create(
        slug="other-event", name="Other Event", timezone="UTC"
    )

    server_generic = BBBServer.objects.create(
        active=True,
        url="https://generic.example.com",
        secret="secret_generic",
        cost=10,
        event_exclusive=None,
    )
    server_exclusive = BBBServer.objects.create(
        active=True,
        url="https://exclusive.example.com",
        secret="secret_exclusive",
        cost=50,
        event_exclusive=event,
    )
    BBBServer.objects.create(
        active=True,
        url="https://other.example.com",
        secret="secret_other",
        cost=5,
        event_exclusive=other_event,
    )

    server = choose_server(event=event, room=room, prefer_server=None)
    assert server.pk == server_exclusive.pk


@pytest.mark.django_db
def test_prefer_server_respects_event_exclusive(event, room, clean_bbb_servers):
    other_event = Event.objects.create(
        slug="other-event", name="Other Event", timezone="UTC"
    )

    BBBServer.objects.create(
        active=True,
        url="https://a.example.com",
        secret="secret_a",
        cost=10,
        event_exclusive=other_event,
    )
    BBBServer.objects.create(
        active=True, url="https://b.example.com", secret="secret_b", cost=50
    )

    with pytest.raises(ConsumerException) as exc_info:
        choose_server(event=event, room=room, prefer_server="https://a.example.com")

    assert exc_info.value.code == "bbb.prefer_server.unavailable"


@pytest.mark.django_db
def test_cost_increment_for_load_balancing(event, room, clean_bbb_servers):
    server_a = BBBServer.objects.create(
        active=True, url="https://a.example.com", secret="secret_a", cost=10
    )
    BBBServer.objects.create(
        active=True, url="https://b.example.com", secret="secret_b", cost=10
    )

    choose_server(event=event, room=room, prefer_server=None)

    server_a.refresh_from_db()
    assert server_a.cost == 20


@pytest.mark.django_db
def test_no_cost_increment_for_single_server(event, room, clean_bbb_servers):
    server_a = BBBServer.objects.create(
        active=True, url="https://a.example.com", secret="secret_a", cost=10
    )

    choose_server(event=event, room=room, prefer_server=None)

    server_a.refresh_from_db()
    assert server_a.cost == 10


@pytest.mark.django_db
def test_choose_server_without_room(event, clean_bbb_servers):
    server_a = BBBServer.objects.create(
        active=True,
        url="https://a.example.com",
        secret="secret_a",
        cost=10,
        rooms_only=False,
    )
    BBBServer.objects.create(
        active=True,
        url="https://b.example.com",
        secret="secret_b",
        cost=50,
        rooms_only=True,  
    )

    server = choose_server(event=event, room=None, prefer_server=None)
    assert server.pk == server_a.pk


@pytest.mark.django_db
def test_relevant_cost_based_on_event_usage(event, room, clean_bbb_servers):
    other_event = Event.objects.create(
        slug="other-event", name="Other Event", timezone="UTC"
    )
    other_room = Room.objects.create(
        event=other_event,
        name="Other Room",
        module_config=[{"type": "call.bigbluebutton", "config": {}}],
    )

    server_a = BBBServer.objects.create(
        active=True, url="https://a.example.com", secret="secret_a", cost=10
    )
    server_b = BBBServer.objects.create(
        active=True, url="https://b.example.com", secret="secret_b", cost=10
    )

    for _ in range(3):
        BBBCall.objects.create(
            room=room,
            event=event,
            server=server_b,
        )

    for _ in range(5):
        BBBCall.objects.create(
            room=other_room,
            event=other_event,
            server=server_a,
        )

    server = choose_server(event=event, room=room, prefer_server=None)
    assert server.pk == server_a.pk
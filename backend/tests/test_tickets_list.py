"""Ticket listing: filters, search and pagination."""

import pytest

from app.models import Priority, Status
from tests.conftest import auth


def ids(response):
    assert response.status_code == 200, response.text
    return [t["id"] for t in response.json()["items"]]


def test_pagination_metadata_and_pages_do_not_overlap(client, alice, sam, make_ticket):
    created = [make_ticket(alice, title=f"Ticket {i}") for i in range(12)]
    p1 = client.get("/api/tickets", headers=auth(sam), params={"page": 1, "page_size": 5}).json()
    p3 = client.get("/api/tickets", headers=auth(sam), params={"page": 3, "page_size": 5}).json()
    assert (p1["total"], p1["pages"], len(p1["items"])) == (12, 3, 5)
    assert len(p3["items"]) == 2

    all_ids = []
    for page in (1, 2, 3):
        all_ids += ids(client.get("/api/tickets", headers=auth(sam), params={"page": page, "page_size": 5}))
    assert sorted(all_ids) == sorted(t.id for t in created)  # every ticket exactly once
    assert all_ids == sorted(all_ids, reverse=True)  # newest first


def test_page_past_the_end_is_empty_not_an_error(client, alice, sam, make_ticket):
    make_ticket(alice)
    r = client.get("/api/tickets", headers=auth(sam), params={"page": 50})
    assert ids(r) == [] and r.json()["total"] == 1


def test_filter_by_status_and_priority(client, alice, sam, make_ticket):
    hit = make_ticket(alice, status=Status.IN_PROGRESS, priority=Priority.HIGH)
    make_ticket(alice, status=Status.IN_PROGRESS, priority=Priority.LOW)
    make_ticket(alice, status=Status.OPEN, priority=Priority.HIGH)
    r = client.get("/api/tickets", headers=auth(sam), params={"status": "in_progress", "priority": "high"})
    assert ids(r) == [hit.id]


def test_filter_by_assignee(client, alice, sam, priya, make_ticket):
    mine = make_ticket(alice, assignee=sam)
    theirs = make_ticket(alice, assignee=priya)
    nobody = make_ticket(alice)
    assert ids(client.get("/api/tickets", headers=auth(sam), params={"assignee": "me"})) == [mine.id]
    assert ids(client.get("/api/tickets", headers=auth(sam), params={"assignee": "unassigned"})) == [nobody.id]
    assert ids(client.get("/api/tickets", headers=auth(sam), params={"assignee": str(priya.id)})) == [theirs.id]


def test_search_is_case_insensitive_over_title_and_description(client, alice, sam, make_ticket):
    by_title = make_ticket(alice, title="VPN keeps dropping")
    by_desc = make_ticket(alice, title="Network", description="The vpn client crashes")
    make_ticket(alice, title="Printer", description="Paper jam")
    assert sorted(ids(client.get("/api/tickets", headers=auth(sam), params={"q": "VpN"}))) == sorted(
        [by_title.id, by_desc.id]
    )


def test_search_treats_wildcards_literally(client, alice, sam, make_ticket):
    hit = make_ticket(alice, title="Discount shows 50% off")
    make_ticket(alice, title="Discount shows 500 off")
    assert ids(client.get("/api/tickets", headers=auth(sam), params={"q": "50%"})) == [hit.id]


@pytest.mark.parametrize(
    "params",
    [{"page": 0}, {"page_size": 0}, {"page_size": 101}, {"status": "closed"}, {"priority": "urgent"}, {"assignee": "bob"}],
)
def test_invalid_query_params_are_rejected(client, sam, params):
    r = client.get("/api/tickets", headers=auth(sam), params=params)
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"

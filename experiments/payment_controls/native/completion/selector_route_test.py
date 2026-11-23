import asyncio
import json
from unittest.mock import AsyncMock, Mock

from experiments.payment_controls.native.completion.selector_route import follow_once


def test_acted_upstream_and_same_turn_retry_cannot_dispatch():
    client = AsyncMock()
    state = {"claimed": False, "upstream_attempts": 1}
    assert asyncio.run(follow_once(state, client, "/vendor/api/v1", "not classified")) == {
        "decision": "stock_already_attempted"}
    assert asyncio.run(follow_once(state, client, "/vendor/api/v1", "not classified")) == {
        "decision": "same_turn_already_handled"}
    client.get.assert_not_called()
    client.post.assert_not_called()


def test_selected_profile_must_appear_in_session_vendor_list():
    from experiments.payment_controls.native.completion import selector_route

    case = json.loads((selector_route.HERE / "process_chat_inputs.json").read_text())["cases"][0]
    client = AsyncMock()
    client.get.return_value = Mock(**{"json.return_value": {"current_vendor_id": 1, "vendors": [{"id": 2}]}})
    state = {"claimed": False, "upstream_attempts": 0}
    result = asyncio.run(follow_once(state, client, "/vendor/api/v1", case["message"]))
    assert result["decision"] == "no_bound_vendor"
    client.post.assert_not_called()

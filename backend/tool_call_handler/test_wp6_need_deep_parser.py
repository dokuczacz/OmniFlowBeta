import tool_call_handler as tch


def test_parse_need_deep_json_first_line_strips_header():
    text = (
        '{"need_deep":true,"missing":["TM.json"],"why":"need tasks","confidence":0.72,"deep_plan":["read-tm"]}\n'
        "Human answer starts here."
    )
    signal, cleaned = tch._wp6_parse_need_deep_signal(text)
    assert signal["parse_status"] == "json"
    assert signal["need_deep"] is True
    assert signal["missing"] == ["TM.json"]
    assert signal["why"] == "need tasks"
    assert abs(signal["confidence"] - 0.72) < 1e-6
    assert signal["deep_plan"] == ["read-tm"]
    assert cleaned == "Human answer starts here."


def test_parse_need_deep_token_fallback():
    text = "Some answer\n__ROUTE_DEEP__\nMore text"
    signal, cleaned = tch._wp6_parse_need_deep_signal(text)
    assert signal["parse_status"] == "token"
    assert signal["need_deep"] is True
    assert cleaned == text


def test_parse_need_deep_none():
    text = "Just a normal answer."
    signal, cleaned = tch._wp6_parse_need_deep_signal(text)
    assert signal["parse_status"] == "none"
    assert signal["need_deep"] is False
    assert cleaned == text


def test_parse_need_deep_does_not_strip_unrelated_json():
    text = '{"foo": "bar"}\nStill normal answer.'
    signal, cleaned = tch._wp6_parse_need_deep_signal(text)
    assert signal["parse_status"] == "none"
    assert signal["need_deep"] is False
    assert cleaned == text


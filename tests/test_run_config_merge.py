from run import _deep_merge


def test_deep_merge_adds_new_keys():
    base = {"a": 1, "nested": {"x": 1}}
    overlay = {"b": 2, "nested": {"y": 2}}
    result = _deep_merge(base, overlay)
    assert result == {"a": 1, "b": 2, "nested": {"x": 1, "y": 2}}


def test_deep_merge_overlay_wins_on_conflict():
    base = {"model": {"default": "old-model"}}
    overlay = {"model": {"default": "new-model"}}
    result = _deep_merge(base, overlay)
    assert result == {"model": {"default": "new-model"}}


def test_deep_merge_list_values_replaced_not_merged():
    base = {"platform_toolsets": {"cli": ["memory"]}}
    overlay = {"platform_toolsets": {"cli": ["memory", "mcp-trade-compliance"]}}
    result = _deep_merge(base, overlay)
    assert result["platform_toolsets"]["cli"] == ["memory", "mcp-trade-compliance"]

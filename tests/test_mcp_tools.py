"""In-process smoke tests of the MCP tool surface (FastMCP layer included:
argument validation, output schema generation, structured content)."""
import pytest

from hubgentic.server.mcp_server import mcp

EXPECTED_TOOLS = {
    "list_ontology",
    "describe_entity",
    "resolve_entity",
    "get_unified_entity",
    "explain_lineage",
}


async def test_five_tools_with_output_schemas():
    tools = await mcp.list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS
    for tool in tools:
        assert tool.outputSchema is not None, f"{tool.name} lacks an output schema"
        assert tool.description


async def test_list_ontology():
    _, structured = await mcp.call_tool("list_ontology", {})
    assert structured["name"] == "financial-services-core"
    assert [e["name"] for e in structured["entities"]] == ["Counterparty"]
    assert {s["id"] for s in structured["sources"]} == {"core_banking", "crm"}


async def test_describe_entity():
    _, structured = await mcp.call_tool(
        "describe_entity", {"entity_type": "Counterparty"}
    )
    assert structured["attributes"]["lei"]["identifying"] is True
    sources = [b["source"] for b in structured["bindings"]]
    assert sources == ["core_banking", "crm"]  # merge-preference order
    assert structured["bindings"][0]["fields"]["legal_name"] == "NAME_TXT"


async def test_resolve_entity_returns_rules():
    _, structured = await mcp.call_tool(
        "resolve_entity",
        {
            "entity_type": "Counterparty",
            "criteria": {"national_tax_code": "IT01234567890"},
        },
    )
    assert len(structured["clusters"]) == 1
    [match] = structured["clusters"][0]["supporting_matches"]
    assert match["rule"] == "deterministic.tax_code"
    assert match["decision"] == "match"


async def test_get_unified_entity_carries_provenance():
    _, structured = await mcp.call_tool(
        "get_unified_entity",
        {
            "entity_type": "Counterparty",
            "criteria": {"legal_name": "Lucia Bianchi"},
        },
    )
    assert structured["entity_type"] == "Counterparty"
    for values in structured["fields"].values():
        for pv in values:
            provenance = pv["provenance"]
            for key in (
                "source",
                "source_object",
                "source_key",
                "source_field",
                "fetched_at",
                "resolution_rule",
                "resolution_confidence",
            ):
                assert key in provenance, f"provenance missing {key}"


async def test_explain_lineage_roundtrip():
    _, unified = await mcp.call_tool(
        "get_unified_entity",
        {
            "entity_type": "Counterparty",
            "criteria": {"national_tax_code": "IT01234567890"},
        },
    )
    _, explanation = await mcp.call_tool(
        "explain_lineage", {"request_id": unified["request_id"]}
    )
    assert explanation["request_id"] == unified["request_id"]
    assert "UnifiedEntity Counterparty" in explanation["rendered"]
    assert "rule=" in explanation["rendered"]
    assert "GREENFIELD" in explanation["rendered"]  # relationship in the tree


async def test_explain_lineage_recompute_fallback():
    _, explanation = await mcp.call_tool(
        "explain_lineage",
        {
            "request_id": "expired0000",
            "entity_type": "Counterparty",
            "criteria": {"national_tax_code": "IT01234567890"},
        },
    )
    assert "legal_name" in explanation["fields"]


async def test_unknown_entity_is_a_clean_tool_error():
    with pytest.raises(Exception, match="unknown entity type"):
        await mcp.call_tool("describe_entity", {"entity_type": "Instrument"})

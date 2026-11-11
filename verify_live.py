"""Exercise the actual stdio MCP server against a new NVivo 15 project file."""
import asyncio
import os
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent


async def main():
    project = "verification_" + uuid.uuid4().hex[:10] + ".nvp"
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")], env=dict(os.environ))
    calls = []
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()

            async def call(tool_name, **arguments):
                response = await session.call_tool(tool_name, arguments)
                if response.is_error:
                    raise RuntimeError(tool_name + " " + str(response.content))
                value = response.structured_content
                if value is None:
                    value = json.loads(response.content[0].text)
                # FastMCP wraps non-object return annotations in a result field.
                if isinstance(value, dict) and list(value) == ["result"]:
                    value = value["result"]
                calls.append(tool_name)
                return value

            initial = await call("nvivo_create_project", project=project, title="编码过程验证")
            assert initial["sources"] == initial["codes"] == initial["coding_references"] == 0, initial
            text = "原文材料。\n补充说明😀，再次阅读原文材料。"
            source = await call("nvivo_import_text", project=project, name="材料验证", text=text)
            parent = await call("nvivo_add_code", project=project, name="归并类别", description="归纳后的类别")
            code = await call("nvivo_add_code", project=project, name="初始代码", description="由原文提取的描述", parent_id=parent["id"])
            code_tree = (await call("nvivo_list_codes", project=project))["codes"]
            assert next(c for c in code_tree if c["id"].lower() == code["id"])["parent_id"].lower() == parent["id"]
            coding = await call("nvivo_code_text", project=project, source_id=source["id"], code_id=code["id"], quote="原文材料", occurrence=1)
            repeated = await call("nvivo_code_text", project=project, source_id=source["id"], code_id=code["id"], quote="原文材料", occurrence=1)
            assert repeated["id"] == coding["id"] and repeated["created"] is False
            memo = await call("nvivo_add_coding_memo", project=project, name="编码过程", text="原文材料形成初始代码，再归入归并类别。本段用于验证编码演进记录的保存。")
            before = (await call("nvivo_read_codings", project=project))["codings"]
            assert len(before) == 1 and before[0]["quote"] == "原文材料", before
            saved = await call("nvivo_checkpoint", project=project)
            assert saved["integrity"] == "passed" and saved["detached"]
            reopened = await call("nvivo_inspect_project", project=project)
            after = (await call("nvivo_read_codings", project=project))["codings"]
            source_readback = await call("nvivo_read_source", project=project, source_id=source["id"])
            memo_readback = await call("nvivo_read_source", project=project, source_id=memo["id"])
            assert after == before
            assert source_readback["text"].replace("\r\n", "\n").rstrip("\n") == text
            assert "形成初始代码" in memo_readback["text"]
            assert reopened["sources"] == 2 and reopened["codes"] == 2 and reopened["coding_references"] == 1
            final_save = await call("nvivo_checkpoint", project=project)
    report = dict(status="passed", verified_at=datetime.now(timezone.utc).isoformat(), transport="MCP stdio", tools=[t.name for t in tools.tools], calls=calls, project=project, native_version=reopened["native_version"], initial=initial, final=reopened, save=final_save, checks={"native_empty_project": True, "native_document_import": True, "code_hierarchy": True, "exact_quote_after_supplementary_unicode": True, "idempotent_coding_retry": True, "coding_development_memo": True, "detach_and_reattach": True, "text_and_coding_readback": True, "native_project_service_reopen": True}, verification_scope="NVivo ProjectService native creation, import, reopen and service-level readback through MCP stdio")
    (ROOT / "results/native_mcp_acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

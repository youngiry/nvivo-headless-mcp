"""NVivo headless MCP server. Run with the configured Python interpreter."""
from mcp.server.mcpserver import MCPServer
import backend

mcp = MCPServer("NVivo Headless")


@mcp.tool()
def nvivo_create_project(project: str, title: str, template_path: str = "", empty: bool = True) -> dict:
    """Create a managed native .nvp working copy inside NVIVO_WORKSPACE."""
    return backend.create_project(project, title, template_path, empty)


@mcp.tool()
def nvivo_inspect_project(project: str) -> dict:
    """Read native project version and current material, code and coding counts."""
    return backend.inspect_project(project)


@mcp.tool()
def nvivo_list_sources(project: str) -> dict:
    """List document and memo IDs with readable native names."""
    return {"sources": backend.list_sources(project)}


@mcp.tool()
def nvivo_read_source(project: str, source_id: str) -> dict:
    """Read the complete stored text of a native source or coding memo."""
    return backend.read_source(project, source_id)


@mcp.tool()
def nvivo_list_codes(project: str) -> dict:
    """List native codes and their definitions."""
    return {"codes": backend.list_codes(project)}


@mcp.tool()
def nvivo_add_code(project: str, name: str, description: str = "", parent_id: str = "") -> dict:
    """Create a native code, optionally under an existing parent code."""
    return backend.add_code(project, name, description, parent_id)


@mcp.tool()
def nvivo_import_text(project: str, name: str, text: str, description: str = "") -> dict:
    """Import text through NVivo native project services on a background desktop."""
    return backend.import_text(project, name, text, description)


@mcp.tool()
def nvivo_add_coding_memo(project: str, name: str, text: str) -> dict:
    """Preserve documented coding development, category decisions and revisions as a memo."""
    return backend.import_text(project, name, text, memo=True)


@mcp.tool()
def nvivo_code_text(project: str, source_id: str, code_id: str, quote: str, occurrence: int = 0) -> dict:
    """Code an exact source quote. Retries preserve one identical coding reference."""
    return backend.code_text(project, source_id, code_id, quote, occurrence)


@mcp.tool()
def nvivo_read_codings(project: str) -> dict:
    """Read back stored source-to-code links and exact selected text."""
    return {"codings": backend.read_codings(project)}


@mcp.tool()
def nvivo_sync_coding(project: str, bundle: dict) -> dict:
    """Synchronize sources, ordered parent/child codes, exact quote codings and coding-process memos from a JSON bundle."""
    return backend.sync_coding(project, bundle)


@mcp.tool()
def nvivo_checkpoint(project: str) -> dict:
    """Reopen with NVivo itself, validate document and coding state, then close the saved .nvp."""
    return backend.checkpoint(project)


@mcp.tool()
def nvivo_doctor() -> dict:
    """Check installed runtime prerequisites without changing projects."""
    import doctor
    return doctor.check()


if __name__ == "__main__":
    mcp.run(transport="stdio")

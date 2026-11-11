"""Headless access to managed NVivo Windows project copies.

Projects are created, imported and read using the installed NVivo runtime.
LocalDB access is limited to finding and detaching this adapter's own connection.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import uuid

import pyodbc
import native_bridge

os.environ.setdefault("WINDIR", os.environ.get("SystemRoot", "C:\\Windows"))
pyodbc.pooling = False
ROOT = Path(__file__).resolve().parent
(ROOT / "results").mkdir(exist_ok=True)
WORKSPACE = Path(os.environ.get("NVIVO_WORKSPACE", ROOT / "workspace")).resolve()
INSTANCE = os.environ.get("NVIVO_LOCALDB_INSTANCE", "QSRNVivo20.6")
LOCALDB = Path(os.environ.get("NVIVO_LOCALDB_EXE", "C:/Program Files/Microsoft SQL Server/150/Tools/Binn/SqlLocalDB.exe"))
INSTALL = Path(os.environ.get("NVIVO_INSTALL_DIR", "C:/Program Files/Lumivero/NVivo 15"))
LOCK = threading.RLock()
NO_WINDOW = subprocess.CREATE_NO_WINDOW
PIPE = None


def utf16_length(text):
    return len(text.encode("utf-16-le")) // 2


def native_text(text):
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")


def managed_path(project):
    path = (WORKSPACE / project).resolve()
    if not path.is_relative_to(WORKSPACE) or path.suffix.lower() != ".nvp":
        raise ValueError("Project must be an .nvp file inside the configured workspace")
    return path


def marker(path):
    return path.with_suffix(".managed.json")


def database_name(path):
    return "NvivoMcp_" + hashlib.sha256(str(path).lower().encode()).hexdigest()[:16]


def connection(database="master", autocommit=False, refresh=True):
    global PIPE
    if PIPE is None:
        subprocess.run([str(LOCALDB), "start", INSTANCE], capture_output=True, check=True, creationflags=NO_WINDOW, timeout=20)
        info = subprocess.check_output([str(LOCALDB), "info", INSTANCE], creationflags=NO_WINDOW).decode(errors="replace")
        match = re.search(r"np:[^\r\n]+", info)
        if not match:
            raise RuntimeError("LocalDB did not return a named pipe")
        PIPE = match.group()
    try:
        return pyodbc.connect("DRIVER={SQL Server};SERVER=" + PIPE + ";DATABASE=" + database + ";Trusted_Connection=yes;", autocommit=autocommit, timeout=15)
    except pyodbc.OperationalError:
        PIPE = None
        if refresh:
            return connection(database, autocommit, refresh=False)
        raise


def create_project(project, title, template_path="", empty=True):
    path = managed_path(project)
    if path.exists() or marker(path).exists():
        raise FileExistsError("Choose a new project filename")
    path.parent.mkdir(parents=True, exist_ok=True)
    marker(path).write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(), "native_creation": True, "title": title}, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        if template_path:
            if empty:
                raise ValueError("Use native empty creation or copy an existing project with empty=false")
            shutil.copy2(Path(template_path), path)
        else:
            native_bridge.run_native("create", path, ROOT / "results" / (path.stem + "_create.json"), title)
        return inspect_project(project)
    except BaseException:
        marker(path).write_text(json.dumps({"status": "creation_failed", "native_creation": True}, ensure_ascii=False), encoding="utf-8")
        raise


def native_state(project):
    path = managed_path(project)
    if not marker(path).is_file():
        raise ValueError("Create a managed project first")
    with LOCK:
        master = connection(autocommit=True)
        try:
            aliases = master.execute("SELECT DB_NAME(database_id) FROM sys.master_files WHERE physical_name=? AND file_id=1", str(path)).fetchall()
            for alias in aliases:
                if alias[0] != database_name(path):
                    raise RuntimeError("Project is open in another NVivo connection")
                master.execute("EXEC master.dbo.sp_detach_db @dbname=?", alias[0])
        finally:
            master.close()
        output = ROOT / "results" / (database_name(path) + "_native.json")
        native_bridge.run_native("verify", path, output)
        return json.loads(output.read_text(encoding="utf-8"))


def snapshot_bundle(project):
    state = native_state(project)
    sources, memos, codes = [], [], []
    for source in state["sources"]:
        entry = {"name": source["name"], "text": source["text"], "description": source.get("description", "") or ""}
        if source.get("linked_memo"):
            entry["memo"] = source["linked_memo"]
        (memos if "Memo" in source.get("type", "") else sources).append(entry)
    custom = [n for n in state["nodes"] if n["type"] == "ThematicNode"]
    names = {n["name"] for n in custom}
    for node in sorted(custom, key=lambda n: n["hierarchy"].count("\\")):
        entry = {"name": node["name"], "description": node.get("description", "") or ""}
        parts = [part for part in node["hierarchy"].split("\\") if part]
        if len(parts) > 1 and parts[-2] in names:
            entry["parent"] = parts[-2]
        if node.get("linked_memo"):
            entry["memo"] = node["linked_memo"]
        codes.append(entry)
    cases = []
    for node in state["nodes"]:
        if node["type"] == "Case":
            entry = {"name": node["name"], "description": node.get("description", "") or "",
                     "attributes": node.get("attributes", {})}
            if node.get("linked_memo"):
                entry["memo"] = node["linked_memo"]
            cases.append(entry)
    texts = {s["name"]: s["text"] for s in sources + memos}
    codings = []
    for ref in state["references"]:
        text = texts[ref["source"]]
        prefix = text.encode("utf-16-le")[:ref["start"] * 2].decode("utf-16-le")
        quote = ref["text"]
        occurrence = sum(1 for m in re.finditer("(?=" + re.escape(quote) + ")", text) if m.start() < len(prefix))
        codings.append({"source": ref["source"], "code": ref["node"], "quote": quote, "occurrence": occurrence})
    return {"sources": sources, "memos": memos, "codes": codes, "cases": cases, "codings": codings}


def validate_native_state(bundle, state):
    def normalized(text):
        return text.replace("\r\n", "\n").replace("\r", "\n")
    def canonical(text):
        return normalized(text).rstrip("\n")
    actual_sources = {s["name"]: s["text"] for s in state["sources"]}
    for document in bundle.get("sources", []) + bundle.get("memos", []):
        if document["name"] not in actual_sources or canonical(document["text"]) != canonical(actual_sources[document["name"]]):
            raise ValueError("NVivo native text readback differs: " + document["name"])
    nodes = {n["name"] for n in state["nodes"] if n["type"] == "ThematicNode"}
    if nodes != {c["name"] for c in bundle.get("codes", [])}:
        raise ValueError("NVivo native code readback differs")
    documents = bundle.get("sources", []) + bundle.get("memos", [])
    if set(actual_sources) != {d["name"] for d in documents}:
        raise ValueError("Native document inventory differs")
    by_name = {n["name"]: n for n in state["nodes"] if n["type"] == "ThematicNode"}
    for code in bundle.get("codes", []):
        parts = [p for p in by_name[code["name"]]["hierarchy"].split("\\") if p]
        parent = parts[-2] if len(parts) > 1 and parts[-2] in nodes else ""
        if parent != code.get("parent", ""):
            raise ValueError("Native code hierarchy differs: " + code["name"])
    actual_cases = {n["name"]: n for n in state["nodes"] if n["type"] == "Case"}
    if set(actual_cases) != {c["name"] for c in bundle.get("cases", [])}:
        raise ValueError("Native case inventory differs")
    for case in bundle.get("cases", []):
        if actual_cases[case["name"]].get("attributes", {}) != case.get("attributes", {}):
            raise ValueError("Native case attributes differ")
    all_nodes = {n["name"]: n for n in state["nodes"]}
    for item in bundle.get("codes", []) + bundle.get("cases", []):
        if item.get("memo") and all_nodes[item["name"]].get("linked_memo") != item["memo"]:
            raise ValueError("Native analysis memo link differs")
    expected_intervals = {}
    for coding in bundle.get("codings", []):
        text = normalized(actual_sources[coding["source"]])
        quote = normalized(coding["quote"])
        position = -1
        for _ in range(coding.get("occurrence", 0) + 1):
            position = text.find(quote, position + 1)
        if position < 0:
            raise ValueError("Native source quote is missing")
        start = utf16_length(text[:position])
        limit = utf16_length(text.rstrip("\n"))
        expected_intervals.setdefault((coding["source"], coding["code"]), []).append((start, min(start + utf16_length(quote), limit)))
    actual_intervals = {}
    for reference in state["references"]:
        text = actual_sources[reference["source"]]
        prefix = text.encode("utf-16-le")[:reference["start"] * 2].decode("utf-16-le")
        start = utf16_length(normalized(prefix))
        end = min(start + utf16_length(normalized(reference["text"])), utf16_length(canonical(text)))
        actual_intervals.setdefault((reference["source"], reference["node"]), []).append((start, end))
    def merged(intervals):
        result = []
        for start, end in sorted(intervals):
            if result and start <= result[-1][1]:
                result[-1] = (result[-1][0], max(result[-1][1], end))
            else:
                result.append((start, end))
        return result
    if {key: merged(value) for key, value in expected_intervals.items()} != {key: merged(value) for key, value in actual_intervals.items()}:
        raise ValueError("NVivo native coding coverage differs")
    return {"native_open_verified": True, "all_document_text_matches": True, "all_code_names_match": True, "all_code_hierarchy_matches": True, "all_coding_coverage_matches": True, "native_documents": len(state["sources"]), "native_custom_codes": len(nodes), "native_coding_references": len(state["references"])}


def sync_coding(project, bundle):
    """Import through NVivo's converter and project services, then reopen natively."""
    with LOCK:
        current = snapshot_bundle(project)
        merged_bundle = {}
        for kind in ("sources", "memos", "codes", "cases"):
            by_name = {item["name"]: item for item in current[kind]}
            for item in bundle.get(kind, []):
                existing = by_name.get(item["name"])
                if existing and kind in ("sources", "memos") and native_text(existing["text"]).rstrip("\r\n") != native_text(item["text"]).rstrip("\r\n"):
                    raise ValueError("Existing material has different text: " + item["name"])
                by_name[item["name"]] = item
            merged_bundle[kind] = list(by_name.values())
        refs = {(c["source"], c["code"], native_text(c["quote"]), c.get("occurrence", 0)): c for c in current["codings"] + bundle.get("codings", [])}
        merged_bundle["codings"] = list(refs.values())
        path = managed_path(project)
        title = inspect_project(project)["title"]
        work = WORKSPACE / "native_runs" / uuid.uuid4().hex
        work.mkdir(parents=True)
        package, xml, candidate, readback = [work / name for name in ("project.qdpx", "project.xml", "project.nvp", "readback.json")]
        native_bridge.package_bundle(merged_bundle, package, title)
        native_bridge.convert_package(package, xml)
        native_bridge.run_native("build", candidate, xml, title)
        native_bridge.run_native("verify", candidate, readback)
        proof = validate_native_state(merged_bundle, json.loads(readback.read_text(encoding="utf-8")))
        # Preserve the last native file and replace only after native reopen succeeds.
        backup = work / "previous.nvp"
        shutil.copy2(path, backup)
        old_log = path.with_name(path.stem + "_log.ldf")
        if old_log.exists():
            os.replace(old_log, work / "previous_log.ldf")
        os.replace(candidate, path)
        path.with_suffix(".coding.json").write_text(json.dumps(merged_bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"project": project, "sources_synced": len(merged_bundle["sources"]), "memos_synced": len(merged_bundle["memos"]), "codes_synced": len(merged_bundle["codes"]), "coding_entries_synced": len(merged_bundle["codings"]), "native_validation": proof, "current": inspect_project(project)}


def inspect_project(project):
    state = native_state(project)
    return {"path": str(managed_path(project)), "title": state["project_title"], "sources": len(state["sources"]), "codes": sum(n["type"] == "ThematicNode" for n in state["nodes"]), "coding_references": len(state["references"]), "headless": True, "native_open_verified": True, "native_version": "20.x / NVivo 15.6.1.3 runtime"}


def item_id(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "nvivo-item/" + name))


def list_sources(project):
    return [{"id": item_id(s["name"]), "name": s["name"], "text_units": utf16_length(s["text"]), "item_type": 3 if "Memo" in s.get("type", "") else 2} for s in native_state(project)["sources"]]


def read_source(project, source_id):
    for s in native_state(project)["sources"]:
        if item_id(s["name"]) == source_id:
            return {"id": source_id, "name": s["name"], "text": s["text"]}
    raise ValueError("Source ID was not found")


def list_codes(project):
    bundle = snapshot_bundle(project)
    return [{"id": item_id(c["name"]), "name": c["name"], "description": c["description"], "parent_id": item_id(c["parent"]) if c.get("parent") else ""} for c in bundle["codes"]]


def read_codings(project):
    return [{"source_id": item_id(r["source"]), "source_name": r["source"], "code_id": item_id(r["node"]), "code_name": r["node"], "start": r["start"], "length": r["length"], "quote": r["text"]} for r in native_state(project)["references"]]


def add_code(project, name, description="", parent_id=""):
    existing = next((c for c in list_codes(project) if c["name"] == name), None)
    if existing and (existing["description"] != description or existing["parent_id"] != parent_id):
        raise ValueError("Existing code has a different definition or parent")
    entry = {"name": name, "description": description}
    if parent_id:
        entry["parent"] = next(c["name"] for c in list_codes(project) if c["id"] == parent_id)
    result = sync_coding(project, {"codes": [entry]})
    return {"id": item_id(name), "name": name, "created": existing is None, "native_validation": result["native_validation"]}


def import_text(project, name, text, description="", memo=False):
    existing = any(s["name"] == name for s in list_sources(project))
    result = sync_coding(project, {"memos" if memo else "sources": [{"name": name, "text": text, "description": description}]})
    return {"id": item_id(name), "name": name, "created": not existing, "native_validation": result["native_validation"]}


def code_text(project, source_id, code_id, quote, occurrence=0):
    source = next(s["name"] for s in list_sources(project) if s["id"] == source_id)
    code = next(c["name"] for c in list_codes(project) if c["id"] == code_id)
    if not quote or occurrence < 0:
        raise ValueError("Provide a nonempty quote and nonnegative occurrence")
    previous = snapshot_bundle(project)["codings"]
    entry = {"source": source, "code": code, "quote": native_text(quote), "occurrence": occurrence}
    existed = entry in previous
    result = sync_coding(project, {"codings": [entry]})
    return {"id": item_id(repr(entry)), "created": not existed, "native_validation": result["native_validation"]}


def checkpoint(project):
    with LOCK:
        bundle = snapshot_bundle(project)
        state = native_state(project)
        path = managed_path(project)
        return {"path": str(path), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "detached": True, "integrity": "passed", **validate_native_state(bundle, state)}

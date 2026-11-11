"""Repeatable native NVivo import with author Shalom and software-level readback."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import re
import shutil
import uuid
import xml.etree.ElementTree as ET
import zipfile

import native_bridge


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def signed_package(source, destination, author):
    with zipfile.ZipFile(source) as original:
        root = ET.fromstring(original.read("project.qde"))
        ns = {"q": native_bridge.NS}
        users = root.find("q:Users", ns)
        if users is None:
            users = ET.Element("{" + native_bridge.NS + "}Users")
            root.insert(0, users)
        if len(users) == 0:
            ET.SubElement(users, "{" + native_bridge.NS + "}User", guid=str(uuid.uuid4()), name=author)
        for user in users:
            user.set("name", author)
        root.set("creatingUserGUID", users[0].get("guid"))
        root.set("modifyingUserGUID", users[0].get("guid"))
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as output:
            for item in original.infolist():
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True) if item.filename == "project.qde" else original.read(item)
                output.writestr(item, data)


def merged_ranges(mapping):
    result = {}
    for key, intervals in mapping.items():
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        result[key] = merged
    return result


def native_name(name):
    return re.sub(r'[\\/:*?"<>|]', "~", name)


def register_recent_project(project, title, work):
    config_root = Path(os.environ["APPDATA"]) / "Lumivero,_LLC"
    configs = list(config_root.glob("NVivo.exe_Url_*/15.6.1.3/user.config"))
    if not configs:
        return {"recent_project_registered": False, "recent_project_detail": "NVivo user settings were not found"}
    config = max(configs, key=lambda path: path.stat().st_mtime)
    shutil.copy2(config, work / "user.config.before")
    import base64
    tree = ET.parse(config)
    value = tree.find(".//setting[@name='RecentProjectList']/value")
    collection = ET.fromstring(base64.b64decode(value.text))
    entries = collection.find("RecentProjectList")
    for entry in list(entries):
        if entry.findtext("Filename", "").lower() == str(project).lower():
            entries.remove(entry)
    entry = ET.Element("RecentProject")
    ET.SubElement(entry, "Name").text = title
    ET.SubElement(entry, "Filename").text = str(project)
    ET.SubElement(entry, "Modified").text = datetime.now().astimezone().isoformat()
    entries.insert(0, entry)
    value.text = base64.b64encode(ET.tostring(collection, encoding="utf-8", xml_declaration=True)).decode("ascii")
    temporary = work / "user.config.updated"
    tree.write(temporary, encoding="utf-8", xml_declaration=True)
    staging = config.with_suffix(".import.tmp")
    shutil.copy2(temporary, staging)
    os.replace(staging, config)
    return {"recent_project_registered": True, "recent_project_refresh": "NVivo startup reads the saved recent-project entry"}


def validate_package(package, state, author):
    """Compare REFI text, hierarchy, case attributes and UTF-16 coding coverage."""
    ns = {"q": native_bridge.NS}
    actual_sources = {s["name"]: s for s in state["sources"]}
    actual_nodes = {n["name"]: n for n in state["nodes"] if n["type"] != "SentimentNode"}
    expected_ranges = {}
    with zipfile.ZipFile(package) as archive:
        root = ET.fromstring(archive.read("project.qde"))
        names = {n.get("guid"): native_name(n.get("name")) for n in root.findall(".//q:Code", ns) + root.findall("q:Cases/q:Case", ns)}
        if set(names.values()) != set(actual_nodes):
            raise ValueError("Native node inventory differs from the package")
        texts = root.findall("q:Sources/q:TextSource", ns) + root.findall("q:Notes/q:Note", ns)
        if {native_name(s.get("name")) for s in texts} != set(actual_sources):
            raise ValueError("Native document inventory differs from the package")
        files = {name.lower(): name for name in archive.namelist()}
        for source in texts:
            name = native_name(source.get("name"))
            relative = "sources/" + source.get("plainTextPath").removeprefix("internal://")
            text = archive.read(files[relative.lower()]).decode("utf-8-sig")
            if normalize(text).rstrip("\n") != normalize(actual_sources[name]["text"]).rstrip("\n"):
                raise ValueError("Native document text differs: " + name)
            raw = text.encode("utf-16-le")
            for selection in source.findall("q:PlainTextSelection", ns):
                start = int(selection.get("startPosition"))
                end = int(selection.get("endPosition"))
                prefix = raw[:start * 2].decode("utf-16-le")
                selected = raw[start * 2:end * 2].decode("utf-16-le")
                canonical_start = len(normalize(prefix))
                canonical_end = canonical_start + len(normalize(selected))
                limit = len(normalize(text).rstrip("\n"))
                for coding in selection.findall("q:Coding/q:CodeRef", ns):
                    code = names[coding.get("targetGUID")]
                    expected_ranges.setdefault((name, code), []).append((canonical_start, min(canonical_end, limit)))
        for parent in root.findall(".//q:Code", ns):
            for child in parent.findall("q:Code", ns):
                path = re.split(r"\\+", actual_nodes[native_name(child.get("name"))]["hierarchy"])
                if path[-2:] != [native_name(parent.get("name")), native_name(child.get("name"))]:
                    raise ValueError("Native code hierarchy differs")
        variables = {v.get("guid"): v.get("name") for v in root.findall("q:Variables/q:Variable", ns)}
        for case in root.findall("q:Cases/q:Case", ns):
            attributes = {}
            for value in case.findall("q:VariableValue", ns):
                variable = value.find("q:VariableRef", ns).get("targetGUID")
                text = value.find("q:TextValue", ns)
                if text is not None:
                    attributes[variables[variable]] = text.text or ""
            actual_attributes = actual_nodes[native_name(case.get("name"))].get("attributes", {})
            defaults = {key: value for key, value in actual_attributes.items() if key not in attributes}
            if any(actual_attributes.get(key) != value for key, value in attributes.items()) or any(
                value not in {"未分配", "Unassigned"} for value in defaults.values()
            ):
                raise ValueError("Native case attributes differ: " + case.get("name"))
    observed_ranges = {}
    for reference in state["references"]:
        text = actual_sources[reference["source"]]["text"]
        raw = text.encode("utf-16-le")
        start = len(normalize(raw[:reference["start"] * 2].decode("utf-16-le")))
        end = start + len(normalize(reference["text"]))
        limit = len(normalize(text).rstrip("\n"))
        observed_ranges.setdefault((reference["source"], reference["node"]), []).append((start, min(end, limit)))
    if merged_ranges(expected_ranges) != merged_ranges(observed_ranges):
        raise ValueError("Native coding coverage differs from the package")
    authors = {state["project_created_by"]}
    for entry in state["sources"] + list(actual_nodes.values()) + state["references"]:
        authors.add(entry["created_by"])
        if "modified_by" in entry:
            authors.add(entry["modified_by"])
    if authors != {author}:
        raise ValueError("Native author readback differs: " + repr(authors))
    return {"all_document_text_matches": True, "all_code_hierarchy_matches": True,
            "all_case_attributes_match": True, "all_coding_coverage_matches": True,
            "native_name_adjustments": {e.get("name"): native_name(e.get("name")) for e in texts if e.get("name") != native_name(e.get("name"))},
            "author_verified": True, "author": author, "documents": len(actual_sources),
            "node_types": dict(Counter(n["type"] for n in state["nodes"])),
            "coding_references": len(state["references"])}


def _run(input_path, project, report_path, author="Shalom", title=""):
    input_path, project, report_path = map(lambda p: Path(p).resolve(), (input_path, project, report_path))
    if project.suffix.lower() != ".nvp":
        raise ValueError("Output project must have .nvp extension")
    project.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    work = report_path.parent / "native_runs" / uuid.uuid4().hex
    work.mkdir(parents=True)
    package, xml, candidate, readback = [work / name for name in ("project.qdpx", "project.xml", "project.nvp", "readback.json")]
    if input_path.suffix.lower() == ".json":
        bundle = json.loads(input_path.read_text(encoding="utf-8"))
        native_bridge.package_bundle(bundle, work / "input.qdpx", title or project.stem)
        signed_package(work / "input.qdpx", package, author)
    else:
        signed_package(input_path, package, author)
    original_author = os.environ.get("NVIVO_AUTHOR")
    os.environ["NVIVO_AUTHOR"] = author
    try:
        native_bridge.convert_package(package, xml)
        native_bridge.run_native("build", candidate, xml, title or project.stem)
        native_bridge.run_native("verify", candidate, readback)
        proof = validate_package(package, json.loads(readback.read_text(encoding="utf-8")), author)
        backup = work / "previous.nvp"
        if project.exists():
            shutil.copy2(project, backup)
        old_log = project.with_name(project.stem + "_log.ldf")
        if old_log.exists():
            shutil.copy2(old_log, work / "previous_log.ldf")
            old_log.rename(work / "detached_previous_log.ldf")
        try:
            os.replace(candidate, project)
            native_bridge.run_native("verify", project, readback)
            state = json.loads(readback.read_text(encoding="utf-8"))
            proof = validate_package(package, state, author)
        except BaseException:
            if backup.exists():
                failed_log = project.with_name(project.stem + "_log.ldf")
                if failed_log.exists():
                    failed_log.rename(work / "failed_final_log.ldf")
                shutil.copy2(backup, project)
                saved_log = work / "previous_log.ldf"
                if saved_log.exists():
                    shutil.copy2(saved_log, old_log)
            raise
        report = {"status": "passed", "verified_at": datetime.now(timezone.utc).isoformat(),
                  "native_open_verified": True, "background_only": True, **proof,
                  "input": str(input_path), "input_sha256": sha256(input_path),
                  "project": str(project), "project_bytes": project.stat().st_size,
                  "project_sha256": sha256(project), "signed_package": str(package),
                  "native_readback": str(readback), "previous_project": str(backup) if backup.exists() else None}
        report.update(register_recent_project(project, state["project_title"], work))
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
    finally:
        if original_author is None:
            os.environ.pop("NVIVO_AUTHOR", None)
        else:
            os.environ["NVIVO_AUTHOR"] = original_author


def run(input_path, project, report_path, author="Shalom", title=""):
    project = Path(project).resolve()
    project.parent.mkdir(parents=True, exist_ok=True)
    with project.with_suffix(".import.lock").open("a+b") as lock:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError("Another import is already updating this project") from error
        try:
            return _run(input_path, project, report_path, author, title)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--author", default="Shalom")
    parser.add_argument("--title", default="")
    args = parser.parse_args()
    print(json.dumps(run(args.input, args.project, args.report, args.author, args.title), ensure_ascii=False, indent=2))

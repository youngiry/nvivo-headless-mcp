"""Invoke NVivo's own project services on an isolated background desktop."""
from pathlib import Path
import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
import shutil
import uuid
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "native"
NS = "urn:QDA-XML:project:1.0"
ET.register_namespace("", NS)


def run_native(mode, project, argument, title=""):
    script = (SOURCES / "run_native.ps1").read_text(encoding="utf-8-sig")
    env = os.environ.copy()
    env.update(NVIVO_NATIVE_ROOT=str(ROOT), NVIVO_NATIVE_MODE=mode, NVIVO_NATIVE_TARGET=str(Path(project).resolve()), NVIVO_NATIVE_ARGUMENT=str(Path(argument).resolve()), NVIVO_PROJECT_TITLE=title)
    temp = Path(tempfile.gettempdir()) / ("nvivo-agent-native-" + uuid.uuid4().hex)
    env["NVIVO_NATIVE_TEMP"] = str(temp)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    try:
        result = subprocess.run(["C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], env=env, capture_output=True, timeout=600, creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        if temp.parent == Path(tempfile.gettempdir()) and temp.name.startswith("nvivo-agent-native-"):
            shutil.rmtree(temp, ignore_errors=True)
    log = Path(argument).with_suffix(".native.log")
    if result.returncode:
        detail = log.read_text(encoding="utf-8-sig", errors="replace") if log.exists() else result.stderr.decode(errors="replace")
        raise RuntimeError("NVivo native service failed\n" + detail[-7000:])
    return log


def package_bundle(bundle, target, title):
    """Write CRLF text and native UTF-16 selection offsets for NVivo's converter."""
    def identifier(key):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, "nvivo-native-bundle/" + key))

    def add(parent, tag, text=None, **attrs):
        element = ET.SubElement(parent, "{" + NS + "}" + tag, attrs)
        element.text = text
        return element

    def native(text):
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
        return text if text.endswith("\r\n") else text + "\r\n"

    project = ET.Element("{" + NS + "}Project", name=title, origin="编码材料", creatingUserGUID=identifier("user"))
    add(add(project, "Users"), "User", guid=identifier("user"), name=os.environ.get("NVIVO_AUTHOR", "Shalom"))
    code_root = add(add(project, "CodeBook"), "Codes") if bundle.get("codes") else None
    code_elements = {}
    for code in bundle.get("codes", []):
        parent = code_elements[code["parent"]] if code.get("parent") else code_root
        node = add(parent, "Code", guid=identifier("code/" + code["name"]), name=code["name"], isCodable="true")
        add(node, "Description", code.get("description", ""))
        if code.get("memo"):
            add(node, "NoteRef", targetGUID=identifier("memo/" + code["memo"]))
        code_elements[code["name"]] = node
    case_names = {case["name"] for case in bundle.get("cases", [])}
    if case_names:
        variables = add(project, "Variables")
        fields = sorted({key for case in bundle["cases"] for key in case.get("attributes", {})})
        for field in fields:
            add(variables, "Variable", guid=identifier("variable/" + field), name=field, typeOfVariable="Text")
        cases = add(project, "Cases")
        for case in bundle["cases"]:
            node = add(cases, "Case", guid=identifier("case/" + case["name"]), name=case["name"])
            add(node, "Description", case.get("description", ""))
            for key, value in case.get("attributes", {}).items():
                entry = add(node, "VariableValue")
                add(entry, "VariableRef", targetGUID=identifier("variable/" + key))
                add(entry, "TextValue", str(value))
    text_elements = {}
    texts = {}
    payloads = {}
    source_root = add(project, "Sources") if bundle.get("sources") else None
    for source in bundle.get("sources", []):
        guid = identifier("source/" + source["name"])
        node = add(source_root, "TextSource", guid=guid, name=source["name"], plainTextPath="internal://" + guid + ".txt")
        add(node, "Description", source.get("description", ""))
        text = native(source["text"])
        payloads[guid + ".txt"] = text
        texts[source["name"]] = text
        text_elements[source["name"]] = node
    selections = {}
    for coding in bundle.get("codings", []):
        text = texts[coding["source"]]
        quote = coding["quote"].replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
        start = -1
        for _ in range(coding.get("occurrence", 0) + 1):
            start = text.find(quote, start + 1)
            if start < 0:
                raise ValueError("Quote was not found in " + coding["source"])
        key = (coding["source"], start, len(quote))
        selection = selections.get(key)
        if selection is None:
            selection = add(text_elements[coding["source"]], "PlainTextSelection", guid=identifier("selection/" + repr(key)), startPosition=str(len(text[:start].encode("utf-16-le")) // 2), endPosition=str(len(text[:start + len(quote)].encode("utf-16-le")) // 2))
            selections[key] = selection
        coded = add(selection, "Coding", guid=identifier("coding/" + repr(key) + "/" + coding["code"]))
        kind = "case/" if coding["code"] in case_names else "code/"
        add(coded, "CodeRef", targetGUID=identifier(kind + coding["code"]))
    for source in bundle.get("sources", []):
        if source.get("memo"):
            add(text_elements[source["name"]], "NoteRef", targetGUID=identifier("memo/" + source["memo"]))
    if bundle.get("memos"):
        notes = add(project, "Notes")
        for memo in bundle["memos"]:
            guid = identifier("memo/" + memo["name"])
            note = add(notes, "Note", guid=guid, name=memo["name"], plainTextPath="internal://" + guid + ".txt")
            add(note, "Description", "编码分析过程")
            payloads[guid + ".txt"] = native(memo["text"])
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("project.qde", ET.tostring(project, encoding="utf-8", xml_declaration=True))
        for name, text in payloads.items():
            archive.writestr("Sources/" + name, text.encode("utf-8-sig"))
        memo_links = []
        for kind in ("sources", "codes", "cases"):
            for item in bundle.get(kind, []):
                if item.get("memo"):
                    memo_links.append({"kind": "source" if kind == "sources" else "node",
                                       "item": re.sub(r'[\\/:*?"<>|]', "~", item["name"]),
                                       "memo": re.sub(r'[\\/:*?"<>|]', "~", item["memo"])})
        if memo_links:
            archive.writestr("memo-links.json", json.dumps(memo_links, ensure_ascii=False))


def convert_package(package, output_xml):
    result = subprocess.run([str(Path(os.environ["NVIVO_INSTALL_DIR"]) / "Converters/QDPX/QSR.Tools.QDPXExporter.exe"), str(Path(package).resolve()), str(Path(output_xml).resolve())], capture_output=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode or not Path(output_xml).is_file():
        raise RuntimeError("NVivo project converter failed, exit " + str(result.returncode))
    converted = ET.parse(output_xml)
    if any(e.tag.endswith("exportError") for e in converted.iter()):
        raise ValueError("NVivo converter rejected the exchange package: " + ET.tostring(converted.getroot(), encoding="unicode"))
    with zipfile.ZipFile(package) as archive:
        if "memo-links.json" in archive.namelist():
            Path(output_xml).with_suffix(".memo-links.json").write_bytes(archive.read("memo-links.json"))
    return {"exit_code": result.returncode, "xml_sha256": hashlib.sha256(Path(output_xml).read_bytes()).hexdigest()}

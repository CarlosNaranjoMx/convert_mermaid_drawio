"""
Convert Mermaid (.mmd) flowcharts into a single draw.io (.drawio) file.

Uso:
    python convert_mmd_draw.py <archivo.mmd> [-o salida.drawio]
    python convert_mmd_draw.py <carpeta>     [-o salida.drawio]

- Si se pasa un archivo .mmd: se genera un .drawio con una sola pestaña.
- Si se pasa una carpeta: se generan tantas pestañas como .mmd haya dentro,
  todas en un único archivo .drawio de salida.

Soporta una variante práctica de Mermaid `flowchart`/`graph`:

  flowchart LR | RL | TB | TD | BT
  graph    LR | RL | TB | TD | BT

  Nodos:
    A
    A["Etiqueta con espacios"]
    A[Etiqueta]
    A(Etiqueta)        -> rectángulo redondeado
    A((Etiqueta))      -> elipse / círculo
    A{Etiqueta}        -> rombo (decisión)
    A[(Etiqueta)]      -> cilindro (BD)

  Aristas:
    A --> B
    A --- B            (sin flecha)
    A -.-> B           (línea punteada)
    A ==> B            (línea gruesa)
    A -->|texto| B     (con etiqueta)
    A -- texto --> B   (con etiqueta, sintaxis alternativa)
    A & B --> C        (varios orígenes / destinos)

  Subgraphs (contenedores anidables):
    subgraph ID["Título"]
      direction LR
      ...
    end

  Estilos:
    classDef nombre fill:#xxx,stroke:#yyy,color:#zzz
    class A,B,C nombre
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html import escape as html_escape
from pathlib import Path
from typing import Iterable
from xml.dom import minidom


# ---------------------------------------------------------------------------
# Modelo intermedio
# ---------------------------------------------------------------------------

@dataclass
class Node:
    id: str
    label: str
    shape: str = "rect"
    parent: str = "__root__"
    classes: list[str] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    width: float = 140.0
    height: float = 60.0


@dataclass
class Subgraph:
    id: str
    label: str
    parent: str = "__root__"
    direction: str | None = None
    classes: list[str] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0


@dataclass
class Edge:
    source: str
    target: str
    label: str = ""
    style: str = "solid"
    arrow: bool = True


@dataclass
class ClassDef:
    name: str
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class Diagram:
    name: str
    direction: str = "TB"
    nodes: dict[str, Node] = field(default_factory=dict)
    subgraphs: dict[str, Subgraph] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    class_defs: dict[str, ClassDef] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parser de Mermaid
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(
    r"^\s*(?:flowchart|graph)\s+(LR|RL|TB|TD|BT)\s*$",
    re.IGNORECASE,
)

_ID = r"[A-Za-z_][\w\.]*"

_NODE_DEF_RE = re.compile(
    rf"(?P<id>{_ID})"
    r"(?:"
    r"\[\(\s*(?P<lbl_cylinder>(?:\"[^\"]*\"|[^)])*?)\s*\)\]"
    r"|\[\[\s*(?P<lbl_subroutine>(?:\"[^\"]*\"|[^\]])*?)\s*\]\]"
    r"|\(\(\s*(?P<lbl_circle>(?:\"[^\"]*\"|[^)])*?)\s*\)\)"
    r"|\[\s*(?P<lbl_rect>(?:\"[^\"]*\"|[^\]])*?)\s*\]"
    r"|\(\s*(?P<lbl_round>(?:\"[^\"]*\"|[^)])*?)\s*\)"
    r"|\{\s*(?P<lbl_rhombus>(?:\"[^\"]*\"|[^}])*?)\s*\}"
    r")?"
)

_CONNECTOR_RE = re.compile(
    r"""
    (?P<full>
        (?::
            -\.->
          | -\.-
          | ==>
          | ===
          | -->
          | ---
        )
    )
    """,
    re.VERBOSE,
)


def _strip_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        return text[1:-1]
    return text


def _shape_for_label_kind(match: re.Match) -> tuple[str, str]:
    if match.group("lbl_cylinder") is not None:
        return _strip_quotes(match.group("lbl_cylinder")), "cylinder"
    if match.group("lbl_circle") is not None:
        return _strip_quotes(match.group("lbl_circle")), "ellipse"
    if match.group("lbl_subroutine") is not None:
        return _strip_quotes(match.group("lbl_subroutine")), "rect"
    if match.group("lbl_rect") is not None:
        return _strip_quotes(match.group("lbl_rect")), "rect"
    if match.group("lbl_round") is not None:
        return _strip_quotes(match.group("lbl_round")), "rounded"
    if match.group("lbl_rhombus") is not None:
        return _strip_quotes(match.group("lbl_rhombus")), "rhombus"
    return "", "rect"


def _ensure_node(diagram: Diagram, node_id: str, label: str = "",
                 shape: str = "rect", parent: str = "__root__") -> Node:
    node = diagram.nodes.get(node_id)
    if node is None:
        node = Node(id=node_id, label=label or node_id, shape=shape, parent=parent)
        diagram.nodes[node_id] = node
    else:
        if label:
            node.label = label
        if shape and shape != "rect":
            node.shape = shape
        if node.parent == "__root__" and parent != "__root__":
            node.parent = parent
    return node


def _parse_node_token(token: str) -> tuple[str, str, str] | None:
    token = token.strip()
    if not token:
        return None
    m = _NODE_DEF_RE.match(token)
    if not m or m.group("id") is None:
        return None
    if m.end() != len(token):
        rest = token[m.end():].strip()
        if rest:
            return None
    label, shape = _shape_for_label_kind(m)
    return m.group("id"), label, shape


def _parse_node_group(token: str) -> list[tuple[str, str, str]]:
    """Parsea `A`, `A["x"]` o `A & B & C[..]` en una lista."""
    parts = [p.strip() for p in re.split(r"\s*&\s*", token) if p.strip()]
    out: list[tuple[str, str, str]] = []
    for p in parts:
        parsed = _parse_node_token(p)
        if parsed is not None:
            out.append(parsed)
    return out


def _split_connectors(line: str) -> list[tuple[str, str, str]] | None:
    matches = list(_CONNECTOR_RE.finditer(line))
    if not matches:
        return None

    parts: list[tuple[str, str, str]] = []
    cursor = 0
    prev_token: str | None = None
    pending_connector: str | None = None

    for m in matches:
        left = line[cursor:m.start()]
        connector = m.group("full")
        cursor = m.end()

        if prev_token is None:
            prev_token = left.strip()
            pending_connector = connector
            continue

        middle = left.strip()
        label_match = re.match(r"\|([^|]*)\|\s*(.*)", middle, re.DOTALL)
        edge_label = ""
        if label_match:
            edge_label = label_match.group(1).strip()
            middle = label_match.group(2).strip()

        parts.append((prev_token, _encode_connector(pending_connector, edge_label), middle))
        prev_token = middle
        pending_connector = connector

    if prev_token is None or pending_connector is None:
        return None

    rest = line[cursor:].strip()
    if rest:
        parts.append((prev_token, _encode_connector(pending_connector, ""), rest))

    return parts


def _encode_connector(connector: str, label: str) -> tuple[str, str]:
    style = "solid"
    arrow = True

    if connector == "-.-":
        style = "dashed"
        arrow = False
    elif connector == "-.->":
        style = "dashed"
        arrow = True
    elif connector == "==>":
        style = "thick"
        arrow = True
    elif connector == "===":
        style = "thick"
        arrow = False
    elif connector == "---":
        style = "solid"
        arrow = False
    elif connector == "-->":
        style = "solid"
        arrow = True

    return style, label if label else ("arrow" if arrow else "")


def _parse_line(line: str, diagram: Diagram) -> None:
    line = line.strip()
    if not line or line.startswith("%%"):
        return
    if line.startswith("subgraph"):
        _parse_subgraph(line, diagram)
        return
    if line == "end":
        return

    parts = _split_connectors(line)
    if not parts:
        return

    source_group, style_label, target_group = parts[0]
    style, label = style_label

    source_nodes = _parse_node_group(source_group)
    target_nodes = _parse_node_group(target_group)
    if not source_nodes or not target_nodes:
        return

    for src in source_nodes:
        for tgt in target_nodes:
            diagram.edges.append(Edge(source=src[0], target=tgt[0], label=label, style=style, arrow=label != "" or style != ""))
            _ensure_node(diagram, src[0], src[1], src[2])
            _ensure_node(diagram, tgt[0], tgt[1], tgt[2])


def _parse_subgraph(line: str, diagram: Diagram) -> None:
    parts = line.split(None, 2)
    if len(parts) < 2:
        return
    subgraph_id = parts[1]
    label = subgraph_id
    if len(parts) == 3 and parts[2].startswith("[") and parts[2].endswith("]"):
        label = _strip_quotes(parts[2][1:-1])
    diagram.subgraphs[subgraph_id] = Subgraph(id=subgraph_id, label=label)


def _parse_mermaid(text: str, name: str = "diagram") -> Diagram:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    direction = "TB"
    if lines and _HEADER_RE.match(lines[0]):
        direction = _HEADER_RE.match(lines[0]).group(1).upper()
        lines = lines[1:]

    diagram = Diagram(name=name, direction=direction)
    for line in lines:
        _parse_line(line, diagram)
    return diagram


def _diagram_to_drawio(diagram: Diagram) -> ET.Element:
    mxfile = ET.Element("mxfile", host="app.diagrams.net")
    diagram_elem = ET.SubElement(mxfile, "diagram", name=diagram.name)
    graph = ET.SubElement(diagram_elem, "mxGraphModel", dx="1000", dy="1000", grid="1", gridSize="10", guides="1", tooltips="1", connect="1", arrows="1", fold="1", page="1", pageScale="1", pageWidth="850", pageHeight="1100")
    root = ET.SubElement(graph, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")

    for node in diagram.nodes.values():
        style = _style_for_shape(node.shape)
        cell = ET.SubElement(root, "mxCell", id=node.id, value=html_escape(node.label), style=style, vertex="1", parent="1")
        ET.SubElement(cell, "mxGeometry", x=str(node.x), y=str(node.y), width=str(node.width), height=str(node.height), as="geometry")

    for edge in diagram.edges:
        cell = ET.SubElement(root, "mxCell", id=str(uuid.uuid4()), value=html_escape(edge.label), style=_style_for_edge(edge), edge="1", parent="1", source=edge.source, target=edge.target)
        ET.SubElement(cell, "mxGeometry", relative="1", as="geometry")

    return mxfile


def _style_for_shape(shape: str) -> str:
    style_map = {
        "rect": "rounded=0;whiteSpace=wrap;html=1;",
        "rounded": "rounded=1;whiteSpace=wrap;html=1;",
        "ellipse": "shape=ellipse;whiteSpace=wrap;html=1;",
        "rhombus": "shape=rhombus;whiteSpace=wrap;html=1;",
        "cylinder": "shape=cylinder;whiteSpace=wrap;html=1;"
    }
    return style_map.get(shape, style_map["rect"])


def _style_for_edge(edge: Edge) -> str:
    style = "endArrow=classic;"
    if not edge.arrow:
        style = "endArrow=none;"
    if edge.style == "dashed":
        style += "dashed=1;"
    if edge.style == "thick":
        style += "strokeWidth=3;"
    return style + "html=1;"


def _prettify_xml(element: ET.Element) -> str:
    raw_xml = ET.tostring(element, encoding="utf-8")
    parsed = minidom.parseString(raw_xml)
    return parsed.toprettyxml(indent="  ")


def _write_output(output_path: Path, xml_content: str) -> None:
    output_path.write_text(xml_content, encoding="utf-8")


def _collect_mmd_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    return sorted([p for p in source.glob("*.mmd") if p.is_file()])


def _build_drawio(source: Path, output: Path) -> None:
    mmd_files = _collect_mmd_files(source)
    diagrams = []
    for mmd_file in mmd_files:
        content = mmd_file.read_text(encoding="utf-8")
        diagrams.append(_parse_mermaid(content, name=mmd_file.stem))

    mxfile = ET.Element("mxfile", host="app.diagrams.net")
    for diagram in diagrams:
        mxfile.append(_diagram_to_drawio(diagram))

    xml_content = _prettify_xml(mxfile)
    _write_output(output, xml_content)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert Mermaid .mmd to draw.io .drawio")
    parser.add_argument("source", type=Path, help="Archivo .mmd o carpeta que contiene .mmd")
    parser.add_argument("-o", "--output", type=Path, help="Archivo .drawio de salida")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    source = args.source
    if not source.exists():
        print(f"Error: {source} no existe.")
        return 1

    output = args.output
    if output is None:
        output = source.with_suffix(".drawio") if source.is_file() else source / "output.drawio"

    _build_drawio(source, output)
    print(f"Generado: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

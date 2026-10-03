"""Edit a Grid 3 ``.gridset`` file directly, always into a separate edited copy.

This is the Grid 3 counterpart of the exported TD Snap file path: nothing here
drives Grid 3, nothing reaches the network, and the file somebody chose is
never written. The app works on a private session copy; every edit reads that
copy, writes a *new* package beside it, re-reads the new package, and keeps it
only if the re-read shows exactly the reviewed change and nothing else.

Why this does not contradict the live rule "no direct grid-set mutation": that
rule protects the grid set Grid 3 has open, which Grid 3 versions and syncs.
An edited copy is a new file the person imports into Grid 3 themselves, the
same way an edited ``.sps`` is imported into TD Snap (see
docs/IMPORT_SAFETY.md).

**What a package looks like.** A ``.gridset`` is a zip. ``Settings0/settings.xml``
names the format version (only ``1`` is read) and, usually, the start grid;
``Settings0/Styles/styles.xml`` holds named styles; and each grid is
``Grids/<name>/grid.xml``, its name being its folder. A cell is a ``<Cell X Y>``
element with a ``<Content>``: a speaking (Write) cell carries an
``Action.InsertText`` command and a caption, a jump carries ``Jump.To`` with
the target grid's name. Positions with no ``<Cell>`` element, and cells whose
content is empty, are empty squares.

**Writes are narrow on purpose.** Exactly the cells ``grid3._cell_kind`` calls
``speak`` can be changed, moved, or removed; everything else on a grid stays
locked with the same reasons live editing gives. Every zip entry the edit does
not need is copied byte for byte, so pictures, settings, and grids that were
not touched cannot change.

Grid sets reach this module only as ``.gridset`` files; a ``.gridsetx`` is
refused by ``Grid3Package`` with the same message as live editing, because its
contents are encrypted.
"""

from __future__ import annotations

import copy
import hashlib
import os
import re
import shutil
import uuid
import zipfile
from xml.etree import ElementTree as ET

from . import obf
from .builder import MAX_TITLE_LENGTH, _normalize_items
from .colors import hex_from_argb
from .errors import PagesetError
from .grid3 import (
    LOCK_REASONS,
    Grid3Cell,
    Grid3Grid,
    Grid3Package,
    _cell_kind,
    _describe_cell,
    _semantic,
    _spoken_after_change,
    _text,
)

FORMAT = "gridset"

# Bounds on the package itself. Real grid sets with pictures run to tens of
# megabytes and a few thousand entries; these refuse a zip bomb rather than
# copy it.
MAX_ENTRIES = 20_000
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_GRIDS = 2_000

# A grid's name is its folder name inside the package.
_FORBIDDEN_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_FILEMAP = "FileMap.xml"
# Folder names Windows will not create, whatever follows a dot.
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL",
                   *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}

SYMBOLS_NOTE = (
    "Symbols are not included. Grid 3's symbol libraries are licensed content, "
    "so an Open Board export carries labels, spoken messages, layout, and links only."
)
NO_SYMBOLS_WARNING = (
    "Edited grid-set files get no symbols. Open the grid in Grid 3 to add "
    "pictures to the new cells."
)

CAN_DO = (
    "Add words and phrases to empty cells on any grid in the file.",
    "Change, move, or remove a cell that just speaks.",
    "Create a new grid the size of an existing one, linked from one of its empty cells.",
    "Bring a whole Open Board (.obz) set in as new linked grids, and export the "
    "grid set as .obz.",
)
CANNOT_DO = (
    "Change a cell that jumps to another grid, runs a command, or holds a word "
    "list, picture, or app.",
    "Open protected .gridsetx grid sets, including WordPower: Grid 3 encrypts them.",
    "Add symbols. Open the edited grid set in Grid 3 to add pictures.",
    "Edit the copy Grid 3 has open. AAC Editor writes a new .gridset you import.",
)


def is_gridset_file(path: str) -> bool:
    """True for a zip that carries Grid 3's settings entry."""
    try:
        with zipfile.ZipFile(path) as package:
            return "Settings0/settings.xml" in package.namelist()
    except (OSError, zipfile.BadZipFile):
        return False


def page_id(name: str) -> int:
    """A stable integer id for a grid, from its name.

    The file routes address pages by integer. A grid set has no numeric ids,
    and an index into the sorted names would shift when a grid is added, so
    the id is derived from the name: 48 bits, safely below JavaScript's
    integer limit.
    """
    return int(hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()[:12], 16)


def _clean_title(title) -> str:
    if not isinstance(title, str):
        raise PagesetError("The new grid's name must be text.")
    title = title.strip()
    if not title:
        raise PagesetError("Give the new grid a name.")
    if len(title) > MAX_TITLE_LENGTH:
        raise PagesetError(
            f"The grid name is too long (maximum {MAX_TITLE_LENGTH} characters)."
        )
    if title.split(".")[0].strip().upper() in _RESERVED_NAMES:
        raise PagesetError(
            f"“{title}” is a name Windows reserves, so Grid 3 cannot store a grid under it."
        )
    if _FORBIDDEN_NAME.search(title) or title.endswith(".") or title in {".", ".."}:
        raise PagesetError(
            'A grid name cannot contain \\ / : * ? " < > | or end with a full stop, '
            "because Grid 3 stores each grid in a folder of that name."
        )
    return title


def _safe_title(name: str) -> str:
    """An imported board's name made usable as a grid folder name."""
    cleaned = _FORBIDDEN_NAME.sub("-", name or "").strip().rstrip(".").strip()
    cleaned = cleaned[:MAX_TITLE_LENGTH].strip() or "Board"
    if cleaned.split(".")[0].strip().upper() in _RESERVED_NAMES:
        cleaned = f"{cleaned} board"[:MAX_TITLE_LENGTH]
    return cleaned


# ---------------------------------------------------------------------------
# reading


class GridsetFile:
    """A session copy of a ``.gridset``, read through ``Grid3Package``."""

    def __init__(self, path: str):
        _check_package(path)
        self.package = Grid3Package(path, session_copy=True)
        self.path = path
        names = self.package.grid_names()
        if not names:
            self.package.close()
            raise PagesetError("This grid set has no grids in it.")
        if len(names) > MAX_GRIDS:
            self.package.close()
            raise PagesetError(f"AAC Editor reads grid sets of at most {MAX_GRIDS} grids.")
        self._ids = {}
        for name in names:
            number = page_id(name)
            if number in self._ids:
                self.package.close()
                raise PagesetError("Two grids in this grid set have the same name.")
            self._ids[number] = name

    def close(self) -> None:
        self.package.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    # -- grids ---------------------------------------------------------------

    def names(self) -> list[str]:
        return sorted(self._ids.values(), key=lambda name: (name.casefold(), name))

    def pages(self) -> list[dict]:
        return [{"id": page_id(name), "title": name} for name in self.names()]

    def name_for(self, number: int) -> str:
        name = self._ids.get(number)
        if name is None:
            raise PagesetError("That grid is not in this grid set.")
        return name

    def start_grid(self) -> str | None:
        wanted = _text(self.package.settings, "StartGrid")
        if not wanted:
            return None
        return next((name for name in self._ids.values()
                     if name.casefold() == wanted.casefold()), None)

    def home_page_id(self) -> int | None:
        start = self.start_grid()
        return page_id(start) if start else None

    def grid(self, name: str) -> Grid3Grid:
        return self.package.grid(name)

    def grid_dimension(self) -> tuple[int, int]:
        """The start grid's size (or the first grid's), as ``(cols, rows)``."""
        grid = self.grid(self.start_grid() or self.names()[0])
        return grid.cols, grid.rows

    def jump_targets(self, name: str) -> dict[tuple[int, int], str]:
        """The grid each ``Jump.To`` cell on *name* opens, by position."""
        root = self.package._xml(f"Grids/{name}/grid.xml")
        targets = {}
        for node in root.findall("./Cells/Cell"):
            for command in node.findall("./Content/Commands/Command"):
                if command.get("ID") != "Jump.To":
                    continue
                for parameter in command.findall("Parameter"):
                    if parameter.get("Key") == "grid":
                        target = "".join(parameter.itertext()).strip()
                        if target:
                            targets[(_int(node.get("X")), _int(node.get("Y")))] = target
        return targets

    # -- what the preview needs ---------------------------------------------

    def page_state(self, number: int, include_buttons: bool = True) -> dict:
        name = self.name_for(number)
        grid = self.grid(name)
        state = {"grid": {"cols": grid.cols, "rows": grid.rows},
                 "free_slots": free_slots(grid)}
        if not include_buttons:
            return state
        buttons = []
        cells = []
        for cell in grid.cells:
            slot = cell.y * grid.cols + cell.x
            if not cell.safe_blank:
                buttons.append(_describe_cell(cell, slot))
            cells.append({
                "slot": slot, "x": cell.x, "y": cell.y,
                "column_span": cell.column_span, "row_span": cell.row_span,
                "label": cell.label, "occupied": not cell.safe_blank,
                "safe_blank": cell.safe_blank, "image": bool(cell.image),
                "style": {"key": cell.style.key, "background": cell.style.background,
                          "border": cell.style.border, "foreground": cell.style.foreground},
                "rect": None,
            })
        buttons.sort(key=lambda button: button["slot"])
        return {
            **state,
            "page": name,
            "buttons": buttons,
            "cells": cells,
            "background": grid.background,
            "content_readable": True,
            "can_edit_existing": True,
            "fingerprint": fingerprint(grid),
        }

    def labels_by_page(self) -> dict[str, list[str]]:
        labels = {}
        for name in self.names():
            grid = self.grid(name)
            labels[name] = sorted(
                {cell.label for cell in grid.cells if cell.label},
                key=str.casefold,
            )
        return labels

    def label_samples(self, limit: int = 40) -> list[str]:
        seen, samples = set(), []
        for labels in self.labels_by_page().values():
            for label in labels:
                if label.casefold() not in seen:
                    seen.add(label.casefold())
                    samples.append(label)
                if len(samples) >= limit:
                    return samples
        return samples


def _int(value, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError as exc:
        raise PagesetError("A Grid 3 grid has invalid cell coordinates.") from exc


def _check_package(path: str) -> None:
    try:
        with zipfile.ZipFile(path) as package:
            infos = package.infolist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise PagesetError("The Grid 3 grid set is not a readable package.") from exc
    if len(infos) > MAX_ENTRIES:
        raise PagesetError("This grid set has more entries than AAC Editor will read.")
    if sum(info.file_size for info in infos) > MAX_TOTAL_BYTES:
        raise PagesetError("This grid set is larger than AAC Editor will read.")
    if any(info.flag_bits & 0x1 for info in infos):
        raise PagesetError(
            "This grid set is password-protected, so AAC Editor cannot read it."
        )


def covered(grid: Grid3Grid) -> set[tuple[int, int]]:
    """Every square some cell element occupies, spans included."""
    squares = set()
    for cell in grid.cells:
        for dx in range(max(1, cell.column_span)):
            for dy in range(max(1, cell.row_span)):
                squares.add((cell.x + dx, cell.y + dy))
    return squares


def free_slots(grid: Grid3Grid) -> list[int]:
    """Safe blank cells, plus squares no cell element covers at all."""
    taken = covered(grid)
    slots = {cell.y * grid.cols + cell.x for cell in grid.cells
             if cell.safe_blank and 0 <= cell.x < grid.cols and 0 <= cell.y < grid.rows}
    slots |= {y * grid.cols + x for y in range(grid.rows) for x in range(grid.cols)
              if (x, y) not in taken}
    return sorted(slots)


def fingerprint(grid: Grid3Grid) -> str:
    snapshot = _semantic(grid)
    payload = repr((snapshot["grid"], sorted(snapshot["cells"].items())))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# XML building blocks


def _rich(tag: str, text: str, trailing_space: bool = False) -> ET.Element:
    """Grid 3's formatted text: ``<p><s><r>text</r></s></p>``."""
    node = ET.Element(tag)
    paragraph = ET.SubElement(node, "p")
    run = ET.SubElement(ET.SubElement(paragraph, "s"), "r")
    run.text = text
    if trailing_space:
        # Grid 3 writes the space it types after a word as its own segment.
        ET.SubElement(ET.SubElement(paragraph, "s"), "r").text = " "
    return node


def _command(command_id: str, key: str | None = None, value: ET.Element | str | None = None):
    node = ET.Element("Command", {"ID": command_id})
    if key is not None:
        parameter = ET.SubElement(node, "Parameter", {"Key": key})
        if isinstance(value, ET.Element):
            parameter.extend(list(value))
        elif value is not None:
            parameter.text = value
    return node


def _style(based_on: str | None, border: str | None = None) -> ET.Element | None:
    if not based_on and not border:
        return None
    style = ET.Element("Style")
    if based_on:
        ET.SubElement(style, "BasedOnStyle").text = based_on
    if border:
        ET.SubElement(style, "BorderColour").text = f"{border}FF"
    return style


def _speak_content(label: str, message: str | None, style: ET.Element | None) -> ET.Element:
    content = ET.Element("Content")
    commands = ET.SubElement(content, "Commands")
    commands.append(_command("Action.InsertText", "text",
                             _rich("Parameter", message or label, trailing_space=True)))
    caption = ET.SubElement(content, "CaptionAndImage")
    caption.append(_rich("Caption", label))
    if style is not None:
        content.append(style)
    return content


def _caption_content(command: ET.Element, label: str, style: ET.Element | None) -> ET.Element:
    content = ET.Element("Content")
    ET.SubElement(content, "Commands").append(command)
    ET.SubElement(content, "CaptionAndImage").append(_rich("Caption", label))
    if style is not None:
        content.append(style)
    return content


def _blank_content(style: ET.Element | None) -> ET.Element:
    content = ET.Element("Content")
    if style is not None:
        content.append(copy.deepcopy(style))
    return content


def _serialize(root: ET.Element, original: bytes | None) -> bytes:
    body = ET.tostring(root, encoding="unicode").encode("utf-8")
    original = original or b""
    bom = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
    declared = original[len(bom):].lstrip().startswith(b"<?xml") or not original
    declaration = b'<?xml version="1.0" encoding="utf-8"?>\n' if declared else b""
    return bom + declaration + body


# ---------------------------------------------------------------------------
# the writer


class _Writer:
    """Collects XML changes against one package, then writes a new zip."""

    def __init__(self, source: GridsetFile):
        self.source = source
        self.package = source.package
        self.trees: dict[str, tuple[ET.Element, bytes]] = {}
        self.new_grids: dict[str, ET.Element] = {}
        self.filemap: tuple[ET.Element, bytes] | None = None

    # -- loading -------------------------------------------------------------

    def tree(self, name: str) -> ET.Element:
        if name in self.new_grids:
            return self.new_grids[name]
        if name not in self.trees:
            entry = f"Grids/{name}/grid.xml"
            raw = self.package._bytes(entry)
            self.trees[name] = (self.package._xml(entry), raw)
        return self.trees[name][0]

    def cells(self, name: str) -> dict[tuple[int, int], ET.Element]:
        found = {}
        for node in self.tree(name).findall("./Cells/Cell"):
            found[(_int(node.get("X")), _int(node.get("Y")))] = node
        return found

    def cell(self, name: str, position: tuple[int, int]) -> ET.Element:
        """The cell element at *position*, created when the square has none."""
        existing = self.cells(name).get(position)
        if existing is not None:
            return existing
        root = self.tree(name)
        cells = root.find("Cells")
        if cells is None:
            cells = ET.SubElement(root, "Cells")
        node = ET.SubElement(cells, "Cell", {"X": str(position[0]), "Y": str(position[1])})
        ET.SubElement(node, "Content")
        return node

    # -- content operations --------------------------------------------------

    @staticmethod
    def set_content(node: ET.Element, content: ET.Element) -> None:
        old = node.find("Content")
        if old is not None:
            index = list(node).index(old)
            node.remove(old)
            node.insert(index, content)
        else:
            node.append(content)

    @staticmethod
    def style_of(node: ET.Element | None) -> ET.Element | None:
        if node is None:
            return None
        style = node.find("./Content/Style")
        return copy.deepcopy(style) if style is not None else None

    def write_speaking(self, name, position, label, message, style) -> None:
        self.set_content(self.cell(name, position), _speak_content(label, message, style))

    def blank(self, name, position, style=None) -> None:
        node = self.cells(name).get(position)
        if node is not None:
            keep = style if style is not None else self.style_of(node)
            self.set_content(node, _blank_content(keep))

    def change(self, name, position, label, message) -> None:
        node = self.cells(name)[position]
        content = node.find("Content")
        caption = content.find("./CaptionAndImage/Caption")
        if caption is None:
            holder = content.find("CaptionAndImage")
            if holder is None:
                holder = ET.SubElement(content, "CaptionAndImage")
            caption = ET.SubElement(holder, "Caption")
        caption.clear()
        caption.extend(list(_rich("Caption", label)))
        for command in content.findall("./Commands/Command"):
            if command.get("ID") != "Action.InsertText":
                continue
            for parameter in command.findall("Parameter"):
                if parameter.get("Key") == "text":
                    parameter.clear()
                    parameter.set("Key", "text")
                    parameter.extend(list(_rich("Parameter", message, trailing_space=True)))

    def move(self, name, source, destination) -> None:
        cells = self.cells(name)
        moving = cells[source]
        target_style = self.style_of(cells.get(destination))
        content = copy.deepcopy(moving.find("Content"))
        self.set_content(self.cell(name, destination), content)
        self.set_content(moving, _blank_content(target_style))

    # -- new grids -----------------------------------------------------------

    def add_grid(self, name: str, parent: str) -> ET.Element:
        """A new grid shaped like *parent*, with Grid 3's Back cell top-left."""
        template = copy.deepcopy(self.tree(parent))
        cells = template.find("Cells")
        if cells is None:
            cells = ET.SubElement(template, "Cells")
        for child in list(cells):
            cells.remove(child)
        for node in template.iter():
            if node.tag.endswith("Guid") and (node.text or "").strip():
                node.text = str(uuid.uuid4())
        for word_list in template.findall("WordList"):
            for child in list(word_list):
                word_list.remove(child)
        back = ET.SubElement(cells, "Cell", {"X": "0", "Y": "0"})
        back.append(_caption_content(
            _command("Jump.Back"), "Back", _style(self._style_for("Jump.Back")),
        ))
        self.new_grids[name] = template
        self._register_in_filemap(name, parent)
        return template

    def link(self, parent: str, position, target: str, label: str) -> None:
        self.set_content(self.cell(parent, position), _caption_content(
            _command("Jump.To", "grid", target), label, _style(self._style_for("Jump.To")),
        ))

    def _style_for(self, command_id: str) -> str | None:
        """The style an existing cell with *command_id* uses, so new ones match."""
        for name in self.source.names():
            root = self.tree(name) if name in self.trees else self.package._xml(
                f"Grids/{name}/grid.xml")
            for node in root.findall("./Cells/Cell"):
                if any(command.get("ID") == command_id
                       for command in node.findall("./Content/Commands/Command")):
                    style = _text(node, "./Content/Style/BasedOnStyle")
                    if style:
                        return style
        return None

    def speaking_style(self, name: str) -> str | None:
        """The style speaking cells already use, preferring Grid 3's own Write style."""
        if "Vocab cell" in self.package.styles:
            return "Vocab cell"
        counts: dict[str, int] = {}
        for grid_name in [name, *self.source.names()]:
            if grid_name in self.new_grids:
                continue
            for cell in self.source.grid(grid_name).cells:
                if _cell_kind(cell) == "speak" and cell.style.key:
                    counts[cell.style.key] = counts.get(cell.style.key, 0) + 1
            if counts:
                break
        return max(counts, key=counts.get) if counts else None

    def _register_in_filemap(self, name: str, parent: str) -> None:
        """Add the new grid to ``FileMap.xml`` in the same shape as its parent's entry.

        Not every package carries a file map. When one does and the parent's
        entry cannot be recognised, the edit stops rather than leave Grid 3
        with a grid it has no record of.
        """
        if _FILEMAP not in self.package.zip.namelist():
            return
        if self.filemap is None:
            raw = self.package._bytes(_FILEMAP)
            self.filemap = (self.package._xml(_FILEMAP), raw)
        root = self.filemap[0]
        patterns = [f"Grids{sep}{parent}{sep}grid.xml" for sep in ("\\", "/")]

        def mentions(node: ET.Element) -> str | None:
            values = [*node.attrib.values(), (node.text or "")]
            for pattern in patterns:
                if any(value.strip() == pattern for value in values):
                    return pattern
            return None

        for holder in root.iter():
            for index, entry in enumerate(list(holder)):
                pattern = mentions(entry)
                if pattern is None:
                    continue
                replacement = pattern.replace(parent, name, 1)
                clone = ET.Element(entry.tag, {
                    key: (replacement if value.strip() == pattern else value)
                    for key, value in entry.attrib.items()
                })
                clone.text = replacement if (entry.text or "").strip() == pattern else entry.text
                clone.tail = entry.tail
                for child in entry:
                    emptied = ET.SubElement(clone, child.tag, dict(child.attrib))
                    emptied.text, emptied.tail = child.text, child.tail
                    if len(child):
                        emptied.text = None
                holder.insert(index + 1, clone)
                return
        raise PagesetError(
            "This grid set's file map does not list its grids in a way AAC Editor "
            "recognises, so it will not add a grid to it."
        )

    # -- saving --------------------------------------------------------------

    def save(self, dest: str) -> None:
        replaced = {f"Grids/{name}/grid.xml": _serialize(root, raw)
                    for name, (root, raw) in self.trees.items()}
        if self.filemap is not None:
            replaced[_FILEMAP] = _serialize(*self.filemap)
        added = {f"Grids/{name}/grid.xml": _serialize(root, None)
                 for name, root in self.new_grids.items()}
        temporary = dest + ".writing"
        try:
            # The reader may already be closed; the copy reads its own handle.
            with zipfile.ZipFile(self.source.path) as source, \
                    zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as out:
                if any(entry in source.namelist() for entry in added):
                    raise PagesetError(
                        "A grid with that name already exists in this grid set."
                    )
                for info in source.infolist():
                    if info.filename in replaced:
                        fresh = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                        fresh.compress_type = zipfile.ZIP_DEFLATED
                        fresh.external_attr = info.external_attr
                        out.writestr(fresh, replaced[info.filename])
                        continue
                    with source.open(info) as reader, out.open(info, "w") as writer:
                        shutil.copyfileobj(reader, writer, 1024 * 1024)
                for entry, data in added.items():
                    out.writestr(entry, data)
            os.replace(temporary, dest)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)


# ---------------------------------------------------------------------------
# verification


def _entries(path: str) -> dict[str, tuple[int, int]]:
    with zipfile.ZipFile(path) as package:
        return {info.filename: (info.CRC, info.file_size) for info in package.infolist()}


def _speaks(cell: Grid3Cell | None, label: str, message: str | None) -> bool:
    return (cell is not None and cell.commands == ("Action.InsertText",)
            and cell.label == label and cell.message == (message or label))


def _blank_at(grid: Grid3Grid, position) -> bool:
    cell = grid.cell_at(*position)
    if cell is None:
        return position not in covered(grid)
    return cell.safe_blank


def verify(source_path: str, result_path: str, expect: dict, new_grids: dict) -> list[str]:
    """Everything that differs from the reviewed edit, as plain sentences.

    *expect* maps a grid name to ``{(x, y): spec}`` for every square the edit
    touched; *new_grids* maps each created grid to the grid it was shaped on.
    A spec is ``("blank",)``, ``("speak", label, message, border)``,
    ``("moved", original_cell, label, message)``, ``("jump", target, label)``
    or ``("back",)``. Anything the edit did not name must be unchanged.
    """
    problems: list[str] = []
    try:
        result = GridsetFile(result_path)
    except PagesetError as exc:
        return [f"the edited grid set could not be read back ({exc})"]
    with GridsetFile(source_path) as before, result:
        before_entries, after_entries = _entries(source_path), _entries(result_path)
        rewritten = {f"Grids/{name}/grid.xml" for name in [*expect, *new_grids]} | {_FILEMAP}
        for entry, signature in before_entries.items():
            if entry not in after_entries:
                problems.append(f"{entry} is missing from the edited grid set")
            elif entry not in rewritten and after_entries[entry] != signature:
                problems.append(f"{entry} changed although the edit did not touch it")
        extra = set(after_entries) - set(before_entries) - {
            f"Grids/{name}/grid.xml" for name in new_grids}
        problems.extend(f"{entry} appeared in the edited grid set" for entry in sorted(extra))
        names = set(result.names())
        for name in before.names():
            if name not in names:
                problems.append(f"grid “{name}” is missing after the edit")
                continue
            old, new = _semantic(before.grid(name)), _semantic(result.grid(name))
            touched = expect.get(name, {})
            if old["grid"] != new["grid"]:
                problems.append(f"grid “{name}” changed its layout")
            for position, value in old["cells"].items():
                if position not in touched and new["cells"].get(position) != value:
                    problems.append(f"cell {position} on “{name}” changed although it "
                                    "was not part of the edit")
            for position in set(new["cells"]) - set(old["cells"]) - set(touched):
                problems.append(f"cell {position} on “{name}” appeared although it was "
                                "not part of the edit")
        for name, parent in new_grids.items():
            if name not in names:
                problems.append(f"the new grid “{name}” is missing")
                continue
            grid, shape = result.grid(name), before.grid(parent)
            if (grid.cols, grid.rows) != (shape.cols, shape.rows):
                problems.append(f"the new grid “{name}” is not the size of “{parent}”")
            named = expect.get(name, {})
            for cell in grid.cells:
                if (cell.x, cell.y) not in named and not cell.safe_blank:
                    problems.append(f"cell {(cell.x, cell.y)} on the new grid “{name}” "
                                    "holds something the review did not name")
        for name, cells in expect.items():
            if name not in names:
                continue
            grid = result.grid(name)
            targets = result.jump_targets(name)
            for position, spec in cells.items():
                cell = grid.cell_at(*position)
                kind = spec[0]
                if kind == "blank" and not _blank_at(grid, position):
                    problems.append(f"cell {position} on “{name}” is not empty after the edit")
                elif kind == "speak":
                    _kind, label, message, border = spec
                    if not _speaks(cell, label, message):
                        problems.append(f"cell {position} on “{name}” does not say “{label}”")
                    elif border and cell.style.border != border:
                        problems.append(f"“{label}” on “{name}” lost its border colour")
                elif kind == "moved":
                    _kind, was, label, message = spec
                    if cell is None or not (
                        cell.commands == was.commands and cell.image == was.image
                        and cell.style == was.style and cell.label == label
                        and cell.message == (message or label)
                    ):
                        problems.append(f"“{was.label}” did not arrive intact at {position} "
                                        f"on “{name}”")
                elif kind == "jump":
                    _kind, target, label = spec
                    if (cell is None or cell.commands != ("Jump.To",) or cell.label != label
                            or targets.get(position) != target):
                        problems.append(f"cell {position} on “{name}” does not open “{target}”")
                elif kind == "back" and (cell is None or cell.commands != ("Jump.Back",)):
                    problems.append(f"the new grid “{name}” has no Back cell")
            for position, target in targets.items():
                if target not in names and position in cells:
                    problems.append(f"cell {position} on “{name}” opens “{target}”, "
                                    "which is not in the grid set")
    return problems


def _finish(writer: _Writer, source_path: str, dest: str, expect: dict,
            new_grids: dict) -> None:
    writer.save(dest)
    problems = verify(source_path, dest, expect, new_grids)
    if problems:
        os.remove(dest)
        raise GridsetVerificationError(problems)


class GridsetVerificationError(PagesetError):
    """The edited copy did not match the review; nothing was kept."""

    def __init__(self, problems: list[str]):
        super().__init__("Validation failed; nothing was saved.")
        self.problems = problems


# ---------------------------------------------------------------------------
# edits


def _position(grid: Grid3Grid, slot) -> tuple[int, int]:
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        raise PagesetError("Every grid position must be a non-negative whole number.")
    if slot >= grid.cols * grid.rows:
        raise PagesetError("A reviewed cell is outside the grid.")
    return slot % grid.cols, slot // grid.cols


def _speak_cell(grid: Grid3Grid, slot: int, what: str) -> Grid3Cell:
    cell = grid.cell_at(*_position(grid, slot))
    if cell is None or cell.safe_blank:
        raise PagesetError(f"The cell to {what} is empty. Reload the grid and review again.")
    kind = _cell_kind(cell)
    if kind != "speak":
        raise PagesetError(f"AAC Editor can't {what} “{cell.label}”: {LOCK_REASONS[kind]}")
    return cell


def _normalize_changes(changes) -> list[dict]:
    normalized = []
    for change in changes or ():
        entry = {"slot": change["slot"]}
        if change.get("label") is not None:
            entry["label"] = str(change["label"]).strip()
            if not entry["label"]:
                raise PagesetError("A changed cell needs a label.")
        if change.get("message") is not None:
            entry["message"] = str(change["message"]).strip()
        if "label" not in entry and "message" not in entry:
            raise PagesetError("A change must give the cell a new label or message.")
        normalized.append(entry)
    return normalized


def _border(item: dict) -> str | None:
    border = item.get("border_color")
    return hex_from_argb(border) if isinstance(border, int) else None


def edit_grid(source_path: str, dest: str, number: int, items=(), changes=(), removals=(),
              moves=(), expected_fingerprint: str | None = None) -> dict:
    """Add, change, move, and remove reviewed cells on one grid, into *dest*.

    The same rules as live Grid 3 editing (``grid3.edit_page``): only plain
    speaking cells can be changed, moved, or removed; every slot names the
    cell as it was reviewed; cells freed by a removal or a move can be reused
    by the same edit; and a label already on the grid is refused.
    """
    normalized = _normalize_items(list(items or []))
    changes = _normalize_changes(changes)
    removals = list(removals or ())
    moves = [{"slot": move["slot"], "to": move["to"]} for move in moves or ()]
    if not (normalized or changes or removals or moves):
        raise PagesetError("Add at least one word or phrase.")
    with GridsetFile(source_path) as source:
        name = source.name_for(number)
        grid = source.grid(name)
        if not expected_fingerprint:
            raise PagesetError(
                "The review fingerprint is required. Reload the grid and review again."
            )
        if fingerprint(grid) != expected_fingerprint:
            raise PagesetError(
                "This grid changed after the preview. Reload the grid and review the "
                "edit again."
            )
        changed = {change["slot"] for change in changes}
        moved = {move["slot"]: move["to"] for move in moves}
        if set(removals) & changed:
            raise PagesetError("A cell can't be changed and removed in the same edit.")
        if set(removals) & set(moved):
            raise PagesetError("A cell can't be moved and removed in the same edit.")
        if len(set(removals)) != len(removals) or len(moved) != len(moves):
            raise PagesetError("The reviewed edit names the same cell twice.")
        for slot in removals:
            _speak_cell(grid, slot, "remove")
        for change in changes:
            _speak_cell(grid, change["slot"], "change")
        for move in moves:
            _speak_cell(grid, move["slot"], "move")
        free = set(free_slots(grid))
        freed = set(removals) | set(moved)
        open_slots = sorted((free | freed) - set(moved.values()))
        for item in normalized:
            if item["slot"] is None:
                taken = {other["slot"] for other in normalized if other["slot"] is not None}
                spare = [slot for slot in open_slots if slot not in taken]
                if not spare:
                    raise PagesetError(
                        f"“{name}” has no room left. Remove a cell or choose another grid."
                    )
                item["slot"] = spare[0]
                open_slots.remove(spare[0])
        destinations = [move["to"] for move in moves] + [item["slot"] for item in normalized]
        if len(set(destinations)) != len(destinations):
            raise PagesetError("Review and place every new or moved cell in a different "
                               "empty space.")
        for slot in destinations:
            _position(grid, slot)
            if slot not in freed and slot not in free:
                raise PagesetError("The space to fill is not a safe empty Grid 3 cell.")
        existing = {
            cell.label.casefold() for cell in grid.cells
            if cell.label and (cell.y * grid.cols + cell.x) not in set(removals) | changed
        }
        planned = [item["label"].casefold() for item in normalized] + [
            change["label"].casefold() for change in changes if "label" in change
        ]
        duplicates = [label for label in planned if label in existing]
        if duplicates:
            raise PagesetError("Already on this grid: " + ", ".join(duplicates) + ".")
        if len(set(planned)) != len(planned):
            raise PagesetError("The reviewed vocabulary contains duplicate labels.")

        writer = _Writer(source)
        expect: dict[tuple[int, int], tuple] = {}
        for slot in removals:
            writer.blank(name, _position(grid, slot))
            expect[_position(grid, slot)] = ("blank",)
        for move in moves:
            source_position = _position(grid, move["slot"])
            target = _position(grid, move["to"])
            writer.move(name, source_position, target)
            expect.setdefault(source_position, ("blank",))
            was = grid.cell_at(*source_position)
            expect[target] = ("moved", was, was.label, was.message or was.label)
        for change in changes:
            was = grid.cell_at(*_position(grid, change["slot"]))
            position = _position(grid, moved.get(change["slot"], change["slot"]))
            label, message = _spoken_after_change(was, change)
            writer.change(name, position, label, message)
            if position in expect and expect[position][0] == "moved":
                expect[position] = ("moved", was, label, message)
            else:
                expect[position] = ("speak", label, message, None)
        style = writer.speaking_style(name)
        for item in normalized:
            position = _position(grid, item["slot"])
            border = _border(item)
            writer.write_speaking(name, position, item["label"], item["message"],
                                  _style(style, border))
            expect[position] = ("speak", item["label"], item["message"], border)
    _finish(writer, source_path, dest, {name: expect}, {})
    checks = {"target_grid": "pass", "content": "pass", "positions": "pass",
              "untouched_buttons": "pass", "package_entries": "pass"}
    if changes:
        checks["changed_content"] = "pass"
    if moves:
        checks["moved_buttons"] = "pass"
    if removals:
        checks["removed_buttons"] = "pass"
    return {
        "page": name, "page_id": number,
        "buttons": len(normalized), "changed": len(changes),
        "moved": len(moves), "removed": len(removals),
        "grid": {"cols": grid.cols, "rows": grid.rows},
        "checks": checks,
        "warnings": [NO_SYMBOLS_WARNING] if normalized else [],
    }


def _place(items: list[dict], grid: Grid3Grid, reserved: set[int]) -> list[dict]:
    """Give every item a slot on a fresh grid, keeping reviewed slots that are free."""
    capacity = grid.cols * grid.rows
    used = set(reserved)
    placed = []
    for item in items:
        slot = item.get("slot")
        if slot is not None and 0 <= slot < capacity and slot not in used:
            used.add(slot)
            placed.append({**item, "slot": slot})
        else:
            placed.append({**item, "slot": None})
    spare = [slot for slot in range(capacity) if slot not in used]
    for item in placed:
        if item["slot"] is None:
            if not spare:
                raise PagesetError(
                    f"There are more words than a {grid.cols} by {grid.rows} grid holds."
                )
            item["slot"] = spare.pop(0)
    return placed


def add_grid(source_path: str, dest: str, title, items, parent_number: int,
             link_slot: int | None = None) -> dict:
    """Create a grid shaped like the parent, fill it, and link it from the parent.

    The new grid matches what live Grid 3 creates: the parent's size, and a
    Back cell in its top-left square. The link goes in the parent's first
    empty cell unless *link_slot* names another empty one.
    """
    title = _clean_title(title)
    normalized = _normalize_items(list(items or []))
    if not normalized:
        raise PagesetError("Add at least one word or phrase.")
    with GridsetFile(source_path) as source:
        parent = source.name_for(parent_number)
        if title.casefold() in {name.casefold() for name in source.names()}:
            raise PagesetError(f"A grid called “{title}” is already in this grid set.")
        parent_grid = source.grid(parent)
        free = free_slots(parent_grid)
        if link_slot is None:
            if not free:
                raise PagesetError(f"“{parent}” has no empty cell to link the new grid from.")
            link_slot = free[0]
        elif link_slot not in free:
            raise PagesetError("The cell chosen for the link is not empty.")
        placed = _place(normalized, parent_grid, {0})
        writer = _Writer(source)
        writer.add_grid(title, parent)
        style = writer.speaking_style(parent)
        expect_new: dict[tuple[int, int], tuple] = {(0, 0): ("back",)}
        for item in placed:
            position = _position(parent_grid, item["slot"])
            border = _border(item)
            writer.write_speaking(title, position, item["label"], item["message"],
                                  _style(style, border))
            expect_new[position] = ("speak", item["label"], item["message"], border)
        link_position = _position(parent_grid, link_slot)
        writer.link(parent, link_position, title, title)
    _finish(writer, source_path, dest,
            {title: expect_new, parent: {link_position: ("jump", title, title)}},
            {title: parent})
    return {
        "page_id": page_id(title), "page": title, "parent": parent,
        "buttons": len(placed), "nav_button_id": link_slot,
        "grid": {"cols": parent_grid.cols, "rows": parent_grid.rows},
        "checks": {"new_grid": "pass", "link": "pass", "content": "pass",
                   "untouched_buttons": "pass", "package_entries": "pass"},
        "warnings": [NO_SYMBOLS_WARNING],
    }


# ---------------------------------------------------------------------------
# Open Board Format


def to_boardset(path: str) -> dict:
    """Every grid as a canonical board set (see ``obf``), read-only."""
    with GridsetFile(path) as source:
        names = source.names()
        known = set(names)
        boards, skipped = [], []
        for name in names:
            grid = source.grid(name)
            targets = source.jump_targets(name)
            cells = []
            for cell in sorted(grid.cells, key=lambda c: (c.y, c.x)):
                if cell.safe_blank:
                    continue
                kind = _cell_kind(cell)
                label = cell.label
                if kind == "speak":
                    cells.append({
                        "row": cell.y, "col": cell.x, "label": label,
                        "message": None if cell.message in (None, label) else cell.message,
                        "border": cell.style.border, "link": None,
                    })
                elif kind == "jump" and cell.commands == ("Jump.To",):
                    target = targets.get((cell.x, cell.y))
                    if target not in known or target == name:
                        obf._skip(skipped, name, label,
                                  "opens a grid that is not in this grid set")
                        continue
                    cells.append({
                        "row": cell.y, "col": cell.x, "label": label or target,
                        "message": None, "border": cell.style.border, "link": target,
                    })
                elif kind == "jump":
                    obf._skip(skipped, name, label or "Back",
                              "is Grid 3 navigation (Back or Home) with no Open Board "
                              "equivalent this app writes")
                elif kind == "span":
                    obf._skip(skipped, name, label,
                              "covers more than one square, which Open Board cannot describe")
                elif kind == "action":
                    obf._skip(skipped, name, label,
                              "runs a Grid 3 command Open Board cannot describe")
                else:
                    obf._skip(skipped, name, label,
                              "holds Grid 3 content (a word list, picture, or app)")
            boards.append({"id": name, "name": name, "locale": None,
                           "rows": grid.rows, "columns": grid.cols, "cells": cells})
        root = source.start_grid() or names[0]
    return {"format": obf.FORMAT, "root": root, "boards": obf._order_boards(boards, root),
            "skipped": skipped, "notes": [SYMBOLS_NOTE]}


def plan_import(path: str, boardset: dict, parent_number: int) -> dict:
    """``obf.plan_import`` against a grid set: every board becomes a grid.

    Grid names must be usable as folder names, and the top-left square of
    every new grid holds Grid 3's Back cell, so a board's own top-left button
    moves to the next empty square (and is named in the plan when it does).
    """
    with GridsetFile(path) as source:
        parent = source.name_for(parent_number)
        parent_grid = source.grid(parent)
        existing = source.names()
    cleaned = dict(boardset)
    cleaned["boards"] = [{**board, "name": _safe_title(board["name"])}
                         for board in boardset.get("boards") or []]
    plan = obf.plan_import(cleaned, grid=(parent_grid.cols, parent_grid.rows),
                           existing_titles=existing)
    capacity = parent_grid.cols * parent_grid.rows
    for page in plan["pages"]:
        used = {cell["slot"] for cell in page["cells"]}
        spare = [slot for slot in range(1, capacity) if slot not in used]
        kept = []
        for cell in page["cells"]:
            if cell["slot"] == 0:
                if not spare:
                    plan["skipped"].append({
                        "board": page["name"], "label": cell["label"],
                        "reason": "has no room once Grid 3's Back cell takes the top-left square",
                    })
                    continue
                cell = {**cell, "slot": spare.pop(0)}
                page["rearranged"] = True
            kept.append(cell)
        page["cells"] = kept
    plan["counts"]["buttons"] = sum(len(page["cells"]) for page in plan["pages"])
    plan["counts"]["links"] = sum(1 for page in plan["pages"]
                                  for cell in page["cells"] if cell["link"])
    plan["parent"] = parent
    return plan


def import_boards(source_path: str, dest: str, plan: dict, parent_number: int) -> dict:
    """Write every planned board as a new grid, linked as the boards were, in one go."""
    with GridsetFile(source_path) as source:
        parent = source.name_for(parent_number)
        parent_grid = source.grid(parent)
        free = free_slots(parent_grid)
        if not free:
            raise PagesetError(f"“{parent}” has no empty cell to link the boards from.")
        titles = {page["board_id"]: _clean_title(page["title"]) for page in plan["pages"]}
        taken = {name.casefold() for name in source.names()}
        if any(title.casefold() in taken for title in titles.values()):
            raise PagesetError("A grid with one of these names is already in this grid set. "
                               "Review the import again.")
        writer = _Writer(source)
        expect: dict[str, dict] = {}
        new_grids = {}
        style = writer.speaking_style(parent)
        for page in plan["pages"]:
            title = titles[page["board_id"]]
            writer.add_grid(title, parent)
            new_grids[title] = parent
            cells = {(0, 0): ("back",)}
            for cell in page["cells"]:
                position = _position(parent_grid, cell["slot"])
                if cell["link"]:
                    target = titles[cell["link"]]
                    writer.link(title, position, target, cell["label"])
                    cells[position] = ("jump", target, cell["label"])
                else:
                    border = cell.get("border_color")
                    writer.write_speaking(title, position, cell["label"], cell["message"],
                                          _style(style, border))
                    cells[position] = ("speak", cell["label"], cell["message"], border)
            expect[title] = cells
        root_title = titles[plan["root"]] if plan["root"] in titles else next(iter(titles.values()))
        link_position = _position(parent_grid, free[0])
        writer.link(parent, link_position, root_title, root_title)
        expect[parent] = {link_position: ("jump", root_title, root_title)}
    _finish(writer, source_path, dest, expect, new_grids)
    return {
        "pages": len(new_grids),
        "page_ids": [page_id(title) for title in new_grids],
        "buttons": plan["counts"]["buttons"],
        "links": plan["counts"]["links"],
        "parent": parent,
        "checks": {"new_grids": "pass", "links": "pass", "content": "pass",
                   "untouched_buttons": "pass", "package_entries": "pass"},
    }


def describe(path: str) -> dict:
    """A JSON-ready summary: format, grids, and the start grid."""
    with GridsetFile(path) as source:
        cols, rows = source.grid_dimension()
        return {"format": FORMAT, "grid": {"cols": cols, "rows": rows},
                "pages": source.pages(), "home_page_id": source.home_page_id()}


def limits() -> dict:
    return {"can": list(CAN_DO), "cannot": list(CANNOT_DO)}


__all__ = [
    "CANNOT_DO", "CAN_DO", "FORMAT", "GridsetFile", "GridsetVerificationError",
    "add_grid", "describe", "edit_grid", "fingerprint", "free_slots", "import_boards",
    "is_gridset_file", "limits", "page_id", "plan_import", "to_boardset", "verify",
]

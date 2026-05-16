from __future__ import annotations

import re
from pathlib import Path


def parse_snbt_string(raw_value: str) -> str:
    match = re.match(r'^"((?:\\.|[^"\\])*)"', raw_value.strip())

    if match is None:
        raise ValueError(f"Could not parse SNBT string value: {raw_value}")

    return decode_snbt_string(match.group(1))


def parse_snbt_string_list(raw_value: str) -> list[str]:
    return [decode_snbt_string(match) for match in re.findall(r'"((?:\\.|[^"\\])*)"', raw_value)]


def decode_snbt_string(value: str) -> str:
    return (
        value.replace(r"\\", "\\")
        .replace(r"\"", '"')
        .replace(r"\n", "\n")
        .replace(r"\t", "\t")
    )


def clean_minecraft_text(value: str) -> str:
    without_hex_colors = re.sub(r"&#[0-9A-Fa-f]{6}", "", value)
    without_ampersand_formatting = re.sub(
        r"&(?:[0-9A-FK-ORZa-fk-orz]|#[0-9A-Fa-f]{6})",
        "",
        without_hex_colors,
    )
    without_images = re.sub(r"\{image:[^}]+\}", "", without_ampersand_formatting)
    cleaned = re.sub(r"\n{3,}", "\n\n", without_images).strip()

    return cleaned


def value_depth(value: str) -> int:
    depth = 0
    in_string = False
    escaped = False

    for character in value:
        if escaped:
            escaped = False
            continue

        if character == "\\":
            escaped = True
            continue

        if character == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if character == "[":
            depth += 1

        if character == "]":
            depth -= 1

    return depth


def required_top_level_string_value(raw_snbt: str, key: str, source_file: Path) -> str:
    value = optional_top_level_string_value(raw_snbt, key)

    if value is None:
        raise ValueError(f"Could not find required top-level key '{key}' in {source_file}")

    return value


def optional_top_level_string_value(raw_snbt: str, key: str) -> str | None:
    depth = 0

    for line in raw_snbt.splitlines():
        stripped_line = line.strip()

        if depth == 1:
            match = re.fullmatch(rf'{re.escape(key)}:\s*"([^"]*)"', stripped_line)

            if match is not None:
                return match.group(1)

        depth = updated_depth(depth, line)

    return None


def optional_top_level_float_value(raw_snbt: str, key: str) -> float | None:
    depth = 0

    for line in raw_snbt.splitlines():
        stripped_line = line.strip()

        if depth == 1:
            match = re.fullmatch(
                rf"{re.escape(key)}:\s*(-?\d+(?:\.\d+)?)(?:[dDfFlLsSbB])?",
                stripped_line,
            )

            if match is not None:
                return float(match.group(1))

        depth = updated_depth(depth, line)

    return None


def optional_top_level_icon_id(raw_snbt: str) -> str | None:
    icon_block = extract_top_level_object(raw_snbt, "icon")

    if icon_block is None:
        return None

    custom_icon_match = re.search(r'"ftbquests:icon":\s*"([^"]+)"', icon_block)

    if custom_icon_match is not None:
        return custom_icon_match.group(1)

    id_match = re.search(r'^\s*id:\s*"([^"]+)"', icon_block, re.MULTILINE)

    if id_match is None:
        return None

    return id_match.group(1)


def extract_item_id_from_item_block(item_block: str | None) -> str | None:
    if item_block is None:
        return None

    id_match = re.search(r'\bid:\s*"([^"]+)"', item_block)

    if id_match is None:
        return None

    return id_match.group(1)


def extract_item_count_from_item_block(item_block: str | None) -> int | None:
    if item_block is None:
        return None

    count_match = re.search(
        r"\b(?:Count|count):\s*(-?\d+)(?:[dDfFlLsSbB])?",
        item_block,
    )

    if count_match is None:
        return None

    return int(count_match.group(1))


def extract_top_level_object(raw_snbt: str, key: str) -> str | None:
    return extract_top_level_value(
        raw_snbt=raw_snbt,
        key=key,
        opener="{",
    )


def extract_top_level_list(raw_snbt: str, key: str) -> str | None:
    return extract_top_level_value(
        raw_snbt=raw_snbt,
        key=key,
        opener="[",
    )


def extract_top_level_value(raw_snbt: str, key: str, opener: str) -> str | None:
    depth = 0
    position = 0

    for line in raw_snbt.splitlines(keepends=True):
        stripped_line = line.strip()

        if depth == 1 and stripped_line.startswith(f"{key}:"):
            opener_index = line.find(opener)

            if opener_index == -1:
                return None

            value_start = position + opener_index
            value_end = find_matching_delimiter(raw_snbt, value_start)

            return raw_snbt[value_start : value_end + 1]

        depth = updated_depth(depth, line)
        position += len(line)

    return None


def split_top_level_objects(raw_snbt_list: str) -> list[str]:
    stripped_list = raw_snbt_list.strip()

    if not stripped_list.startswith("[") or not stripped_list.endswith("]"):
        raise ValueError("Expected an SNBT list enclosed by '[' and ']'.")

    list_body = stripped_list[1:-1]

    objects: list[str] = []
    depth = 0
    object_start: int | None = None
    in_string = False
    escaped = False

    for index, character in enumerate(list_body):
        if escaped:
            escaped = False
            continue

        if character == "\\":
            escaped = True
            continue

        if character == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if character == "{":
            if depth == 0:
                object_start = index

            depth += 1
            continue

        if character == "}":
            depth -= 1

            if depth == 0 and object_start is not None:
                objects.append(list_body[object_start : index + 1])
                object_start = None

    if depth != 0:
        raise ValueError("Unbalanced braces while splitting SNBT list objects.")

    return objects


def find_matching_delimiter(raw_snbt: str, opening_index: int) -> int:
    opener = raw_snbt[opening_index]

    if opener == "{":
        closer = "}"
    elif opener == "[":
        closer = "]"
    else:
        raise ValueError(f"Unsupported opening delimiter: {opener}")

    depth = 0
    in_string = False
    escaped = False

    for index in range(opening_index, len(raw_snbt)):
        character = raw_snbt[index]

        if escaped:
            escaped = False
            continue

        if character == "\\":
            escaped = True
            continue

        if character == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if character == opener:
            depth += 1

        if character == closer:
            depth -= 1

            if depth == 0:
                return index

    raise ValueError(f"Could not find matching closing delimiter for {opener}.")


def updated_depth(current_depth: int, line: str) -> int:
    depth = current_depth
    in_string = False
    escaped = False

    for character in line:
        if escaped:
            escaped = False
            continue

        if character == "\\":
            escaped = True
            continue

        if character == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if character in "{[":
            depth += 1

        if character in "}]":
            depth -= 1

    return depth


def title_from_filename(filename: str) -> str:
    return filename.replace("_2r_", " ").replace("_6", "").replace("_", " ").title()
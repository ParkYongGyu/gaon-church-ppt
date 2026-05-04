#!/usr/bin/env python3
"""
input/next_sunday.txt → output/YY_MM_DD.pptx 전체 파이프라인.

사용법:
  python3 scripts/generate_ppt.py
  python3 scripts/generate_ppt.py input/next_sunday.txt   # 입력 파일 지정
"""

import re
import sys
import tempfile
from pathlib import Path

from lxml import etree

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.update_slides import (
    A,
    P,
    build_slide12,
    insert_sermon_slides,
    pack,
    split_by_language,
    unpack,
    verify,
)

TEMPLATE = PROJECT_ROOT / "templates" / "master_slides.pptx"
OUTPUT_DIR = PROJECT_ROOT / "output"


def parse_input(input_path: Path) -> dict:
    text = input_path.read_text(encoding="utf-8")
    lines = text.strip().split("\n")
    data = {}
    for line in lines:
        if " : " in line:
            key, _, val = line.partition(" : ")
            data[key.strip()] = val.strip()
        elif line.strip() == "":
            break
    return data


def date_to_filename(date_str: str) -> str:
    parts = date_str.split("-")
    y = parts[0][-2:]
    m = parts[1].zfill(2)
    d = parts[2].zfill(2)
    return f"{y}_{m}_{d}.pptx"


def update_slide10(work_dir: Path, prayer: str):
    slide_path = work_dir / "ppt" / "slides" / "slide10.xml"
    tree = etree.parse(str(slide_path))
    runs = list(tree.iter(f"{{{A}}}r"))

    parts = prayer.rsplit(" ", 1)
    if len(parts) == 2:
        name, title = parts
    else:
        name, title = prayer, ""

    runs[2].find(f"{{{A}}}t").text = name
    t3 = runs[3].find(f"{{{A}}}t")
    t3.text = f" {title}" if title else ""

    tree.write(
        str(slide_path), xml_declaration=True, encoding="UTF-8", standalone="yes"
    )


def update_slide11(work_dir: Path, sermon_title: str, scripture_ref: str):
    slide_path = work_dir / "ppt" / "slides" / "slide11.xml"
    tree = etree.parse(str(slide_path))
    root = tree.getroot()
    txBody = root.find(f".//{{{P}}}txBody")
    p_elem = txBody.find(f"{{{A}}}p")
    children = list(p_elem)

    br_count = 0
    keep = []
    for child in children:
        keep.append(child)
        if child.tag == f"{{{A}}}br":
            br_count += 1
            if br_count == 3:
                break

    for child in children:
        p_elem.remove(child)
    for elem in keep:
        p_elem.append(elem)

    def add_runs(parent, text):
        for lang, seg in split_by_language(text):
            r = etree.SubElement(parent, f"{{{A}}}r")
            rpr = etree.SubElement(r, f"{{{A}}}rPr")
            rpr.set("lang", "ko-KR" if lang == "ko" else "en-US")
            rpr.set("altLang", "en-US" if lang == "ko" else "ko-KR")
            rpr.set("sz", "3600")
            rpr.set("dirty", "0")
            fill = etree.SubElement(rpr, f"{{{A}}}solidFill")
            etree.SubElement(fill, f"{{{A}}}srgbClr").set("val", "FFFFFF")
            t = etree.SubElement(r, f"{{{A}}}t")
            if " " in seg:
                t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            t.text = seg

    add_runs(p_elem, sermon_title)
    for _ in range(2):
        etree.SubElement(p_elem, f"{{{A}}}br")
    add_runs(p_elem, scripture_ref)

    xml_bytes = etree.tostring(
        tree, xml_declaration=True, encoding="UTF-8", standalone="yes"
    )
    slide_path.write_bytes(xml_bytes)


def main():
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "input" / "next_sunday.txt"
    if not input_path.exists():
        sys.exit(f"입력 파일이 없습니다: {input_path}")

    sermon_pptx = None
    for arg in sys.argv[2:]:
        if arg.endswith(".pptx"):
            sermon_pptx = Path(arg)
            if not sermon_pptx.exists():
                sys.exit(f"설교 PPT 파일이 없습니다: {sermon_pptx}")

    data = parse_input(input_path)
    date_str = data.get("날짜", "")
    prayer = data.get("대표기도", "")
    sermon_title = data.get("설교제목", "")
    scripture_ref = data.get("성경본문", "")

    if not date_str or not sermon_title:
        sys.exit("입력 파일에 날짜 또는 설교제목이 없습니다.")

    output_name = date_to_filename(date_str)
    output_path = OUTPUT_DIR / output_name

    print(f"날짜: {date_str}")
    print(f"대표기도: {prayer}")
    print(f"설교제목: {sermon_title}")
    print(f"성경본문: {scripture_ref}")
    if sermon_pptx:
        print(f"설교 PPT: {sermon_pptx.name}")
    print()

    with tempfile.TemporaryDirectory() as work_dir:
        work = Path(work_dir)
        unpack(TEMPLATE, work)

        print("Slide 10: 대표기도 수정")
        update_slide10(work, prayer)

        print("Slide 11: 설교제목 + 성경본문 수정")
        update_slide11(work, sermon_title, scripture_ref)

        print("Slide 12: 성경 본문 생성")
        build_slide12(work, input_path)

        if sermon_pptx:
            print("\n설교 슬라이드 삽입:")
            insert_sermon_slides(work, sermon_pptx)

        print()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        pack(work, output_path)

    print()
    verify(output_path)
    print(f"\n출력: {output_path}")


if __name__ == "__main__":
    main()

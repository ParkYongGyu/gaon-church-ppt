#!/usr/bin/env python3
"""
가온교회 주일 슬라이드 자동 변경 보조 도구

사용법:
  python3 scripts/update_slides.py unpack <pptx> <work_dir>
      → pptx를 work_dir에 풀어 XML 직접 수정 가능 상태로 만듦
  python3 scripts/update_slides.py pack <work_dir> <output.pptx>
      → 수정된 work_dir을 pptx로 다시 패킹 ([Content_Types].xml 우선)
  python3 scripts/update_slides.py verify <pptx>
      → slide 10/11/12의 텍스트만 추출하여 출력 (변경 검증용)
  python3 scripts/update_slides.py split-title <설교제목>
      → 설교제목 한 줄을 한글/영문 경계로 분할하여 (lang, text) 튜플 출력
  python3 scripts/update_slides.py build-slide12 <work_dir> <input_file>
      → input 파일에서 성경 본문을 파싱하여 slide 12 생성 (넘치면 추가 슬라이드)

이 스크립트는 stdlib(zipfile, re)와 lxml만 사용합니다.
lxml이 없으면 'pip3 install lxml'.
"""

import math
import re
import sys
import shutil
import zipfile
from copy import deepcopy
from pathlib import Path

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
A = NS["a"]
P = NS["p"]
R = NS["r"]
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
SLIDE_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"

KOREAN_RE = re.compile(r"[가-힣ㄱ-ㆎ]")

# --- 높이 추정 상수 (EMU 단위, 1pt = 12700 EMU) --------------------------------

TEXTBOX_HEIGHT_EMU = 4526876
TEXTBOX_WIDTH_PT = 697.0
# 한 줄에 들어가는 폭(한글 전각 기준 단위). 공백/숫자/문장부호는 절반 폭으로 계산.
KO_WIDTH_PER_LINE = 36.0
ASCII_WIDTH_RATIO = 0.55
TITLE_HEIGHT_PT = 40.0
BODY_LINE_HEIGHT_PT = 34.8
SPACER_HEIGHT_PT = 25.0
# 프로젝터에서 하단이 잘려 보이지 않는 영역 보호: 본문 1줄 일찍 페이지를 넘긴다
PROJECTOR_SAFE_LINES = 1


# --- 한글/영문 경계 분할 -----------------------------------------------------


def is_korean_char(ch: str) -> bool:
    return bool(KOREAN_RE.match(ch))


def split_by_language(text: str):
    if not text:
        return []

    segments = []
    current_lang = None
    current_buf = []

    for ch in text:
        if ch.isspace():
            if current_lang is None:
                current_buf.append(ch)
                continue
            current_buf.append(ch)
            continue

        ch_lang = "ko" if is_korean_char(ch) else "en"

        if current_lang is None:
            current_lang = ch_lang
            current_buf.append(ch)
        elif ch_lang == current_lang:
            current_buf.append(ch)
        else:
            segments.append((current_lang, "".join(current_buf)))
            current_lang = ch_lang
            current_buf = [ch]

    if current_buf:
        segments.append((current_lang or "en", "".join(current_buf)))

    return segments


# --- 성경 본문 파싱 -----------------------------------------------------------


def parse_scripture_blocks(input_path: Path):
    """input/next_sunday.txt에서 성경 본문 블록들을 파싱.
    Returns: [(ref, body_text), ...]
    """
    text = input_path.read_text(encoding="utf-8")
    lines = text.strip().split("\n")

    body_start = 0
    for i, line in enumerate(lines):
        if line.strip() == "" and i > 0:
            if any(
                lines[j].startswith(
                    ("날짜", "대표기도", "설교제목", "설교자", "성경본문")
                )
                for j in range(i)
            ):
                body_start = i + 1
                break

    body_lines = lines[body_start:]
    blocks = []
    current_ref = None
    current_body_lines = []
    ref_pattern = re.compile(r"^[가-힣]+\s+\d+:\d+")

    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            if current_ref and current_body_lines:
                blocks.append((current_ref, "\n".join(current_body_lines)))
                current_ref = None
                current_body_lines = []
            continue
        if ref_pattern.match(stripped) and not current_body_lines:
            current_ref = stripped
        elif current_ref:
            current_body_lines.append(stripped)

    if current_ref and current_body_lines:
        blocks.append((current_ref, "\n".join(current_body_lines)))

    return blocks


# --- 높이 추정 ----------------------------------------------------------------


def _verse_lines(ref: str, body: str):
    """본문을 절 단위 라인으로 분할. 절 번호가 없는 단일 절은 ref에서 유추해 붙인다."""
    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    if len(lines) == 1 and not re.match(r"^\d+", lines[0]):
        m = re.search(r":(\d+)", ref)
        if m:
            lines[0] = f"{m.group(1)} {lines[0]}"
    return lines


def _effective_width(text: str) -> float:
    """렌더링 폭 추정 (한글 전각 = 1.0, 공백/숫자/영문/문장부호 = 절반 폭)."""
    return sum(
        1.0 if KOREAN_RE.match(ch) else ASCII_WIDTH_RATIO for ch in text
    )


def _verse_height_pt(line: str) -> float:
    """절 한 줄(문단)이 차지할 예상 높이(pt)."""
    wrapped = max(1, math.ceil(_effective_width(line) / KO_WIDTH_PER_LINE))
    return wrapped * BODY_LINE_HEIGHT_PT


def split_blocks_into_pages(blocks):
    """본문 블록들을 페이지별로 분배.
    - 절마다 새 문단이므로 절 단위로 높이를 계산한다.
    - 한 블록이 페이지를 넘으면 절 경계에서 잘라 다음 페이지로 넘기고
      이어지는 페이지의 제목에는 "(계속)"을 붙인다.
    - 프로젝터 하단 잘림 보호를 위해 PROJECTOR_SAFE_LINES 줄만큼 일찍 넘긴다.
    Returns: [[(ref, body), ...], [(ref, body), ...], ...]
    """
    max_height_pt = (
        TEXTBOX_HEIGHT_EMU / 12700.0 - PROJECTOR_SAFE_LINES * BODY_LINE_HEIGHT_PT
    )
    pages = []
    page = []  # [(title, [verses])]
    height = 0.0

    def close_page():
        nonlocal page, height
        if page:
            pages.append([(title, "\n".join(vs)) for title, vs in page])
            page = []
            height = 0.0

    for ref, body in blocks:
        verses = _verse_lines(ref, body)
        continued = False
        i = 0
        while i < len(verses):
            spacer = SPACER_HEIGHT_PT if page else 0.0
            title = f"{ref} (계속)" if continued else ref
            block_h = spacer + TITLE_HEIGHT_PT
            taken = []
            while i < len(verses):
                vh = _verse_height_pt(verses[i])
                if height + block_h + vh > max_height_pt and (taken or page):
                    break
                block_h += vh
                taken.append(verses[i])
                i += 1
            if taken:
                page.append((title, taken))
                height += block_h
                continued = True
            if i < len(verses):
                close_page()

    close_page()
    return pages


# --- XML 헬퍼 (Slide 12 빌드) -------------------------------------------------


def _make_rpr(is_ko: bool):
    rpr = etree.SubElement(etree.Element("dummy"), f"{{{A}}}rPr")
    if is_ko:
        rpr.set("lang", "ko-KR")
        rpr.set("altLang", "en-US")
    else:
        rpr.set("lang", "en-US")
        rpr.set("altLang", "ko-KR")
    rpr.set("sz", "2400")
    rpr.set("b", "1")
    rpr.set("dirty", "0")
    fill = etree.SubElement(rpr, f"{{{A}}}solidFill")
    scheme = etree.SubElement(fill, f"{{{A}}}schemeClr")
    scheme.set("val", "tx2")
    etree.SubElement(scheme, f"{{{A}}}lumMod").set("val", "20000")
    etree.SubElement(scheme, f"{{{A}}}lumOff").set("val", "80000")
    return rpr


def _make_run(text: str, is_ko: bool):
    r = etree.Element(f"{{{A}}}r")
    r.append(_make_rpr(is_ko))
    t = etree.SubElement(r, f"{{{A}}}t")
    if " " in text:
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    return r


def _make_end_para_rpr():
    rpr = etree.Element(f"{{{A}}}endParaRPr")
    rpr.set("lang", "en-US")
    rpr.set("altLang", "ko-KR")
    rpr.set("sz", "1600")
    rpr.set("b", "1")
    rpr.set("dirty", "0")
    fill = etree.SubElement(rpr, f"{{{A}}}solidFill")
    scheme = etree.SubElement(fill, f"{{{A}}}schemeClr")
    scheme.set("val", "tx2")
    etree.SubElement(scheme, f"{{{A}}}lumMod").set("val", "20000")
    etree.SubElement(scheme, f"{{{A}}}lumOff").set("val", "80000")
    return rpr


def _make_title_paragraph(ref_text: str):
    p = etree.Element(f"{{{A}}}p")
    for text, is_ko in _split_lang(ref_text):
        p.append(_make_run(text, is_ko))
    p.append(_make_end_para_rpr())
    return p


def _make_body_paragraph(text: str):
    p = etree.Element(f"{{{A}}}p")
    ppr = etree.SubElement(p, f"{{{A}}}pPr")
    lnSpc = etree.SubElement(ppr, f"{{{A}}}lnSpc")
    etree.SubElement(lnSpc, f"{{{A}}}spcPts").set("val", "3480")
    for t, is_ko in _split_lang(text):
        p.append(_make_run(t, is_ko))
    return p


def _make_spacer_paragraph():
    p = etree.Element(f"{{{A}}}p")
    ppr = etree.SubElement(p, f"{{{A}}}pPr")
    ppr.set("marL", "457200")
    ppr.set("indent", "-457200")
    lnSpc = etree.SubElement(ppr, f"{{{A}}}lnSpc")
    etree.SubElement(lnSpc, f"{{{A}}}spcPct").set("val", "150000")
    p.append(_make_end_para_rpr())
    return p


def _split_lang(text: str):
    """split_by_language wrapper returning (text, is_korean) tuples."""
    segs = split_by_language(text)
    return [(seg, lang == "ko") for lang, seg in segs]


def _build_txbody_paragraphs(blocks):
    """성경 본문 블록 리스트 → <a:p> 엘리먼트 리스트.
    절마다 새 문단을 만들어 절 번호가 항상 줄 머리에 보이게 한다."""
    paragraphs = []
    for i, (ref, body) in enumerate(blocks):
        if i > 0:
            paragraphs.append(_make_spacer_paragraph())
        paragraphs.append(_make_title_paragraph(ref))
        for verse in body.split("\n"):
            if verse.strip():
                paragraphs.append(_make_body_paragraph(verse.strip()))
    return paragraphs


# --- 슬라이드 추가 (PPTX 구조 업데이트) -----------------------------------------


def _next_slide_number(work_dir: Path) -> int:
    slides_dir = work_dir / "ppt" / "slides"
    existing = [
        int(f.stem.replace("slide", ""))
        for f in slides_dir.glob("slide*.xml")
        if f.stem.replace("slide", "").isdigit()
    ]
    return max(existing) + 1 if existing else 1


def _find_slide12_rId(work_dir: Path) -> str:
    """presentation.xml.rels에서 slide12.xml의 rId를 찾는다."""
    rels_path = work_dir / "ppt" / "_rels" / "presentation.xml.rels"
    tree = etree.parse(str(rels_path))
    for rel in tree.findall(f"{{{REL_NS}}}Relationship"):
        if rel.get("Target") == "slides/slide12.xml":
            return rel.get("Id")
    return ""


def _find_slide12_sldId(work_dir: Path, rid: str) -> str:
    """presentation.xml에서 slide12의 sldId를 찾는다."""
    pres_path = work_dir / "ppt" / "presentation.xml"
    tree = etree.parse(str(pres_path))
    root = tree.getroot()
    for sld in root.iter(f"{{{P}}}sldId"):
        if sld.get(f"{{{R}}}id") == rid:
            return sld.get("id")
    return ""


def add_overflow_slide(work_dir: Path, blocks, page_index: int) -> str:
    """slide 12 구조를 복제하여 새 슬라이드를 추가하고 presentation에 등록.
    Returns: 새 슬라이드 파일 경로.
    """
    slide_num = _next_slide_number(work_dir)
    slides_dir = work_dir / "ppt" / "slides"
    rels_dir = slides_dir / "_rels"

    # 1. slide12.xml을 기반으로 새 슬라이드 XML 생성
    slide12_path = slides_dir / "slide12.xml"
    tree = etree.parse(str(slide12_path))
    root = tree.getroot()

    txBody = root.find(f".//{{{P}}}txBody")
    bodyPr = txBody.find(f"{{{A}}}bodyPr")
    lstStyle = txBody.find(f"{{{A}}}lstStyle")

    for p in txBody.findall(f"{{{A}}}p"):
        txBody.remove(p)

    for para in _build_txbody_paragraphs(blocks):
        txBody.append(para)

    new_slide_path = slides_dir / f"slide{slide_num}.xml"
    xml_bytes = etree.tostring(
        tree, xml_declaration=True, encoding="UTF-8", standalone="yes"
    )
    new_slide_path.write_bytes(xml_bytes)

    # 2. rels 파일 복사 (slide12와 동일한 레이아웃 참조)
    slide12_rels = rels_dir / "slide12.xml.rels"
    new_rels = rels_dir / f"slide{slide_num}.xml.rels"
    shutil.copy2(slide12_rels, new_rels)

    # 3. [Content_Types].xml에 추가
    ct_path = work_dir / "[Content_Types].xml"
    ct_tree = etree.parse(str(ct_path))
    ct_root = ct_tree.getroot()
    override = etree.SubElement(ct_root, f"{{{CT_NS}}}Override")
    override.set("PartName", f"/ppt/slides/slide{slide_num}.xml")
    override.set(
        "ContentType",
        "application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
    )
    ct_tree.write(str(ct_path), xml_declaration=True, encoding="UTF-8", standalone=True)

    # 4. presentation.xml.rels에 새 relationship 추가
    pres_rels_path = work_dir / "ppt" / "_rels" / "presentation.xml.rels"
    pres_rels_tree = etree.parse(str(pres_rels_path))
    pres_rels_root = pres_rels_tree.getroot()

    existing_rids = [
        int(r.get("Id").replace("rId", ""))
        for r in pres_rels_root.findall(f"{{{REL_NS}}}Relationship")
        if r.get("Id", "").startswith("rId")
    ]
    new_rid_num = max(existing_rids) + 1
    new_rid = f"rId{new_rid_num}"

    new_rel = etree.SubElement(pres_rels_root, f"{{{REL_NS}}}Relationship")
    new_rel.set("Id", new_rid)
    new_rel.set("Type", SLIDE_TYPE)
    new_rel.set("Target", f"slides/slide{slide_num}.xml")
    pres_rels_tree.write(
        str(pres_rels_path), xml_declaration=True, encoding="UTF-8", standalone=True
    )

    # 5. presentation.xml의 sldIdLst에 slide 12 바로 뒤에 삽입
    pres_path = work_dir / "ppt" / "presentation.xml"
    pres_tree = etree.parse(str(pres_path))
    pres_root = pres_tree.getroot()

    sld_id_lst = pres_root.find(f"{{{P}}}sldIdLst")
    slide12_rid = _find_slide12_rId(work_dir)

    existing_ids = [
        int(s.get("id")) for s in sld_id_lst.findall(f"{{{P}}}sldId")
    ]
    new_id = max(existing_ids) + 1

    # slide12의 위치를 찾아 page_index만큼 뒤에 삽입
    slide12_idx = 0
    for idx, sld in enumerate(sld_id_lst.findall(f"{{{P}}}sldId")):
        if sld.get(f"{{{R}}}id") == slide12_rid:
            slide12_idx = idx
            break

    new_sld_id = etree.Element(f"{{{P}}}sldId")
    new_sld_id.set("id", str(new_id))
    new_sld_id.set(f"{{{R}}}id", new_rid)
    sld_id_lst.insert(slide12_idx + page_index, new_sld_id)

    pres_tree.write(
        str(pres_path), xml_declaration=True, encoding="UTF-8", standalone=True
    )

    return str(new_slide_path)


def remove_overflow_slides(work_dir: Path):
    """이전 실행에서 생성된 overflow 슬라이드(slide29 이상)를 정리."""
    slides_dir = work_dir / "ppt" / "slides"
    rels_dir = slides_dir / "_rels"
    pres_rels_path = work_dir / "ppt" / "_rels" / "presentation.xml.rels"
    pres_path = work_dir / "ppt" / "presentation.xml"
    ct_path = work_dir / "[Content_Types].xml"

    overflow_slides = sorted(
        f
        for f in slides_dir.glob("slide*.xml")
        if f.stem.replace("slide", "").isdigit()
        and int(f.stem.replace("slide", "")) > 28
    )

    if not overflow_slides:
        return

    overflow_nums = [int(f.stem.replace("slide", "")) for f in overflow_slides]

    # presentation.xml.rels에서 제거
    pres_rels_tree = etree.parse(str(pres_rels_path))
    pres_rels_root = pres_rels_tree.getroot()
    rids_to_remove = set()
    for rel in pres_rels_root.findall(f"{{{REL_NS}}}Relationship"):
        target = rel.get("Target", "")
        for num in overflow_nums:
            if target == f"slides/slide{num}.xml":
                rids_to_remove.add(rel.get("Id"))
                pres_rels_root.remove(rel)
                break
    pres_rels_tree.write(
        str(pres_rels_path), xml_declaration=True, encoding="UTF-8", standalone=True
    )

    # presentation.xml의 sldIdLst에서 제거
    pres_tree = etree.parse(str(pres_path))
    pres_root = pres_tree.getroot()
    sld_id_lst = pres_root.find(f"{{{P}}}sldIdLst")
    for sld in list(sld_id_lst.findall(f"{{{P}}}sldId")):
        if sld.get(f"{{{R}}}id") in rids_to_remove:
            sld_id_lst.remove(sld)
    pres_tree.write(
        str(pres_path), xml_declaration=True, encoding="UTF-8", standalone=True
    )

    # [Content_Types].xml에서 제거
    ct_tree = etree.parse(str(ct_path))
    ct_root = ct_tree.getroot()
    for ov in list(ct_root.findall(f"{{{CT_NS}}}Override")):
        pn = ov.get("PartName", "")
        for num in overflow_nums:
            if pn == f"/ppt/slides/slide{num}.xml":
                ct_root.remove(ov)
                break
    ct_tree.write(str(ct_path), xml_declaration=True, encoding="UTF-8", standalone=True)

    # 파일 삭제
    for f in overflow_slides:
        f.unlink(missing_ok=True)
        rels_f = rels_dir / f"{f.name}.rels"
        rels_f.unlink(missing_ok=True)


# --- build-slide12 메인 -------------------------------------------------------


def build_slide12(work_dir: Path, input_path: Path):
    """input 파일에서 성경 본문을 파싱하여 slide 12를 생성.
    본문이 한 페이지를 초과하면 추가 슬라이드를 자동 생성.
    """
    blocks = parse_scripture_blocks(input_path)
    if not blocks:
        sys.exit("성경 본문 블록을 찾을 수 없습니다.")

    # 이전 overflow 슬라이드 정리
    remove_overflow_slides(work_dir)

    # 블록을 페이지별로 분배
    pages = split_blocks_into_pages(blocks)

    print(f"성경 본문 {len(blocks)}개 → {len(pages)}페이지로 분배")
    for i, page in enumerate(pages):
        refs = [ref for ref, _ in page]
        print(f"  페이지 {i + 1}: {', '.join(refs)}")

    # 첫 페이지 → slide 12에 직접 적용
    slide12_path = work_dir / "ppt" / "slides" / "slide12.xml"
    tree = etree.parse(str(slide12_path))
    root = tree.getroot()
    txBody = root.find(f".//{{{P}}}txBody")

    for p in txBody.findall(f"{{{A}}}p"):
        txBody.remove(p)

    for para in _build_txbody_paragraphs(pages[0]):
        txBody.append(para)

    xml_bytes = etree.tostring(
        tree, xml_declaration=True, encoding="UTF-8", standalone="yes"
    )
    slide12_path.write_bytes(xml_bytes)
    print(f"  slide12.xml 업데이트 완료")

    # 2페이지 이상이면 overflow 슬라이드 생성
    for page_idx in range(1, len(pages)):
        new_path = add_overflow_slide(work_dir, pages[page_idx], page_idx)
        print(f"  {Path(new_path).name} 생성 완료 (overflow 페이지 {page_idx + 1})")

    # 검증
    _verify_slide12_encoding(work_dir, pages)


def _verify_slide12_encoding(work_dir: Path, pages):
    """생성된 슬라이드들의 한글 인코딩 검증."""
    slides_dir = work_dir / "ppt" / "slides"

    all_ok = True
    files_to_check = ["slide12.xml"]
    for i in range(1, len(pages)):
        overflow = sorted(
            f.name
            for f in slides_dir.glob("slide*.xml")
            if f.stem.replace("slide", "").isdigit()
            and int(f.stem.replace("slide", "")) > 28
        )
        files_to_check.extend(overflow)
        break

    for fname in files_to_check:
        fpath = slides_dir / fname
        if not fpath.exists():
            continue
        tree = etree.parse(str(fpath))
        texts = []
        for t_elem in tree.iter(f"{{{A}}}t"):
            if t_elem.text:
                texts.append(t_elem.text)
        full = "".join(texts)
        if "�" in full:
            print(f"  WARNING: {fname}에서 인코딩 깨짐 감지!")
            all_ok = False

    if all_ok:
        print("인코딩 검증 통과")


# --- 설교 슬라이드 삽입 (이철준 원로목사 등) ------------------------------------

LAYOUT_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"

# 설교 슬라이드 디자인 상수
SERMON_BG_COLOR = "FFF8F0"
SERMON_ACCENT_COLOR = "C8956C"
SERMON_TITLE_COLOR = "3D2B1F"
SERMON_BODY_COLOR = "333333"
SERMON_SLIDE_W = 9144000
SERMON_SLIDE_H = 5143500


def extract_sermon_text(sermon_pptx_path: Path):
    """설교 PPTX에서 각 슬라이드의 제목과 본문 텍스트를 추출."""
    import tempfile as _tf

    slides = []
    with _tf.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(sermon_pptx_path, "r") as z:
            z.extractall(tmp)

        slides_dir = Path(tmp) / "ppt" / "slides"
        i = 1
        while True:
            spath = slides_dir / f"slide{i}.xml"
            if not spath.exists():
                break
            tree = etree.parse(str(spath))
            root = tree.getroot()
            title = ""
            body_paragraphs = []

            for sp in root.iter(f"{{{P}}}sp"):
                nvSpPr = sp.find(f"{{{P}}}nvSpPr")
                if nvSpPr is None:
                    continue
                nvPr = nvSpPr.find(f"{{{P}}}nvPr")
                if nvPr is None:
                    continue
                ph = nvPr.find(f"{{{P}}}ph")
                if ph is None:
                    continue

                ph_type = ph.get("type", "")
                ph_idx = ph.get("idx", "")
                txBody = sp.find(f"{{{P}}}txBody")
                if txBody is None:
                    continue

                if ph_type == "title":
                    texts = []
                    for p in txBody.findall(f"{{{A}}}p"):
                        for r in p.findall(f"{{{A}}}r"):
                            t = r.find(f"{{{A}}}t")
                            if t is not None and t.text:
                                texts.append(t.text)
                    title = "".join(texts).strip()
                elif ph_idx == "1" or ph_type == "body":
                    for p in txBody.findall(f"{{{A}}}p"):
                        ptexts = []
                        for r in p.findall(f"{{{A}}}r"):
                            t = r.find(f"{{{A}}}t")
                            if t is not None and t.text:
                                ptexts.append(t.text)
                        body_paragraphs.append("".join(ptexts))

            slides.append({"title": title, "body": body_paragraphs})
            i += 1

    return slides


def _sermon_make_run(text: str, is_ko: bool, sz: str, color: str, bold: bool = False):
    """설교 슬라이드용 텍스트 run 생성."""
    r = etree.Element(f"{{{A}}}r")
    rpr = etree.SubElement(r, f"{{{A}}}rPr")
    rpr.set("lang", "ko-KR" if is_ko else "en-US")
    rpr.set("altLang", "en-US" if is_ko else "ko-KR")
    rpr.set("sz", sz)
    rpr.set("dirty", "0")
    if bold:
        rpr.set("b", "1")
    fill = etree.SubElement(rpr, f"{{{A}}}solidFill")
    etree.SubElement(fill, f"{{{A}}}srgbClr").set("val", color)
    latin = etree.SubElement(rpr, f"{{{A}}}latin")
    latin.set("typeface", "맑은 고딕")
    ea = etree.SubElement(rpr, f"{{{A}}}ea")
    ea.set("typeface", "맑은 고딕")
    t = etree.SubElement(r, f"{{{A}}}t")
    if " " in text:
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    return r


def _create_sermon_slide_xml(title: str, body_paragraphs: list):
    """환한 배경의 설교 슬라이드 XML 생성."""
    NSMAP = {
        "a": A,
        "r": R,
        "p": P,
    }

    sld = etree.Element(f"{{{P}}}sld", nsmap=NSMAP)
    cSld = etree.SubElement(sld, f"{{{P}}}cSld")

    # 배경: 따뜻한 아이보리
    bg = etree.SubElement(cSld, f"{{{P}}}bg")
    bgPr = etree.SubElement(bg, f"{{{P}}}bgPr")
    grad = etree.SubElement(bgPr, f"{{{A}}}gradFill")
    gsLst = etree.SubElement(grad, f"{{{A}}}gsLst")
    gs1 = etree.SubElement(gsLst, f"{{{A}}}gs")
    gs1.set("pos", "0")
    etree.SubElement(gs1, f"{{{A}}}srgbClr").set("val", "FFFCF7")
    gs2 = etree.SubElement(gsLst, f"{{{A}}}gs")
    gs2.set("pos", "100000")
    etree.SubElement(gs2, f"{{{A}}}srgbClr").set("val", "F5EDE0")
    lin = etree.SubElement(grad, f"{{{A}}}lin")
    lin.set("ang", "5400000")
    lin.set("scaled", "1")
    etree.SubElement(bgPr, f"{{{A}}}effectLst")

    # Shape tree
    spTree = etree.SubElement(cSld, f"{{{P}}}spTree")
    nvGrpSpPr = etree.SubElement(spTree, f"{{{P}}}nvGrpSpPr")
    etree.SubElement(nvGrpSpPr, f"{{{P}}}cNvPr").set("id", "1")
    nvGrpSpPr[0].set("name", "")
    etree.SubElement(nvGrpSpPr, f"{{{P}}}cNvGrpSpPr")
    etree.SubElement(nvGrpSpPr, f"{{{P}}}nvPr")
    grpSpPr = etree.SubElement(spTree, f"{{{P}}}grpSpPr")

    # 상단 장식 바
    _add_rect(spTree, shape_id=2, name="AccentBar",
              x=0, y=0, w=SERMON_SLIDE_W, h=57150,
              fill_color=SERMON_ACCENT_COLOR)

    # 하단 장식 라인
    _add_rect(spTree, shape_id=3, name="BottomLine",
              x=0, y=SERMON_SLIDE_H - 38100, w=SERMON_SLIDE_W, h=38100,
              fill_color=SERMON_ACCENT_COLOR)

    # 제목 영역 (콤팩트)
    title_y = 114300
    title_h = 533400
    _add_text_box(spTree, shape_id=4, name="Title",
                  x=457200, y=title_y, w=8229600, h=title_h,
                  text=title, font_size="2400", color=SERMON_TITLE_COLOR,
                  bold=True, anchor="b")

    # 구분선
    divider_y = title_y + title_h + 57150
    _add_rect(spTree, shape_id=5, name="Divider",
              x=457200, y=divider_y, w=1828800, h=25400,
              fill_color=SERMON_ACCENT_COLOR)

    # 본문 영역 (최대한 넓게)
    body_y = divider_y + 76200
    body_h = SERMON_SLIDE_H - body_y - 114300
    _add_body_text_box(spTree, shape_id=6, name="Body",
                       x=457200, y=body_y, w=8229600, h=body_h,
                       paragraphs=body_paragraphs,
                       font_size="1600", color=SERMON_BODY_COLOR)

    return sld


def _add_rect(spTree, shape_id: int, name: str,
              x: int, y: int, w: int, h: int, fill_color: str):
    """단색 사각형 도형 추가."""
    sp = etree.SubElement(spTree, f"{{{P}}}sp")
    nvSpPr = etree.SubElement(sp, f"{{{P}}}nvSpPr")
    cNvPr = etree.SubElement(nvSpPr, f"{{{P}}}cNvPr")
    cNvPr.set("id", str(shape_id))
    cNvPr.set("name", name)
    etree.SubElement(nvSpPr, f"{{{P}}}cNvSpPr")
    etree.SubElement(nvSpPr, f"{{{P}}}nvPr")
    spPr = etree.SubElement(sp, f"{{{P}}}spPr")
    xfrm = etree.SubElement(spPr, f"{{{A}}}xfrm")
    off = etree.SubElement(xfrm, f"{{{A}}}off")
    off.set("x", str(x))
    off.set("y", str(y))
    ext = etree.SubElement(xfrm, f"{{{A}}}ext")
    ext.set("cx", str(w))
    ext.set("cy", str(h))
    prstGeom = etree.SubElement(spPr, f"{{{A}}}prstGeom")
    prstGeom.set("prst", "rect")
    etree.SubElement(prstGeom, f"{{{A}}}avLst")
    solidFill = etree.SubElement(spPr, f"{{{A}}}solidFill")
    etree.SubElement(solidFill, f"{{{A}}}srgbClr").set("val", fill_color)
    ln = etree.SubElement(spPr, f"{{{A}}}ln")
    etree.SubElement(ln, f"{{{A}}}noFill")


def _add_text_box(spTree, shape_id: int, name: str,
                  x: int, y: int, w: int, h: int,
                  text: str, font_size: str, color: str,
                  bold: bool = False, anchor: str = "t"):
    """단일 텍스트 박스 도형 추가."""
    sp = etree.SubElement(spTree, f"{{{P}}}sp")
    nvSpPr = etree.SubElement(sp, f"{{{P}}}nvSpPr")
    cNvPr = etree.SubElement(nvSpPr, f"{{{P}}}cNvPr")
    cNvPr.set("id", str(shape_id))
    cNvPr.set("name", name)
    cNvSpPr = etree.SubElement(nvSpPr, f"{{{P}}}cNvSpPr")
    cNvSpPr.set("txBox", "1")
    etree.SubElement(nvSpPr, f"{{{P}}}nvPr")
    spPr = etree.SubElement(sp, f"{{{P}}}spPr")
    xfrm = etree.SubElement(spPr, f"{{{A}}}xfrm")
    off = etree.SubElement(xfrm, f"{{{A}}}off")
    off.set("x", str(x))
    off.set("y", str(y))
    ext = etree.SubElement(xfrm, f"{{{A}}}ext")
    ext.set("cx", str(w))
    ext.set("cy", str(h))
    prstGeom = etree.SubElement(spPr, f"{{{A}}}prstGeom")
    prstGeom.set("prst", "rect")
    etree.SubElement(prstGeom, f"{{{A}}}avLst")
    etree.SubElement(spPr, f"{{{A}}}noFill")

    txBody = etree.SubElement(sp, f"{{{P}}}txBody")
    bodyPr = etree.SubElement(txBody, f"{{{A}}}bodyPr")
    bodyPr.set("wrap", "square")
    bodyPr.set("anchor", anchor)
    etree.SubElement(bodyPr, f"{{{A}}}normAutofit")
    etree.SubElement(txBody, f"{{{A}}}lstStyle")

    ap = etree.SubElement(txBody, f"{{{A}}}p")
    for seg_text, is_ko in _split_lang(text):
        ap.append(_sermon_make_run(seg_text, is_ko, font_size, color, bold))


def _add_body_text_box(spTree, shape_id: int, name: str,
                       x: int, y: int, w: int, h: int,
                       paragraphs: list, font_size: str, color: str):
    """여러 단락의 본문 텍스트 박스 추가."""
    sp = etree.SubElement(spTree, f"{{{P}}}sp")
    nvSpPr = etree.SubElement(sp, f"{{{P}}}nvSpPr")
    cNvPr = etree.SubElement(nvSpPr, f"{{{P}}}cNvPr")
    cNvPr.set("id", str(shape_id))
    cNvPr.set("name", name)
    cNvSpPr = etree.SubElement(nvSpPr, f"{{{P}}}cNvSpPr")
    cNvSpPr.set("txBox", "1")
    etree.SubElement(nvSpPr, f"{{{P}}}nvPr")
    spPr = etree.SubElement(sp, f"{{{P}}}spPr")
    xfrm = etree.SubElement(spPr, f"{{{A}}}xfrm")
    off = etree.SubElement(xfrm, f"{{{A}}}off")
    off.set("x", str(x))
    off.set("y", str(y))
    ext = etree.SubElement(xfrm, f"{{{A}}}ext")
    ext.set("cx", str(w))
    ext.set("cy", str(h))
    prstGeom = etree.SubElement(spPr, f"{{{A}}}prstGeom")
    prstGeom.set("prst", "rect")
    etree.SubElement(prstGeom, f"{{{A}}}avLst")
    etree.SubElement(spPr, f"{{{A}}}noFill")

    txBody = etree.SubElement(sp, f"{{{P}}}txBody")
    bodyPr = etree.SubElement(txBody, f"{{{A}}}bodyPr")
    bodyPr.set("wrap", "square")
    bodyPr.set("anchor", "t")
    etree.SubElement(bodyPr, f"{{{A}}}normAutofit")
    etree.SubElement(txBody, f"{{{A}}}lstStyle")

    for para_text in paragraphs:
        ap = etree.SubElement(txBody, f"{{{A}}}p")
        ppr = etree.SubElement(ap, f"{{{A}}}pPr")
        lnSpc = etree.SubElement(ppr, f"{{{A}}}lnSpc")
        etree.SubElement(lnSpc, f"{{{A}}}spcPct").set("val", "100000")
        spcAft = etree.SubElement(ppr, f"{{{A}}}spcAft")
        etree.SubElement(spcAft, f"{{{A}}}spcPts").set("val", "200")

        if not para_text.strip():
            endRpr = etree.SubElement(ap, f"{{{A}}}endParaRPr")
            endRpr.set("lang", "ko-KR")
            endRpr.set("sz", font_size)
            continue

        for seg_text, is_ko in _split_lang(para_text):
            ap.append(_sermon_make_run(seg_text, is_ko, font_size, color))


def insert_sermon_slides(work_dir: Path, sermon_pptx_path: Path):
    """설교 PPTX에서 텍스트를 추출하여 환한 디자인 슬라이드로 삽입.
    성경본문 슬라이드(slide12 + overflow) 바로 뒤에 삽입됨.
    """
    slides_data = extract_sermon_text(sermon_pptx_path)
    if not slides_data:
        print("설교 PPT에서 슬라이드를 찾을 수 없습니다.")
        return

    print(f"설교 슬라이드 {len(slides_data)}장 추출")

    slides_dir = work_dir / "ppt" / "slides"
    rels_dir = slides_dir / "_rels"

    # slide12의 layout rels 참조 가져오기 (동일한 layout 사용)
    slide12_rels_path = rels_dir / "slide12.xml.rels"

    # 성경 본문 관련 슬라이드들의 위치 파악 (slide12 + overflow)
    pres_path = work_dir / "ppt" / "presentation.xml"
    pres_rels_path = work_dir / "ppt" / "_rels" / "presentation.xml.rels"

    # slide12의 rId 찾기
    slide12_rid = _find_slide12_rId(work_dir)

    pres_tree = etree.parse(str(pres_path))
    pres_root = pres_tree.getroot()
    sld_id_lst = pres_root.find(f"{{{P}}}sldIdLst")
    sld_ids = list(sld_id_lst.findall(f"{{{P}}}sldId"))

    # slide12 위치 찾기
    slide12_pos = 0
    for idx, sld in enumerate(sld_ids):
        if sld.get(f"{{{R}}}id") == slide12_rid:
            slide12_pos = idx
            break

    # overflow 슬라이드(29+)가 slide12 뒤에 몇 개 있는지 확인
    pres_rels_tree = etree.parse(str(pres_rels_path))
    pres_rels_root = pres_rels_tree.getroot()

    rid_to_target = {}
    for rel in pres_rels_root.findall(f"{{{REL_NS}}}Relationship"):
        rid_to_target[rel.get("Id")] = rel.get("Target", "")

    overflow_count = 0
    for i in range(slide12_pos + 1, len(sld_ids)):
        rid = sld_ids[i].get(f"{{{R}}}id")
        target = rid_to_target.get(rid, "")
        # overflow slides are slide29+
        m = re.search(r"slide(\d+)\.xml", target)
        if m and int(m.group(1)) > 28:
            overflow_count += 1
        else:
            break

    insert_after_pos = slide12_pos + overflow_count  # 삽입 위치 (0-indexed)

    for i, sdata in enumerate(slides_data):
        slide_num = _next_slide_number(work_dir)

        # 1. 슬라이드 XML 생성
        sld_xml = _create_sermon_slide_xml(sdata["title"], sdata["body"])
        xml_bytes = etree.tostring(
            sld_xml, xml_declaration=True, encoding="UTF-8", standalone="yes"
        )
        new_slide_path = slides_dir / f"slide{slide_num}.xml"
        new_slide_path.write_bytes(xml_bytes)

        # 2. rels 파일 생성 (slide12와 동일한 layout 참조)
        new_rels_path = rels_dir / f"slide{slide_num}.xml.rels"
        shutil.copy2(slide12_rels_path, new_rels_path)

        # 3. [Content_Types].xml 업데이트
        ct_path = work_dir / "[Content_Types].xml"
        ct_tree = etree.parse(str(ct_path))
        ct_root = ct_tree.getroot()
        override = etree.SubElement(ct_root, f"{{{CT_NS}}}Override")
        override.set("PartName", f"/ppt/slides/slide{slide_num}.xml")
        override.set(
            "ContentType",
            "application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
        )
        ct_tree.write(str(ct_path), xml_declaration=True, encoding="UTF-8", standalone=True)

        # 4. presentation.xml.rels에 relationship 추가
        pres_rels_tree = etree.parse(str(pres_rels_path))
        pres_rels_root = pres_rels_tree.getroot()
        existing_rids = [
            int(r.get("Id").replace("rId", ""))
            for r in pres_rels_root.findall(f"{{{REL_NS}}}Relationship")
            if r.get("Id", "").startswith("rId")
        ]
        new_rid = f"rId{max(existing_rids) + 1}"
        new_rel = etree.SubElement(pres_rels_root, f"{{{REL_NS}}}Relationship")
        new_rel.set("Id", new_rid)
        new_rel.set("Type", SLIDE_TYPE)
        new_rel.set("Target", f"slides/slide{slide_num}.xml")
        pres_rels_tree.write(
            str(pres_rels_path), xml_declaration=True, encoding="UTF-8", standalone=True
        )

        # 5. presentation.xml의 sldIdLst에 삽입
        pres_tree = etree.parse(str(pres_path))
        pres_root = pres_tree.getroot()
        sld_id_lst = pres_root.find(f"{{{P}}}sldIdLst")
        existing_ids = [int(s.get("id")) for s in sld_id_lst.findall(f"{{{P}}}sldId")]
        new_id = max(existing_ids) + 1

        new_sld_id = etree.Element(f"{{{P}}}sldId")
        new_sld_id.set("id", str(new_id))
        new_sld_id.set(f"{{{R}}}id", new_rid)
        sld_id_lst.insert(insert_after_pos + 1 + i, new_sld_id)
        pres_tree.write(
            str(pres_path), xml_declaration=True, encoding="UTF-8", standalone=True
        )

        print(f"  slide{slide_num}.xml → {sdata['title'][:30]}...")

    print(f"설교 슬라이드 {len(slides_data)}장 삽입 완료 (성경본문 뒤)")


# --- 설교 PPTX verbatim 삽입 (원본 형식 그대로 보존) ------------------------

SLIDEMASTER_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster"
)

_VERBATIM_FOLDER_PREFIX = {
    "ppt/slides": "slide",
    "ppt/slideLayouts": "slideLayout",
    "ppt/slideMasters": "slideMaster",
    "ppt/theme": "theme",
    "ppt/media": "image",
    "ppt/embeddings": "oleObject",
}


def _ct_localname(el) -> str:
    return etree.QName(el).localname


def _scripture_block_end_pos(work_dir: Path) -> int:
    """sldIdLst에서 slide12 + 성경본문 overflow(slide29+) 블록의 마지막 위치(0-indexed)."""
    pres_path = work_dir / "ppt" / "presentation.xml"
    pres_rels_path = work_dir / "ppt" / "_rels" / "presentation.xml.rels"
    slide12_rid = _find_slide12_rId(work_dir)

    proot = etree.parse(str(pres_path)).getroot()
    sld_ids = proot.find(f"{{{P}}}sldIdLst").findall(f"{{{P}}}sldId")
    rid_to_target = {
        r.get("Id"): r.get("Target", "")
        for r in etree.parse(str(pres_rels_path))
        .getroot()
        .findall(f"{{{REL_NS}}}Relationship")
    }

    pos12 = 0
    for idx, s in enumerate(sld_ids):
        if s.get(f"{{{R}}}id") == slide12_rid:
            pos12 = idx
            break

    overflow = 0
    for i in range(pos12 + 1, len(sld_ids)):
        tgt = rid_to_target.get(sld_ids[i].get(f"{{{R}}}id"), "")
        m = re.search(r"slide(\d+)\.xml", tgt)
        if m and int(m.group(1)) > 28:
            overflow += 1
        else:
            break
    return pos12 + overflow


def insert_pptx_verbatim(work_dir: Path, src_pptx_path: Path) -> int:
    """설교 PPTX의 모든 슬라이드를 *원본 형식 그대로* 패키지에 병합하여
    성경 본문 슬라이드(slide12 + overflow) 바로 뒤에 삽입한다.

    OOXML 파트는 관계 ID(r:id)로만 서로를 참조하므로, 각 파트 XML은
    바이트 그대로 복사하고 .rels의 Target 경로만 새 파트명으로 다시 쓴다.
    이렇게 하면 폰트/색/이미지/레이아웃이 100% 보존된다.
    """
    import posixpath

    with zipfile.ZipFile(src_pptx_path, "r") as z:
        src = {name: z.read(name) for name in z.namelist()}

    if "ppt/presentation.xml" not in src:
        print("설교 PPT가 올바른 PPTX가 아닙니다.")
        return 0

    def norm(base_part, target):
        return posixpath.normpath(
            posixpath.join(posixpath.dirname(base_part), target)
        )

    def rels_for(part):
        return f"{posixpath.dirname(part)}/_rels/{posixpath.basename(part)}.rels"

    def rel_target(from_part, to_part):
        return posixpath.relpath(to_part, posixpath.dirname(from_part))

    # 1. 원본 슬라이드 순서 파악
    pres = etree.fromstring(src["ppt/presentation.xml"])
    pres_rels = etree.fromstring(src["ppt/_rels/presentation.xml.rels"])
    rid_to_target = {
        r.get("Id"): r.get("Target")
        for r in pres_rels.findall(f"{{{REL_NS}}}Relationship")
    }
    slide_order = []
    sld_lst = pres.find(f"{{{P}}}sldIdLst")
    if sld_lst is not None:
        for sld in sld_lst.findall(f"{{{P}}}sldId"):
            tgt = rid_to_target.get(sld.get(f"{{{R}}}id"))
            if tgt:
                slide_order.append(norm("ppt/presentation.xml", tgt))
    if not slide_order:
        print("설교 PPT에서 슬라이드를 찾을 수 없습니다.")
        return 0

    # 2. 슬라이드에서 도달 가능한 모든 파트 수집 (노트 슬라이드는 제외)
    collected = set()

    def visit(part):
        if part in collected or part not in src:
            return
        collected.add(part)
        rp = rels_for(part)
        if rp in src:
            for rel in etree.fromstring(src[rp]).findall(
                f"{{{REL_NS}}}Relationship"
            ):
                if rel.get("TargetMode") == "External":
                    continue
                if (rel.get("Type") or "").endswith("notesSlide"):
                    continue
                visit(norm(part, rel.get("Target")))

    for sp in slide_order:
        visit(sp)

    # 3. 대상 파트명 할당 (기존 번호와 충돌 회피)
    counters = {}

    def alloc(folder, prefix, ext):
        key = (folder, prefix, ext)
        if key not in counters:
            mx = 0
            d = work_dir / folder
            if d.exists():
                pat = re.compile(rf"{re.escape(prefix)}(\d+){re.escape(ext)}$")
                for f in d.iterdir():
                    m = pat.match(f.name)
                    if m:
                        mx = max(mx, int(m.group(1)))
            counters[key] = mx
        counters[key] += 1
        return f"{folder}/{prefix}{counters[key]}{ext}"

    mapping = {}
    for part in sorted(collected):
        folder = posixpath.dirname(part)
        ext = posixpath.splitext(part)[1]
        prefix = _VERBATIM_FOLDER_PREFIX.get(folder)
        if prefix is None:
            stem = posixpath.splitext(posixpath.basename(part))[0]
            prefix = re.sub(r"\d+$", "", stem) or "part"
        mapping[part] = alloc(folder, prefix, ext)

    # 4. 파트 바이트 복사 + .rels Target 재작성
    for src_part, dest_part in mapping.items():
        out = work_dir / dest_part
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(src[src_part])

        rp = rels_for(src_part)
        if rp not in src:
            continue
        rels = etree.fromstring(src[rp])
        for rel in list(rels.findall(f"{{{REL_NS}}}Relationship")):
            if (rel.get("Type") or "").endswith("notesSlide"):
                rels.remove(rel)
                continue
            if rel.get("TargetMode") == "External":
                continue
            child = norm(src_part, rel.get("Target"))
            if child in mapping:
                rel.set("Target", rel_target(dest_part, mapping[child]))
        dest_rels = work_dir / rels_for(dest_part)
        dest_rels.parent.mkdir(parents=True, exist_ok=True)
        dest_rels.write_bytes(
            etree.tostring(
                rels, xml_declaration=True, encoding="UTF-8", standalone=True
            )
        )

    # 5. [Content_Types].xml 갱신
    src_ct = etree.fromstring(src["[Content_Types].xml"])
    src_overrides, src_defaults = {}, {}
    for el in src_ct:
        ln = _ct_localname(el)
        if ln == "Override":
            src_overrides[el.get("PartName")] = el.get("ContentType")
        elif ln == "Default":
            src_defaults[el.get("Extension", "").lower()] = el.get("ContentType")

    ct_path = work_dir / "[Content_Types].xml"
    ct_tree = etree.parse(str(ct_path))
    ct_root = ct_tree.getroot()
    have_over = {
        e.get("PartName") for e in ct_root if _ct_localname(e) == "Override"
    }
    have_def = {
        e.get("Extension", "").lower()
        for e in ct_root
        if _ct_localname(e) == "Default"
    }
    for src_part, dest_part in mapping.items():
        src_pn = "/" + src_part
        dest_pn = "/" + dest_part
        if src_pn in src_overrides:
            if dest_pn not in have_over:
                o = etree.SubElement(ct_root, f"{{{CT_NS}}}Override")
                o.set("PartName", dest_pn)
                o.set("ContentType", src_overrides[src_pn])
                have_over.add(dest_pn)
        else:
            ext = posixpath.splitext(dest_part)[1].lstrip(".").lower()
            if ext and ext not in have_def and ext in src_defaults:
                d = etree.SubElement(ct_root, f"{{{CT_NS}}}Default")
                d.set("Extension", ext)
                d.set("ContentType", src_defaults[ext])
                have_def.add(ext)
    ct_tree.write(
        str(ct_path), xml_declaration=True, encoding="UTF-8", standalone=True
    )

    # 6. 삽입 위치: slide12 + 성경본문 overflow 블록 뒤
    insert_after_pos = _scripture_block_end_pos(work_dir)

    # 7. presentation.xml.rels + presentation.xml 갱신
    pres_path = work_dir / "ppt" / "presentation.xml"
    pres_rels_path = work_dir / "ppt" / "_rels" / "presentation.xml.rels"
    prt = etree.parse(str(pres_rels_path))
    prr = prt.getroot()
    rid_nums = [
        int(r.get("Id")[3:])
        for r in prr.findall(f"{{{REL_NS}}}Relationship")
        if r.get("Id", "").startswith("rId")
    ]
    next_rid_n = (max(rid_nums) + 1) if rid_nums else 1

    pt = etree.parse(str(pres_path))
    proot = pt.getroot()
    sld_id_lst = proot.find(f"{{{P}}}sldIdLst")
    sld_master_lst = proot.find(f"{{{P}}}sldMasterIdLst")

    def add_rel(rtype, target):
        nonlocal next_rid_n
        rid = f"rId{next_rid_n}"
        next_rid_n += 1
        rel = etree.SubElement(prr, f"{{{REL_NS}}}Relationship")
        rel.set("Id", rid)
        rel.set("Type", rtype)
        rel.set("Target", target)
        return rid

    # 7a. 가져온 슬라이드 마스터를 presentation에 등록
    if sld_master_lst is not None:
        mids = [
            int(m.get("id"))
            for m in sld_master_lst.findall(f"{{{P}}}sldMasterId")
        ]
        next_mid = (max(mids) + 1) if mids else 2147483648
        for src_part, dest_part in mapping.items():
            if (
                posixpath.dirname(src_part) == "ppt/slideMasters"
                and dest_part.endswith(".xml")
            ):
                rid = add_rel(SLIDEMASTER_TYPE, dest_part[len("ppt/"):])
                e = etree.SubElement(sld_master_lst, f"{{{P}}}sldMasterId")
                e.set("id", str(next_mid))
                e.set(f"{{{R}}}id", rid)
                next_mid += 1

    # 7b. 슬라이드를 원본 순서대로 삽입
    all_ids = [int(s.get("id")) for s in sld_id_lst.findall(f"{{{P}}}sldId")]
    next_sid = (max(all_ids) + 1) if all_ids else 256
    for i, src_slide in enumerate(slide_order):
        dest_slide = mapping[src_slide]
        rid = add_rel(SLIDE_TYPE, dest_slide[len("ppt/"):])
        e = etree.Element(f"{{{P}}}sldId")
        e.set("id", str(next_sid))
        next_sid += 1
        e.set(f"{{{R}}}id", rid)
        sld_id_lst.insert(insert_after_pos + 1 + i, e)

    prt.write(
        str(pres_rels_path), xml_declaration=True, encoding="UTF-8", standalone=True
    )
    pt.write(
        str(pres_path), xml_declaration=True, encoding="UTF-8", standalone=True
    )

    print(
        f"설교 PPT {len(slide_order)}장을 원본 형식 그대로 삽입 완료 (성경본문 뒤)"
    )
    return len(slide_order)


# --- PPTX 패킹/언패킹 -------------------------------------------------------

def unpack(pptx_path: Path, work_dir: Path):
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    with zipfile.ZipFile(pptx_path, "r") as z:
        z.extractall(work_dir)
    print(f"Unpacked {pptx_path} → {work_dir}")


def pack(work_dir: Path, output_pptx: Path):
    output_pptx.parent.mkdir(parents=True, exist_ok=True)
    if output_pptx.exists():
        output_pptx.unlink()

    content_types = work_dir / "[Content_Types].xml"
    if not content_types.exists():
        raise FileNotFoundError(f"{content_types} not found")

    with zipfile.ZipFile(output_pptx, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(content_types, "[Content_Types].xml")
        for path in sorted(work_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(work_dir).as_posix()
            if rel == "[Content_Types].xml":
                continue
            zf.write(path, rel)

    print(f"Packed {work_dir} → {output_pptx}")


# --- 검증 -------------------------------------------------------------------

def verify(pptx_path: Path):
    with zipfile.ZipFile(pptx_path, "r") as z:
        slide_nums = [10, 11, 12]
        # overflow 슬라이드도 검증
        for name in z.namelist():
            if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                num_str = name.replace("ppt/slides/slide", "").replace(".xml", "")
                if num_str.isdigit() and int(num_str) > 28:
                    slide_nums.append(int(num_str))

        for slide_num in sorted(slide_nums):
            slide_path = f"ppt/slides/slide{slide_num}.xml"
            print(f"\n=== Slide {slide_num} ===")
            try:
                xml = z.read(slide_path)
            except KeyError:
                print(f"  (없음)")
                continue
            tree = etree.fromstring(xml)
            for t in tree.iter("{%s}t" % A):
                if t.text:
                    print(t.text)


# --- 엔트리 포인트 ----------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "unpack":
        if len(sys.argv) != 4:
            sys.exit("usage: unpack <pptx> <work_dir>")
        unpack(Path(sys.argv[2]), Path(sys.argv[3]))

    elif cmd == "pack":
        if len(sys.argv) != 4:
            sys.exit("usage: pack <work_dir> <output.pptx>")
        pack(Path(sys.argv[2]), Path(sys.argv[3]))

    elif cmd == "verify":
        if len(sys.argv) != 3:
            sys.exit("usage: verify <pptx>")
        verify(Path(sys.argv[2]))

    elif cmd == "split-title":
        if len(sys.argv) != 3:
            sys.exit("usage: split-title <설교제목>")
        segments = split_by_language(sys.argv[2])
        for lang, seg in segments:
            marker = "ko-KR" if lang == "ko" else "en-US"
            print(f"  [{marker}] {seg!r}")

    elif cmd == "build-slide12":
        if len(sys.argv) != 4:
            sys.exit("usage: build-slide12 <work_dir> <input_file>")
        build_slide12(Path(sys.argv[2]), Path(sys.argv[3]))

    else:
        sys.exit(f"Unknown command: {cmd}")


# lxml lazy import
try:
    from lxml import etree
except ImportError:
    pass


if __name__ == "__main__":
    try:
        from lxml import etree
    except ImportError:
        sys.exit("lxml이 필요합니다: pip3 install lxml")
    main()

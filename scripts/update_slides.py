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

이 스크립트는 stdlib(zipfile, re)와 lxml만 사용합니다.
lxml이 없으면 'pip3 install lxml'.
"""

import re
import sys
import shutil
import zipfile
from pathlib import Path

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

# --- 한글/영문 경계 분할 -----------------------------------------------------

# 한글 음절(가-힣), 자음(ㄱ-ㅎ), 모음(ㅏ-ㅣ)
KOREAN_RE = re.compile(r"[\uac00-\ud7a3\u3131-\u318e]")


def is_korean_char(ch: str) -> bool:
    return bool(KOREAN_RE.match(ch))


def split_by_language(text: str):
    """
    텍스트를 한글/비한글 연속 구간으로 분할.
    반환: [(lang, segment), ...]  lang은 'ko' 또는 'en'.
    공백은 직전 구간에 포함됨 (직전 구간이 없으면 다음 구간에 포함).
    """
    if not text:
        return []

    segments = []
    current_lang = None
    current_buf = []

    for ch in text:
        if ch.isspace():
            # 공백은 직전 언어를 유지
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
        # current_lang이 None이면 (전체 공백) en으로 처리
        segments.append((current_lang or "en", "".join(current_buf)))

    return segments


# --- PPTX 패킹/언패킹 -------------------------------------------------------

def unpack(pptx_path: Path, work_dir: Path):
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    with zipfile.ZipFile(pptx_path, "r") as z:
        z.extractall(work_dir)
    print(f"Unpacked {pptx_path} → {work_dir}")


def pack(work_dir: Path, output_pptx: Path):
    """
    [Content_Types].xml을 ZIP의 첫 엔트리로 두고, 나머지를 deflate로 압축.
    pptx 사양 준수.
    """
    output_pptx.parent.mkdir(parents=True, exist_ok=True)
    if output_pptx.exists():
        output_pptx.unlink()

    content_types = work_dir / "[Content_Types].xml"
    if not content_types.exists():
        raise FileNotFoundError(f"{content_types} not found")

    with zipfile.ZipFile(output_pptx, "w", zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml을 먼저
        zf.write(content_types, "[Content_Types].xml")

        # 나머지 파일을 디렉토리 순회 순서로
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
    """slide 10, 11, 12의 텍스트를 추출하여 출력."""
    try:
        from lxml import etree
    except ImportError:
        sys.exit("lxml이 필요합니다: pip3 install lxml")

    with zipfile.ZipFile(pptx_path, "r") as z:
        for slide_num in (10, 11, 12):
            slide_path = f"ppt/slides/slide{slide_num}.xml"
            print(f"\n=== Slide {slide_num} ===")
            try:
                xml = z.read(slide_path)
            except KeyError:
                print(f"  (없음)")
                continue
            tree = etree.fromstring(xml)
            for t in tree.iter("{%s}t" % NS["a"]):
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

    else:
        sys.exit(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()

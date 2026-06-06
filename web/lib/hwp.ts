/**
 * HWP 5.x 텍스트 추출기 (주보 파싱용 최소 구현).
 *
 * HWP 5.x = OLE Compound File. BodyText/Section* 스트림을 raw-deflate 해제 후
 * 레코드를 순회하며 HWPTAG_PARA_TEXT(67)에서 UTF-16LE 텍스트를 추출한다.
 */

import { inflateRawSync } from "node:zlib";
import * as CFB from "cfb";

const HWPTAG_PARA_TEXT = 67;

/** 8 WCHAR(16바이트)를 차지하는 인라인/확장 컨트롤 문자 코드 */
const CTRL_EXTENDED = new Set([
  1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23,
]);

function extractParaText(payload: Buffer): string {
  const out: string[] = [];
  let i = 0;
  while (i + 1 < payload.length) {
    const ch = payload.readUInt16LE(i);
    if (ch < 32) {
      if (ch === 9) {
        out.push("\t");
        i += 16; // 탭은 인라인 컨트롤: 8 WCHAR
      } else if (CTRL_EXTENDED.has(ch)) {
        i += 16;
      } else {
        if (ch === 10 || ch === 13) out.push("\n");
        i += 2;
      }
    } else {
      out.push(String.fromCharCode(ch));
      i += 2;
    }
  }
  return out.join("");
}

function extractSectionText(data: Buffer): string {
  const paras: string[] = [];
  let pos = 0;
  while (pos + 4 <= data.length) {
    const hdr = data.readUInt32LE(pos);
    const tag = hdr & 0x3ff;
    let size = (hdr >>> 20) & 0xfff;
    pos += 4;
    if (size === 0xfff) {
      size = data.readUInt32LE(pos);
      pos += 4;
    }
    if (tag === HWPTAG_PARA_TEXT) {
      paras.push(extractParaText(data.subarray(pos, pos + size)));
    }
    pos += size;
  }
  return paras.join("\n");
}

/** HWP 파일 버퍼에서 전체 본문 텍스트를 추출한다. */
export function extractHwpText(buf: Buffer): string {
  const cfb = CFB.read(buf, { type: "buffer" });

  const header = CFB.find(cfb, "/FileHeader");
  if (!header || !header.content) {
    throw new Error("HWP 파일이 아닙니다 (FileHeader 없음)");
  }
  const hdrBuf = Buffer.from(header.content as Uint8Array);
  const signature = hdrBuf.subarray(0, 17).toString("latin1");
  if (!signature.startsWith("HWP Document File")) {
    throw new Error("HWP 5.x 형식이 아닙니다");
  }
  const flags = hdrBuf.readUInt32LE(36);
  const compressed = (flags & 1) === 1;
  if ((flags >> 1) & 1) {
    throw new Error("암호화된 HWP 파일은 지원하지 않습니다");
  }

  const sections = cfb.FullPaths.map((p, idx) => ({ p, idx }))
    .filter(({ p }) => /BodyText\/Section\d+$/.test(p))
    .sort(
      (a, b) =>
        parseInt(a.p.match(/(\d+)$/)![1], 10) -
        parseInt(b.p.match(/(\d+)$/)![1], 10)
    );

  if (sections.length === 0) {
    throw new Error("본문(BodyText)을 찾을 수 없습니다");
  }

  const texts: string[] = [];
  for (const { idx } of sections) {
    const entry = cfb.FileIndex[idx];
    if (!entry.content) continue;
    let raw = Buffer.from(entry.content as Uint8Array);
    if (compressed) raw = inflateRawSync(raw);
    texts.push(extractSectionText(raw));
  }
  return texts.join("\n");
}

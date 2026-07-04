/**
 * 주보 텍스트 → 예배 정보 필드 파싱.
 *
 * 주보 형식 (예: 주보_0607.hwp):
 *   2026-6-7
 *   대표기도 : 허영실 권사
 *   성경본문 : 베드로전서 3:15, 고린도전서 3:6–7
 *   설교제목 : [삶을 낭비하지 말라] 07. ...
 *   설교자 : 이봉연 목사
 *   ... (광고/설교 요약) ...
 *   베드로전서 3:15          ← 본문 전문 섹션
 *   15 오직 여러분의 마음에 ...
 *   고린도전서 3:6–7
 *   6 나는 심고 ...
 */

export interface BulletinFields {
  date: string;
  prayer: string;
  sermonTitle: string;
  preacher: string;
  scriptureRef: string;
  scriptureBody: string;
}

export interface BulletinParseResult {
  /** 추출된 필드. 못 찾은 항목은 빈 문자열로 둔다(폼에서 직접 입력). */
  fields: BulletinFields;
  /** 못 찾았거나 직접 확인이 필요한 항목 안내. 화면에 표시한다. */
  warnings: string[];
}

function cleanLine(line: string): string {
  // 탭 분할 레이아웃 잔여물 제거 + 공백 정리
  return line.replace(/\t+/g, " ").replace(/\s+/g, " ").trim();
}

function labelValue(line: string, label: string): string | null {
  const m = line.match(new RegExp(`^${label}\\s*[:：]\\s*(.+)$`));
  return m ? m[1].trim() : null;
}

/**
 * 주보의 월/일을 기준으로 연도를 보정한다.
 * (주보에 직전 연도가 잘못 적혀 있는 경우가 있어 연도는 신뢰하지 않음)
 * 오늘로부터 -3일 ~ +1년 사이에서 가장 가까운 미래(또는 직전) 날짜를 선택.
 */
export function resolveDate(month: number, day: number, today: Date): string {
  const candidates = [
    today.getFullYear() - 1,
    today.getFullYear(),
    today.getFullYear() + 1,
  ].map((y) => new Date(y, month - 1, day));

  const floor = new Date(today);
  floor.setDate(floor.getDate() - 3);

  const future = candidates.filter((d) => d >= floor);
  const chosen = future.length
    ? future.reduce((a, b) => (a <= b ? a : b))
    : candidates[1];

  return `${chosen.getFullYear()}-${chosen.getMonth() + 1}-${chosen.getDate()}`;
}

/** "15. 오직..." → "15 오직..." (기존 데이터 표기와 통일) */
function normalizeVerseLine(line: string): string {
  return line.replace(/^(\d+)\.\s*/, "$1 ");
}

/**
 * 대시 계열 문자(‐ ‑ ‒ – — ― −)를 하이픈으로 통일.
 * 주보에서 헤더는 en dash(–), 본문 섹션 제목은 하이픈(-)처럼
 * 같은 구절을 다른 대시로 표기하는 경우가 있어 매칭 전에 정규화한다.
 */
function normalizeDashes(s: string): string {
  return s.replace(/[‐-―−]/g, "-");
}

export function parseBulletin(
  text: string,
  today: Date
): BulletinParseResult {
  const rawLines = text.split("\n");
  const lines = rawLines.map(cleanLine);

  let dateStr = "";
  let prayer = "";
  let sermonTitle = "";
  let preacher = "";
  let scriptureRef = "";
  let scriptureRefLineIdx = -1;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line) continue;

    if (!dateStr) {
      const m = line.match(/^(\d{4})[-.\/]\s?(\d{1,2})[-.\/]\s?(\d{1,2})/);
      if (m) {
        dateStr = resolveDate(parseInt(m[2], 10), parseInt(m[3], 10), today);
        continue;
      }
    }
    if (!prayer) {
      const v = labelValue(line, "대표기도");
      if (v) {
        prayer = v;
        continue;
      }
    }
    if (!sermonTitle) {
      const v = labelValue(line, "설교제목");
      if (v) {
        sermonTitle = v;
        continue;
      }
    }
    if (!preacher) {
      const v = labelValue(line, "설교자");
      if (v) {
        preacher = v;
        continue;
      }
    }
    if (!scriptureRef) {
      const v = labelValue(line, "성경본문");
      if (v) {
        scriptureRef = v;
        scriptureRefLineIdx = i;
        continue;
      }
    }
  }

  // 못 찾은 항목은 막지 않고 경고로 안내한다(나머지 필드는 정상 채움).
  const warnings: string[] = [];
  const missing: string[] = [];
  if (!dateStr) missing.push("날짜");
  if (!prayer) missing.push("대표기도");
  if (!sermonTitle) missing.push("설교제목");
  if (!scriptureRef) missing.push("성경본문");
  if (missing.length) {
    warnings.push(`주보에서 찾지 못한 항목: ${missing.join(", ")} (직접 입력해 주세요)`);
  }

  // ---- 성경 본문 전문 추출 ----
  // 약칭 목록 각각에 대해, 헤더 라인("성경본문 : ...") 이후에 다시 등장하는
  // 지점을 찾고 그 다음 절 텍스트를 수집한다.
  // 약칭 구분자는 주보에 따라 콤마(,) · 파이프(|) · 슬래시(/)가 쓰인다.
  const refs = scriptureRef
    .split(/[,|/]/)
    .map((r) => r.trim())
    .filter(Boolean);

  const sections: string[] = [];
  for (let r = 0; r < refs.length; r++) {
    const ref = normalizeDashes(refs[r]);
    let start = -1;
    for (let i = scriptureRefLineIdx + 1; i < lines.length; i++) {
      if (normalizeDashes(lines[i]).startsWith(ref)) {
        start = i;
        break;
      }
    }
    if (start === -1) continue;

    const body: string[] = [];
    for (let i = start + 1; i < lines.length; i++) {
      const line = lines[i];
      if (!line) continue;
      // 다음 약칭 시작 / 새 섹션(<...>, ★, [...]) 도달 시 종료
      if (
        refs.some(
          (other, oi) =>
            oi !== r && normalizeDashes(line).startsWith(normalizeDashes(other))
        )
      )
        break;
      if (/^[<★]/.test(line)) break;
      if (/^\[/.test(line) && !/^\[\d/.test(line)) break;
      // 절 번호로 시작하지 않는 라인이 나오면 본문 종료로 간주
      if (!/^\d+[.\s]/.test(line)) break;
      body.push(normalizeVerseLine(line));
    }
    if (body.length) {
      sections.push([ref, ...body].join("\n"));
    }
  }

  if (sections.length === 0 && scriptureRef) {
    warnings.push(
      "성경 본문 전문을 찾지 못했습니다. 본문 전문은 직접 입력해 주세요."
    );
  }

  return {
    fields: {
      date: dateStr,
      prayer,
      sermonTitle,
      preacher: preacher || "이봉연 목사",
      // 구분자가 있으면 콤마로 정규화, 없으면 원본 약칭을 그대로 둔다.
      scriptureRef: refs.join(", ") || scriptureRef,
      scriptureBody: sections.join("\n\n"),
    },
    warnings,
  };
}

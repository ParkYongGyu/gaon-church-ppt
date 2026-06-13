import { NextRequest, NextResponse } from "next/server";
import { extractHwpText } from "@/lib/hwp";
import { parseBulletin } from "@/lib/bulletin";

export const maxDuration = 60;

/**
 * 주보 HWP 파일을 파싱해 예배 정보 필드를 반환한다 (저장하지 않음).
 * 클라이언트가 결과로 폼을 채운 뒤 기존 /api/worship POST로 저장한다.
 */
export async function POST(req: NextRequest) {
  try {
    const form = await req.formData();
    const file = form.get("file");
    if (!(file instanceof File)) {
      return NextResponse.json(
        { error: "파일이 없습니다" },
        { status: 400 }
      );
    }
    if (file.size > 10 * 1024 * 1024) {
      return NextResponse.json(
        { error: "파일이 너무 큽니다 (10MB 제한)" },
        { status: 400 }
      );
    }

    const buf = Buffer.from(await file.arrayBuffer());

    // KST 기준 오늘 날짜로 연도 보정
    const now = new Date(Date.now() + 9 * 60 * 60 * 1000);
    const today = new Date(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate()
    );

    const text = extractHwpText(buf);
    const { fields, warnings } = parseBulletin(text, today);

    return NextResponse.json({ ok: true, fields, warnings });
  } catch (err: unknown) {
    const msg =
      err instanceof Error ? err.message : "주보 파싱 중 오류가 발생했습니다";
    return NextResponse.json({ error: msg }, { status: 422 });
  }
}

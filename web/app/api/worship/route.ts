import { Redis } from "@upstash/redis";
import { NextRequest, NextResponse } from "next/server";

const redis = new Redis({
  url: process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL || "",
  token:
    process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN || "",
});

const LATEST_KEY = "gaon:next-sunday";

function dateKey(date: string): string {
  return `gaon:date:${date}`;
}

interface WorshipData {
  date: string;
  prayer: string;
  sermonTitle: string;
  preacher: string;
  scriptureRef: string;
  scriptureBody: string;
  recipients: string;
  sermonPptxName: string;
  updatedAt: string;
}

function sermonKey(date: string): string {
  return `gaon:sermon:${date}`;
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const {
      date,
      prayer,
      sermonTitle,
      preacher,
      scriptureRef,
      scriptureBody,
      recipients,
      sermonPptxBase64,
      sermonPptxName,
    } = body;

    if (!date || !prayer || !sermonTitle || !scriptureRef || !scriptureBody) {
      return NextResponse.json(
        { error: "필수 항목이 누락되었습니다" },
        { status: 400 }
      );
    }

    const data: WorshipData = {
      date,
      prayer,
      sermonTitle,
      preacher: preacher || "이봉연 목사",
      scriptureRef,
      scriptureBody,
      recipients: recipients || "",
      sermonPptxName: sermonPptxName || "",
      updatedAt: new Date().toISOString(),
    };

    const saves: Promise<unknown>[] = [
      redis.set(LATEST_KEY, data),
      redis.set(dateKey(date), data),
    ];

    if (sermonPptxBase64) {
      saves.push(redis.set(sermonKey(date), sermonPptxBase64));
    }

    await Promise.all(saves);

    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ error: "서버 오류" }, { status: 500 });
  }
}

export async function GET(req: NextRequest) {
  const date = req.nextUrl.searchParams.get("date");

  if (date) {
    const format = req.nextUrl.searchParams.get("format");

    if (format === "sermon-pptx") {
      const b64 = await redis.get<string>(sermonKey(date));
      if (!b64) {
        return NextResponse.json(null);
      }
      const binary = Buffer.from(b64, "base64");
      return new NextResponse(binary, {
        headers: {
          "Content-Type":
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
          "Content-Disposition": `attachment; filename="sermon.pptx"`,
        },
      });
    }

    const data = await redis.get<WorshipData>(dateKey(date));
    if (!data) {
      return NextResponse.json(null);
    }
    if (format === "txt") {
      const lines = [
        `날짜 : ${data.date}`,
        `대표기도 : ${data.prayer}`,
        `설교제목 : ${data.sermonTitle}`,
        `설교자 : ${data.preacher}`,
        `성경본문 : ${data.scriptureRef}`,
      ];
      if (data.recipients) {
        lines.push(`수신자 : ${data.recipients}`);
      }
      lines.push("", data.scriptureBody);
      const txt = lines.join("\n");
      return new NextResponse(txt, {
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      });
    }
    return NextResponse.json(data);
  }

  const apiKey = req.headers.get("x-api-key");
  const expectedKey = process.env.ROUTINE_API_KEY;

  if (!expectedKey || apiKey !== expectedKey) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const data = await redis.get<WorshipData>(LATEST_KEY);

  if (!data) {
    return NextResponse.json(
      { error: "아직 입력된 데이터가 없습니다" },
      { status: 404 }
    );
  }

  const format = req.nextUrl.searchParams.get("format");

  if (format === "txt") {
    const txt = [
      `날짜 : ${data.date}`,
      `대표기도 : ${data.prayer}`,
      `설교제목 : ${data.sermonTitle}`,
      `설교자 : ${data.preacher}`,
      `성경본문 : ${data.scriptureRef}`,
      "",
      data.scriptureBody,
    ].join("\n");

    return new NextResponse(txt, {
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  return NextResponse.json(data);
}

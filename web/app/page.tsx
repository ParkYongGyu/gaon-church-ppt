"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

function getNextSunday(): string {
  const today = new Date();
  const day = today.getDay();
  const diff = day === 0 ? 7 : 7 - day;
  const next = new Date(today);
  next.setDate(today.getDate() + diff);
  const y = next.getFullYear();
  const m = next.getMonth() + 1;
  const d = next.getDate();
  return `${y}-${m}-${d}`;
}

const inputClass =
  "w-full rounded-lg border border-stone-300 bg-white px-3 py-2 shadow-sm placeholder:text-stone-400 focus:border-stone-500 focus:ring-1 focus:ring-stone-500 focus:outline-none";

export default function Home() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [date, setDate] = useState(getNextSunday);
  const [prayer, setPrayer] = useState("");
  const [sermonTitle, setSermonTitle] = useState("");
  const [preacher, setPreacher] = useState("이봉연 목사");
  const [scriptureRef, setScriptureRef] = useState("");
  const [scriptureBody, setScriptureBody] = useState("");
  const [recipients, setRecipients] = useState("gikimiad@gmail.com");
  const [sermonFile, setSermonFile] = useState<File | null>(null);
  const [sermonFileName, setSermonFileName] = useState("");

  const loadByDate = useCallback(async (d: string) => {
    if (!d.match(/^\d{4}-\d{1,2}-\d{1,2}$/)) return;

    setLoading(true);
    try {
      const res = await fetch(`/api/worship?date=${encodeURIComponent(d)}`);
      if (!res.ok) return;
      const data = await res.json();
      if (!data) return;

      setPrayer(data.prayer || "");
      setSermonTitle(data.sermonTitle || "");
      setPreacher(data.preacher || "이봉연 목사");
      setScriptureRef(data.scriptureRef || "");
      setScriptureBody(data.scriptureBody || "");
      setRecipients(data.recipients || "gikimiad@gmail.com");
      setSermonFileName(data.sermonPptxName || "");
    } catch {
      /* 무시 */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadByDate(date);
  }, [date, loadByDate]);

  function handleDateChange(newDate: string) {
    setDate(newDate);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError("");

    try {
      let sermonPptxBase64 = "";
      let sermonPptxName = "";
      if (sermonFile) {
        const buf = await sermonFile.arrayBuffer();
        sermonPptxBase64 = btoa(
          new Uint8Array(buf).reduce((s, b) => s + String.fromCharCode(b), "")
        );
        sermonPptxName = sermonFile.name;
      }

      const res = await fetch("/api/worship", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          date,
          prayer,
          sermonTitle,
          preacher,
          scriptureRef,
          scriptureBody,
          recipients,
          sermonPptxBase64,
          sermonPptxName,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "저장 실패");
      }

      router.push("/success");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "알 수 없는 오류");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-lg px-4 py-8">
      <header className="mb-8 text-center">
        <h1 className="text-2xl font-bold text-stone-800">
          가온교회 주일예배
        </h1>
        <p className="mt-1 text-sm text-stone-500">
          슬라이드 생성을 위한 예배 정보 입력
        </p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-5">
        <Field label="날짜" required>
          <div className="relative">
            <input
              type="text"
              value={date}
              onChange={(e) => handleDateChange(e.target.value)}
              placeholder="2026-5-4"
              className={inputClass}
              required
            />
            {loading && (
              <span className="absolute top-1/2 right-3 -translate-y-1/2 text-xs text-stone-400">
                불러오는 중...
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-stone-400">
            형식: YYYY-M-D (예: 2026-5-4) — 기존 입력이 있으면 자동으로
            불러옵니다
          </p>
        </Field>

        <Field label="대표기도" required>
          <input
            type="text"
            value={prayer}
            onChange={(e) => setPrayer(e.target.value)}
            placeholder="홍길동 집사"
            className={inputClass}
            required
          />
        </Field>

        <Field label="설교제목" required>
          <input
            type="text"
            value={sermonTitle}
            onChange={(e) => setSermonTitle(e.target.value)}
            placeholder="[삶을 낭비하지 말라] 02_그리스도의 아름다움과 기쁨"
            className={inputClass}
            required
          />
        </Field>

        <Field label="설교자">
          <input
            type="text"
            value={preacher}
            onChange={(e) => setPreacher(e.target.value)}
            className={inputClass}
          />
        </Field>

        <Field label="성경본문 (약칭)" required>
          <input
            type="text"
            value={scriptureRef}
            onChange={(e) => setScriptureRef(e.target.value)}
            placeholder="요 17:3, 고후 4:4-6, 빌 3:7-8"
            className={inputClass}
            required
          />
          <p className="mt-1 text-xs text-stone-400">
            슬라이드 11번에 표시될 본문 약칭 (콤마 구분)
          </p>
        </Field>

        <Field label="성경 본문 전문" required>
          <textarea
            value={scriptureBody}
            onChange={(e) => setScriptureBody(e.target.value)}
            placeholder={`요 17:3\n영생은 곧 유일하신 참 하나님과 그가 보내신 자 예수 그리스도를 아는 것이니이다\n\n고후 4:4-6\n4 그 중에 이 세상의 신이 믿지 아니하는 자들의 마음을 혼미하게 하여...\n5 우리는 자기를 전파하는 것이 아니라...\n6 어둠에서 빛이 비치라 하시던 그 하나님께서...`}
            rows={36}
            className={`${inputClass} font-mono text-sm`}
            required
          />
          <p className="mt-1 text-xs text-stone-400">
            각 본문 사이는 빈 줄로 구분. 여러 절이면 절 번호로 시작.
          </p>
        </Field>

        <Field label="수신자 이메일">
          <input
            type="text"
            value={recipients}
            onChange={(e) => setRecipients(e.target.value)}
            placeholder="gikimiad@gmail.com, someone@example.com"
            className={inputClass}
          />
          <p className="mt-1 text-xs text-stone-400">
            콤마(,)로 구분하여 여러 명에게 발송 가능
          </p>
        </Field>

        <Field label="추가 설교 PPT (선택)">
          <input
            type="file"
            accept=".pptx"
            onChange={(e) => {
              const f = e.target.files?.[0] || null;
              setSermonFile(f);
              if (f) setSermonFileName(f.name);
            }}
            className={inputClass}
          />
          {sermonFileName && !sermonFile && (
            <p className="mt-1 text-xs text-stone-500">
              기존 업로드: {sermonFileName}
            </p>
          )}
          <p className="mt-1 text-xs text-stone-400">
            이철준 원로목사 등 별도 설교 슬라이드가 있을 때 업로드
          </p>
        </Field>

        {error && (
          <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-stone-800 px-4 py-3 font-medium text-white transition hover:bg-stone-700 disabled:opacity-50"
        >
          {submitting ? "저장 중..." : "저장"}
        </button>
      </form>
    </main>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-stone-700">
        {label}
        {required && <span className="text-red-500"> *</span>}
      </span>
      {children}
    </label>
  );
}

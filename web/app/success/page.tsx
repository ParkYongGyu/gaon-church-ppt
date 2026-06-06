import Link from "next/link";

export default async function Success({
  searchParams,
}: {
  searchParams: Promise<{ generated?: string }>;
}) {
  const { generated } = await searchParams;
  const immediate = generated === "1";

  return (
    <main className="mx-auto max-w-lg px-4 py-16 text-center">
      <div className="mb-6 text-5xl">&#10003;</div>
      <h1 className="text-xl font-bold text-stone-800">저장 완료</h1>
      <p className="mt-2 text-stone-500">
        {immediate
          ? "슬라이드 생성이 시작되었습니다. 약 1~2분 후 Drive 업로드와 메일 발송이 완료됩니다."
          : "저장만 완료되었습니다. PPT 생성은 “저장하고 바로 생성”으로 실행하세요."}
      </p>
      <Link
        href="/"
        className="mt-6 inline-block text-sm text-stone-500 underline hover:text-stone-700"
      >
        다시 입력하기
      </Link>
    </main>
  );
}

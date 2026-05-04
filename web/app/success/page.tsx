import Link from "next/link";

export default function Success() {
  return (
    <main className="mx-auto max-w-lg px-4 py-16 text-center">
      <div className="mb-6 text-5xl">&#10003;</div>
      <h1 className="text-xl font-bold text-stone-800">저장 완료</h1>
      <p className="mt-2 text-stone-500">
        토요일 저녁 8시에 슬라이드가 자동 생성됩니다.
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

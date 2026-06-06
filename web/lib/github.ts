/**
 * GitHub Actions 워크플로우 트리거 (repository_dispatch).
 *
 * 환경변수:
 *   GH_DISPATCH_TOKEN — repo 권한이 있는 GitHub PAT
 *   GH_REPO           — "owner/repo" (기본: ParkYongGyu/gaon-church-ppt)
 */

const DEFAULT_REPO = "ParkYongGyu/gaon-church-ppt";

export async function dispatchGeneratePpt(
  date: string
): Promise<{ dispatched: boolean; error?: string }> {
  const token = process.env.GH_DISPATCH_TOKEN;
  if (!token) {
    return {
      dispatched: false,
      error: "GH_DISPATCH_TOKEN 미설정 — 토요일 자동 생성 시 반영됩니다",
    };
  }

  const repo = process.env.GH_REPO || DEFAULT_REPO;
  const res = await fetch(`https://api.github.com/repos/${repo}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({
      event_type: "generate-ppt",
      client_payload: { date },
    }),
  });

  if (res.status === 204) {
    return { dispatched: true };
  }
  const text = await res.text();
  return {
    dispatched: false,
    error: `GitHub 트리거 실패 (${res.status}): ${text.slice(0, 200)}`,
  };
}

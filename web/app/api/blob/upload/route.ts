import { handleUpload, type HandleUploadBody } from "@vercel/blob/client";
import { NextResponse } from "next/server";

/**
 * 대용량 설교 PPT를 브라우저에서 Vercel Blob로 직접 업로드하기 위한
 * 클라이언트 토큰 발급 엔드포인트.
 *
 * Vercel Function 본문 한도(4.5MB)를 우회하기 위해, 파일 자체는
 * 브라우저 → Blob 으로 직접 전송되고 여기서는 짧은 토큰만 발급한다.
 */
export async function POST(request: Request): Promise<NextResponse> {
  const body = (await request.json()) as HandleUploadBody;

  try {
    const jsonResponse = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async () => ({
        // .pptx 및 일부 브라우저가 비우는 경우(octet-stream)까지 허용
        allowedContentTypes: [
          "application/vnd.openxmlformats-officedocument.presentationml.presentation",
          "application/octet-stream",
        ],
        addRandomSuffix: true,
        maximumSizeInBytes: 200 * 1024 * 1024, // 200MB
      }),
      // 프로덕션에서만 호출됨(공개 URL 필요). 결과 URL은 클라이언트가
      // upload() 반환값으로 직접 받으므로 여기서는 별도 처리 불필요.
      onUploadCompleted: async () => {},
    });

    return NextResponse.json(jsonResponse);
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message },
      { status: 400 }
    );
  }
}

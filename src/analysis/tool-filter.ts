/** NAVER_TOOLS_ALLOW 값(쉼표 구분)을 Set으로. 비어 있으면 null(전체 허용). */
export function parseToolAllowList(raw: string | undefined): Set<string> | null {
  const names = (raw ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return names.length > 0 ? new Set(names) : null;
}

/** 허용 목록에 없는 도구는 등록하지 않도록 server.registerTool을 감싼다. */
export function applyToolFilter(
  server: { registerTool: (...args: any[]) => any },
  allow: Set<string> | null
): void {
  if (!allow) return;
  const original = server.registerTool.bind(server);
  server.registerTool = (name: string, ...rest: any[]) =>
    allow.has(name) ? original(name, ...rest) : undefined;
}

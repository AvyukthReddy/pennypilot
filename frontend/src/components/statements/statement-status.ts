const NON_TERMINAL_STATUSES = new Set(["uploaded", "queued", "processing"]);

export function isNonTerminalStatus(status: string): boolean {
  return NON_TERMINAL_STATUSES.has(status);
}

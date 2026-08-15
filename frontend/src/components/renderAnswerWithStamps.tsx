import type { ReactNode } from "react";
import { CitationStamp } from "./CitationStamp";

const CITATION_PATTERN = /\[(doc|award):([\w-]+)\]/g;

export function renderAnswerWithStamps(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  CITATION_PATTERN.lastIndex = 0;
  while ((match = CITATION_PATTERN.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const [, kind, id] = match;
    parts.push(<CitationStamp key={`stamp-${key++}`} label={`${kind}:${id}`} variant="verified" />);
    lastIndex = CITATION_PATTERN.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}

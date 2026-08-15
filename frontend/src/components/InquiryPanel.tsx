import { useState } from "react";
import { postChat } from "../api/client";
import { renderAnswerWithStamps } from "./renderAnswerWithStamps";
import { Input } from "./ui/input";

export interface InquiryPanelProps {
  conversationId: string;
}

interface Turn {
  role: "user" | "answer" | "clarification" | "error";
  text: string;
  droppedCount?: number;
}

export function InquiryPanel({ conversationId }: InquiryPanelProps) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  async function send() {
    const message = draft.trim();
    if (!message || sending) return;
    setDraft("");
    setTurns((prev) => [...prev, { role: "user", text: message }]);
    setSending(true);
    try {
      const response = await postChat(conversationId, message);
      if (response.needs_clarification) {
        setTurns((prev) => [...prev, { role: "clarification", text: response.clarification_question ?? "" }]);
      } else {
        setTurns((prev) => [
          ...prev,
          { role: "answer", text: response.answer, droppedCount: response.dropped_claims.length },
        ]);
      }
    } catch {
      setTurns((prev) => [...prev, { role: "error", text: "Something went wrong — try again." }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex w-full shrink-0 flex-col border-hairline bg-card md:w-[290px] md:border-l">
      <div className="border-b border-hairline p-3.5 font-mono text-xs uppercase tracking-wider text-muted">
        Inquiry log
      </div>
      <div className="flex-1 space-y-3.5 overflow-y-auto p-4">
        {turns.map((turn, index) => {
          if (turn.role === "user") {
            return (
              <div key={index} className="ml-auto max-w-[85%] rounded-lg rounded-br-sm bg-paper px-2.5 py-2 text-xs">
                {turn.text}
              </div>
            );
          }
          if (turn.role === "clarification") {
            return (
              <div key={index} className="rounded border border-primary/40 bg-paper px-2.5 py-2 text-xs text-ink">
                {turn.text}
              </div>
            );
          }
          if (turn.role === "error") {
            return (
              <div key={index} className="rounded border border-destructive/40 px-2.5 py-2 text-xs text-destructive">
                {turn.text}
              </div>
            );
          }
          return (
            <div key={index} className="border-t-2 border-primary pt-2 text-xs leading-relaxed text-ink">
              <div>{renderAnswerWithStamps(turn.text)}</div>
              {!!turn.droppedCount && (
                <div className="mt-1.5 font-mono text-[10px] text-muted">
                  {turn.droppedCount} unverifiable claim{turn.droppedCount === 1 ? "" : "s"} omitted
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="border-t border-hairline p-3">
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") send();
          }}
          placeholder="Ask a follow-up…"
          aria-label="Ask a follow-up question"
          disabled={sending}
        />
      </div>
    </div>
  );
}

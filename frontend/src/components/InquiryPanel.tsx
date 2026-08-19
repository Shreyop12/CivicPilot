import { useEffect, useRef, useState } from "react";
import { postChat } from "../api/client";
import { AnswerMarkdown } from "./AnswerMarkdown";
import { Input } from "./ui/input";

export interface InquiryPanelProps {
  conversationId: string;
}

interface Turn {
  role: "user" | "answer" | "clarification" | "error";
  text: string;
  droppedCount?: number;
}

const MIN_WIDTH = 280;
const MAX_WIDTH = 560;
const DEFAULT_WIDTH = 340;
const WIDTH_STORAGE_KEY = "civicpilot.inquiry-panel-width";

function readStoredWidth(): number {
  if (typeof window === "undefined") return DEFAULT_WIDTH;
  const stored = Number(window.localStorage.getItem(WIDTH_STORAGE_KEY));
  return stored >= MIN_WIDTH && stored <= MAX_WIDTH ? stored : DEFAULT_WIDTH;
}

export function InquiryPanel({ conversationId }: InquiryPanelProps) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [width, setWidth] = useState(readStoredWidth);
  const panelRef = useRef<HTMLDivElement>(null);
  const resizingRef = useRef(false);
  const widthRef = useRef(width);

  useEffect(() => {
    widthRef.current = width;
  }, [width]);

  useEffect(() => {
    function onPointerMove(event: PointerEvent) {
      if (!resizingRef.current || !panelRef.current) return;
      const right = panelRef.current.getBoundingClientRect().right;
      const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, right - event.clientX));
      setWidth(next);
    }
    function onPointerUp() {
      if (!resizingRef.current) return;
      resizingRef.current = false;
      document.body.style.removeProperty("cursor");
      window.localStorage.setItem(WIDTH_STORAGE_KEY, String(widthRef.current));
    }
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, []);

  function startResize(event: React.PointerEvent) {
    event.preventDefault();
    resizingRef.current = true;
    document.body.style.cursor = "col-resize";
  }

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
    <div
      ref={panelRef}
      className="relative flex w-full min-w-0 shrink-0 flex-col border-hairline bg-card md:w-[var(--panel-width)] md:border-l"
      style={{ "--panel-width": `${width}px` } as React.CSSProperties}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize inquiry log"
        onPointerDown={startResize}
        className="absolute inset-y-0 left-0 hidden w-3 -translate-x-1/2 cursor-col-resize touch-none select-none md:block"
      />
      <div className="border-b border-hairline p-3.5 font-mono text-xs uppercase tracking-wider text-muted">
        Inquiry log
      </div>
      <div className="min-w-0 flex-1 space-y-3.5 overflow-y-auto overflow-x-hidden p-4">
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
            <div key={index} className="min-w-0 border-t-2 border-primary pt-2 text-xs leading-relaxed text-ink">
              <AnswerMarkdown text={turn.text} />
              {!!turn.droppedCount && (
                <div className="mt-1.5 font-mono text-[10px] text-muted">
                  {turn.droppedCount} unverifiable claim{turn.droppedCount === 1 ? "" : "s"} omitted
                </div>
              )}
            </div>
          );
        })}
        {sending && (
          <div className="flex items-center gap-1.5 text-xs text-muted" aria-live="polite">
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted [animation-delay:-0.3s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted [animation-delay:-0.15s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted" />
            <span>Looking this up…</span>
          </div>
        )}
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

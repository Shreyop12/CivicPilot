import { useEffect, useState } from "react";
import { fetchAgencies } from "./api/client";
import type { AgencySummary } from "./api/types";
import { AgencyRail } from "./components/AgencyRail";
import { AgencyRecord } from "./components/AgencyRecord";
import { InquiryPanel } from "./components/InquiryPanel";
import { Button } from "./components/ui/button";

function newConversationId(): string {
  return crypto.randomUUID();
}

export function App() {
  const [agencies, setAgencies] = useState<AgencySummary[]>([]);
  const [selected, setSelected] = useState<AgencySummary | null>(null);
  const [conversationId, setConversationId] = useState<string>(() => newConversationId());
  const [railOpen, setRailOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    fetchAgencies().then(setAgencies).catch(() => setAgencies([]));
  }, []);

  function handleSelect(agency: AgencySummary) {
    setSelected(agency);
    setConversationId(newConversationId());
    setRailOpen(false);
  }

  return (
    <div className="flex h-screen flex-col bg-paper text-ink md:flex-row">
      <div className="flex items-center justify-between border-b border-hairline bg-card p-3 lg:hidden">
        <Button variant="outline" size="sm" onClick={() => setRailOpen(true)}>
          Agencies
        </Button>
        <span className="font-serif text-sm">{selected?.name ?? "CivicPilot"}</span>
        <Button variant="outline" size="sm" className="md:hidden" onClick={() => setChatOpen(true)}>
          Ask
        </Button>
      </div>

      <div className={`${railOpen ? "fixed inset-0 z-20 bg-paper" : "hidden"} lg:relative lg:z-auto lg:block`}>
        {railOpen && (
          <Button variant="outline" size="sm" className="m-2 lg:hidden" onClick={() => setRailOpen(false)}>
            Close
          </Button>
        )}
        <AgencyRail agencies={agencies} selectedToptierCode={selected?.toptier_code ?? null} onSelect={handleSelect} />
      </div>

      <main className="flex-1 overflow-y-auto">
        {selected ? (
          <AgencyRecord toptierCode={selected.toptier_code} />
        ) : (
          <div className="p-6 text-sm text-muted">Select an agency to view its record.</div>
        )}
      </main>

      <div className={`${chatOpen ? "fixed inset-x-0 bottom-0 z-20 h-[70vh]" : "hidden"} md:relative md:z-auto md:block md:h-auto`}>
        {chatOpen && (
          <Button variant="outline" size="sm" className="m-2 md:hidden" onClick={() => setChatOpen(false)}>
            Close
          </Button>
        )}
        <InquiryPanel conversationId={conversationId} />
      </div>
    </div>
  );
}

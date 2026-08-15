import { useMemo, useState } from "react";
import type { AgencySummary } from "../api/types";
import { Input } from "./ui/input";

export interface AgencyRailProps {
  agencies: AgencySummary[];
  selectedToptierCode: string | null;
  onSelect: (agency: AgencySummary) => void;
}

export function AgencyRail({ agencies, selectedToptierCode, onSelect }: AgencyRailProps) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return agencies;
    return agencies.filter((agency) => agency.name.toLowerCase().includes(q));
  }, [agencies, query]);

  return (
    <nav className="w-full shrink-0 border-hairline bg-card md:w-[220px] md:border-r" aria-label="Agencies">
      <div className="p-3">
        <Input
          placeholder="Search agencies…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search agencies"
        />
      </div>
      <ul>
        {filtered.map((agency) => (
          <li key={agency.toptier_code}>
            <button
              type="button"
              onClick={() => onSelect(agency)}
              className={`flex min-h-11 w-full items-center justify-between px-3.5 py-2 text-left text-sm ${
                agency.toptier_code === selectedToptierCode
                  ? "border-l-2 border-primary bg-paper font-semibold"
                  : ""
              }`}
            >
              <span>{agency.name}</span>
              <span className="font-mono text-[10px] text-muted">{agency.toptier_code}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

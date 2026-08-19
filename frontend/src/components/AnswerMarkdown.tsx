import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CitationStamp } from "./CitationStamp";

const CITATION_PATTERN = /\[(doc|award):([\w-]+)\]/g;
const CITATION_SCHEME = "citation:";

function withCitationLinks(text: string): string {
  return text.replace(CITATION_PATTERN, (_match, kind: string, id: string) => `[${kind}:${id}](${CITATION_SCHEME}${kind}:${id})`);
}

const components: Components = {
  a({ href, children }) {
    if (href?.startsWith(CITATION_SCHEME)) {
      return <CitationStamp label={href.slice(CITATION_SCHEME.length)} variant="verified" />;
    }
    return (
      <a href={href} target="_blank" rel="noreferrer" className="underline decoration-dotted underline-offset-2">
        {children}
      </a>
    );
  },
  p({ children }) {
    return <p className="mb-2 last:mb-0">{children}</p>;
  },
  strong({ children }) {
    return <strong className="font-semibold text-ink">{children}</strong>;
  },
  ul({ children }) {
    return <ul className="mb-2 list-disc space-y-1 pl-4 last:mb-0">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="mb-2 list-decimal space-y-1 pl-4 last:mb-0">{children}</ol>;
  },
  li({ children }) {
    return <li className="pl-0.5">{children}</li>;
  },
  code({ children }) {
    return <code className="rounded bg-paper px-1 py-0.5 font-mono text-[11px]">{children}</code>;
  },
  table({ children }) {
    return (
      <div className="mb-2 overflow-x-auto rounded border border-hairline last:mb-0">
        <table className="w-full border-collapse text-left text-[11px]">{children}</table>
      </div>
    );
  },
  thead({ children }) {
    return <thead className="bg-paper font-mono uppercase tracking-wide text-muted">{children}</thead>;
  },
  th({ children }) {
    return <th className="whitespace-nowrap border-b border-hairline px-2 py-1.5 font-medium">{children}</th>;
  },
  td({ children }) {
    return <td className="border-b border-hairline px-2 py-1.5 align-top last:border-b-0">{children}</td>;
  },
  tr({ children }) {
    return <tr className="last:[&>td]:border-b-0">{children}</tr>;
  },
};

export interface AnswerMarkdownProps {
  text: string;
}

function urlTransform(url: string): string {
  return url.startsWith(CITATION_SCHEME) ? url : defaultUrlTransform(url);
}

export function AnswerMarkdown({ text }: AnswerMarkdownProps) {
  return (
    <div className="space-y-2 [&_p]:leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components} urlTransform={urlTransform}>
        {withCitationLinks(text)}
      </ReactMarkdown>
    </div>
  );
}

import type { NoticeLevel } from "../lib/notices";
import { SafeSignalMark, WarningIcon } from "./icons";

export function NoticeBadge({ level }: { level: NoticeLevel }) {
  if (level === "warning") {
    return (
      <span className="flex size-9 shrink-0 items-center justify-center rounded-[9px] bg-caution-soft text-caution">
        <WarningIcon size={22} />
      </span>
    );
  }
  return <SafeSignalMark size={36} />;
}

export function NoticeContent({ level, title, body }: { level: NoticeLevel; title: string; body: string }) {
  return (
    <span className="flex items-start gap-3 text-left">
      <NoticeBadge level={level} />
      <span className="min-w-0">
        <span className="block text-[15px] font-semibold leading-5 text-ink">{title}</span>
        <span className="mt-0.5 block text-pretty text-[14px] leading-5 text-muted">{body}</span>
      </span>
    </span>
  );
}

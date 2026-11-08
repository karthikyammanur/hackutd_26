import { ChevronRightIcon, PlusIcon, SafeSignalMark } from "../components/icons";
import { SectionTitle, TabHeader, TabPage } from "../components/ui";

function CoverageCard() {
  return (
    <div className="relative mt-2 overflow-hidden rounded-xl bg-[#8f0a4f]">
      <svg viewBox="0 0 350 250" className="block w-full" aria-hidden="true">
        <path d="M0 62h350M0 170h350M84 0v250M238 0v250" stroke="#6e083d" strokeWidth="6" />
        <path d="M152 0c10 60-12 96 16 150s-8 66-6 100" fill="none" stroke="#f3c5da" strokeWidth="1.500" />
        <path d="M122 92h78V10h116v58h28v62h-72v86h-60v-86h-90z" fill="#ff5ca1" />
        <circle cx="176" cy="104" r="17" fill="#fff" />
        <circle cx="176" cy="104" r="8" fill="#8f0a4f" />
        <circle cx="176" cy="133" r="9" fill="#3b82f6" stroke="#fff" strokeWidth="3" />
      </svg>
      <div className="absolute inset-x-2 bottom-2 flex items-center justify-between rounded-lg bg-white/85 p-3 text-ink backdrop-blur-sm">
        <div>
          <p className="text-[12px]">Network coverage</p>
          <p className="text-[15px] font-medium">5G coverage available</p>
          <p className="text-[12px] text-muted">Near Sample Ave</p>
        </div>
        <span className="flex size-11 items-center justify-center rounded-md bg-plum text-[14px] font-bold text-white">
          5G
        </span>
      </div>
    </div>
  );
}

export function Services({ onOpenInbox }: { onOpenInbox: () => void }) {
  return (
    <TabPage>
      <TabHeader title="Services" actions={<PlusIcon />} />
      <div className="px-5">
        <CoverageCard />
        <div className="mt-7">
          <SectionTitle>Security</SectionTitle>
        </div>
        <button
          type="button"
          onClick={onOpenInbox}
          className="mt-3 flex min-h-11 w-full items-center gap-3 rounded-xl border border-line p-3.5 text-left"
        >
          <SafeSignalMark />
          <span className="min-w-0 flex-1">
            <span className="block text-[15px] font-semibold">Safe Signal</span>
            <span className="block text-[14px] text-muted">On. See your call notifications.</span>
          </span>
          <ChevronRightIcon size={18} />
        </button>
        <div className="mt-7">
          <SectionTitle>More for you</SectionTitle>
        </div>
        <ul className="mt-3 grid grid-cols-2 gap-3">
          <li className="on-dark h-[150px] rounded-xl bg-[radial-gradient(circle_at_50%_120%,#6a2b8f_0%,#14101f_62%)] p-3.5 text-white">
            <p className="text-[13px]">Satellite</p>
            <p className="mt-1 text-[16px] font-medium leading-5">Connected in more places</p>
          </li>
          <li className="h-[150px] rounded-xl border border-line bg-[linear-gradient(160deg,#f7f3fb,#f2d9e8)] p-3.5">
            <p className="text-[13px]">Home Internet</p>
            <p className="mt-1 text-[16px] font-medium leading-5">Set up your gateway</p>
          </li>
        </ul>
      </div>
    </TabPage>
  );
}

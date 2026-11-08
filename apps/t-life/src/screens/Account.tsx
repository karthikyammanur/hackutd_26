import { PhoneArt } from "../components/art";
import {
  AddPersonIcon,
  ChevronRightIcon,
  ClipboardIcon,
  DeviceIcon,
  GearIcon,
  PeopleIcon,
  PersonIcon,
  PlusIcon,
} from "../components/icons";
import { SectionTitle, ShortcutRow, StatusChip, TabHeader, TabPage } from "../components/ui";
import { DEMO_MEMBER_NUMBER } from "../lib/notices";

export function Account() {
  return (
    <TabPage>
      <TabHeader
        title="Account"
        actions={
          <>
            <GearIcon />
            <PersonIcon />
          </>
        }
      />
      <div className="px-5">
        <h2 className="mt-3 text-[26px] font-medium">Sample plan</h2>
        <p className="mt-0.5 text-[15px]">+ Home Internet</p>
        <ShortcutRow
          items={[
            { label: "My plans", Icon: ClipboardIcon },
            { label: "Add-ons", Icon: PlusIcon },
            { label: "Add a line", Icon: DeviceIcon },
            { label: "Account", Icon: PeopleIcon },
          ]}
        />
        <div className="mt-8">
          <SectionTitle>Billing and payments</SectionTitle>
        </div>
        <div className="mt-3 rounded-xl border border-line p-4">
          <div className="flex items-start justify-between">
            <p className="text-[14px]">Current balance</p>
            <StatusChip>AutoPay on</StatusChip>
          </div>
          <p className="mt-1 text-[34px] font-bold leading-10">$XX.XX</p>
          <p className="mt-2 text-[14px] text-muted">Sample bill for the demo</p>
        </div>
        <div className="mt-8">
          <SectionTitle>Lines and devices</SectionTitle>
        </div>
        <div className="mt-3 flex items-center gap-3 rounded-xl border border-line p-3.5">
          <PhoneArt className="h-[78px] w-[56px] shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-[16px] font-semibold">Demo (You)</p>
            <p className="text-[14px] text-muted">Sample phone 5</p>
            <p className="text-[14px] text-muted">{DEMO_MEMBER_NUMBER}</p>
            <div className="mt-1">
              <StatusChip tone="green">Upgrade available</StatusChip>
            </div>
          </div>
          <ChevronRightIcon size={18} />
        </div>
        <div className="mt-3 flex items-center gap-2 text-[14px] text-muted">
          <AddPersonIcon size={18} />
          One line on this demo account
        </div>
        <p className="mt-6 text-[13px] leading-[1.45] text-muted">
          This is a Safe Signal demo built for HackUTD. It isn't a T-Mobile app, and all account content is made up.
        </p>
      </div>
    </TabPage>
  );
}

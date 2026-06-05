import { Loader2, ShieldCheck } from "lucide-react";

export default function ControlOverlay({ isChecking, onCheckIdentity }) {
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-[78px] z-40 flex justify-center sm:bottom-[86px]">
      <button
        type="button"
        title="Check Identity"
        aria-label="Check Identity"
        disabled={isChecking}
        onClick={onCheckIdentity}
        className="pointer-events-auto flex h-12 w-12 items-center justify-center rounded-full border border-slate-600 bg-slate-800 text-white shadow-xl transition hover:scale-[1.03] hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-70"
      >
        {isChecking ? <Loader2 size={20} className="animate-spin" /> : <ShieldCheck size={20} />}
      </button>
    </div>
  );
}

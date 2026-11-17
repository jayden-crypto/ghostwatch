import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { API_BASE_URL, API_MODE } from "@/lib/api/config";

/**
 * Says where the numbers on screen come from. In mock mode it is loud on purpose: fixture data
 * must never be mistaken for real data.
 */
export function ModeBadge() {
  if (API_MODE === "mock") {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            tabIndex={0}
            data-testid="mode-badge"
            className="rounded-sm border border-timed-out/50 px-1.5 py-0.5 font-mono text-[11px] font-medium tracking-wider text-timed-out"
          >
            MOCK DATA
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom">Everything on screen comes from contract fixtures, not from a backend.</TooltipContent>
      </Tooltip>
    );
  }
  return (
    <span data-testid="mode-badge" className="font-mono text-[11px] text-fg-subtle" title="Data comes from this API">
      {API_BASE_URL.replace(/^https?:\/\//, "")}
    </span>
  );
}

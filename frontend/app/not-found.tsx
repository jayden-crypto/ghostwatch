import { SearchX } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/data/empty-state";
import { Page } from "@/components/shell/page";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <Page title="Page not found">
      <EmptyState
        icon={SearchX}
        title="There is nothing at this address"
        description="The link may be wrong, or the page may have moved."
        action={
          <Button asChild variant="outline" size="sm">
            <Link href="/">Go to the overview</Link>
          </Button>
        }
      />
    </Page>
  );
}

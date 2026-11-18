import { useQuery } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Providers } from "@/components/shell/providers";

function Probe() {
  const { data } = useQuery({ queryKey: ["probe"], queryFn: async () => "loaded" });
  return <p>{data ?? "loading"}</p>;
}

describe("Providers", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows a finished request without waiting for a timer", async () => {
    // A hidden tab or pane throttles timers; here they never fire at all. The data must still arrive.
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    render(
      <Providers>
        <Probe />
      </Providers>,
    );
    await act(async () => {
      for (let tick = 0; tick < 10; tick++) await Promise.resolve();
    });
    expect(screen.getByText("loaded")).toBeInTheDocument();
  });
});

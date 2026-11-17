import type { Metadata } from "next";

import { Gallery } from "./gallery";

export const metadata: Metadata = { title: "Component gallery" };

/** Not in the navigation. Every badge for every enum value, and the shared states, on one page. */
export default function ComponentGalleryPage() {
  return <Gallery />;
}

import type { ReactNode } from "react";

/** A navigation entry supplied by a separately built Studio distribution. */
export type StudioNavigationContribution = {
  href: string;
  icon: ReactNode;
  label: string;
  enabled?: boolean;
};

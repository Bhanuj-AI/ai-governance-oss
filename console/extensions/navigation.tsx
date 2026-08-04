import type { StudioNavigationContribution } from "@/extensions/types";

/**
 * Build-time navigation contributions for a Kavach Studio distribution.
 *
 * OSS ships an empty manifest. A separately built distribution, such as
 * Kavach Enterprise, may replace this file in its Studio image and copy the
 * corresponding Next.js routes into the build context. This keeps the OSS
 * console free of edition checks while preserving one Studio URL and shell.
 */
export const STUDIO_NAVIGATION_CONTRIBUTIONS: readonly StudioNavigationContribution[] = [];

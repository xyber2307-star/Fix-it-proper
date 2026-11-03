// Single source of truth for per-route head tags, shared by the client
// head hook and the build time prerender step.

import { BRAND } from "../config/brand";

export interface PageMeta {
  path: string;
  shortTitle: string;
  fullTitle: string;
  description: string;
}

export const PAGE_META: PageMeta[] = [
  {
    path: "/",
    shortTitle: "Home",
    fullTitle: `${BRAND.name}: Website diagnosis for small business owners`,
    description: `${BRAND.name} analyzes a public website URL and returns ranked fixes with evidence.`,
  },
  {
    path: "/privacy",
    shortTitle: "Privacy Policy",
    fullTitle: `Privacy Policy - ${BRAND.name}`,
    description: `How ${BRAND.name} handles submitted URLs, fetched page content, logs, caches, and third party processors.`,
  },
  {
    path: "/terms",
    shortTitle: "Terms and Conditions",
    fullTitle: `Terms and Conditions - ${BRAND.name}`,
    description: `The rules for using ${BRAND.name}: acceptable use, AI suggestions, availability, and liability.`,
  },
  {
    path: "/contact",
    shortTitle: "Contact",
    fullTitle: `Contact - ${BRAND.name}`,
    description: `Contact the ${BRAND.name} operator by email or through the contact form.`,
  },
  {
    path: "/signin",
    shortTitle: "Sign in",
    fullTitle: `Sign in - ${BRAND.name}`,
    description: `Sign in to ${BRAND.name} with email or Google to keep a history of saved reports.`,
  },
  {
    path: "/saved",
    shortTitle: "Saved reports",
    fullTitle: `Saved reports - ${BRAND.name}`,
    description: `Your saved ${BRAND.name} website reports. Review past results or delete them.`,
  },
];

export const NOT_FOUND_META: PageMeta = {
  path: "/404",
  shortTitle: "Page not found",
  fullTitle: `Page not found - ${BRAND.name}`,
  description: `The page you asked for does not exist on ${BRAND.name}.`,
};

export function metaForPath(path: string): PageMeta {
  return PAGE_META.find((meta) => meta.path === path) ?? NOT_FOUND_META;
}

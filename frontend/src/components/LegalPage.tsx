// NOTE: the legal pages built on this layout are plain language drafts written
// from the product's actual behavior. They must be reviewed by a qualified
// lawyer in the operator's jurisdiction before launch.

import type { ReactNode } from "react";
import { BRAND } from "../config/brand";
import Breadcrumbs from "./Breadcrumbs";
import Container from "./Container";
import { useDocumentHead } from "../lib/head";

interface LegalPageProps {
  title: string;
  metaDescription: string;
  path: string;
  updated: string;
  children: ReactNode;
}

export function LegalSection({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id}>
      <h2 id={id} className="font-serif text-xl font-semibold">
        {title}
      </h2>
      <div className="mt-2 space-y-3 text-muted">{children}</div>
    </section>
  );
}

export default function LegalPage({
  title,
  metaDescription,
  path,
  updated,
  children,
}: LegalPageProps) {
  useDocumentHead(`${title} - ${BRAND.name}`, metaDescription, path);
  return (
    <Container className="py-10">
      <Breadcrumbs items={[{ label: "Home", href: "/" }, { label: title }]} />
      <h1 className="mt-2 font-serif text-3xl font-semibold">{title}</h1>
      <p className="mt-1 text-sm text-muted">Last updated: {updated}</p>
      <div className="mt-8 space-y-8">{children}</div>
    </Container>
  );
}

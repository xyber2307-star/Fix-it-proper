import { useEffect } from "react";

export function useDocumentHead(title: string, description: string, path: string) {
  useEffect(() => {
    document.title = title;
    let meta = document.querySelector('meta[name="description"]');
    if (meta === null) {
      meta = document.createElement("meta");
      meta.setAttribute("name", "description");
      document.head.appendChild(meta);
    }
    meta.setAttribute("content", description);
    let link = document.querySelector('link[rel="canonical"]');
    if (link === null) {
      link = document.createElement("link");
      link.setAttribute("rel", "canonical");
      document.head.appendChild(link);
    }
    link.setAttribute("href", `${window.location.origin}${path}`);
  }, [title, description, path]);
}

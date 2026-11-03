import { PassThrough } from "node:stream";
import { renderToPipeableStream } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import Site from "./Site";

export { NOT_FOUND_META, PAGE_META } from "./lib/pages";

export function render(url: string): Promise<string> {
  return new Promise((resolve, reject) => {
    let html = "";
    const { pipe } = renderToPipeableStream(
      <MemoryRouter initialEntries={[url]}>
        <AuthProvider>
          <Site />
        </AuthProvider>
      </MemoryRouter>,
      {
        onShellError: (error: unknown) => reject(error),
        onError: (error: unknown) => console.error("prerender stream error", error),
        onAllReady() {
          const stream = new PassThrough();
          stream.on("data", (chunk: Buffer) => {
            html += chunk.toString();
          });
          stream.on("end", () => resolve(html));
          stream.on("error", reject);
          pipe(stream);
        },
      },
    );
  });
}

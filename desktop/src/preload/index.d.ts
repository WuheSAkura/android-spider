export {};

declare global {
  interface Window {
    desktopApi: {
      request: (request: { method: string; path: string; body?: unknown }) => Promise<{
        ok: boolean;
        status: number;
        data: unknown;
        error: string;
      }>;
      getBaseUrl: () => Promise<string>;
      openPath: (targetPath: string) => Promise<string>;
      openExternal: (targetUrl: string) => Promise<void>;
      showError: (title: string, content: string) => Promise<void>;
    };
  }
}

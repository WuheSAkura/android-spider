import { contextBridge, ipcRenderer } from "electron";

type ServiceRequest = {
  method: string;
  path: string;
  body?: unknown;
};

const desktopApi = {
  request: (request: ServiceRequest) => ipcRenderer.invoke("service:request", request),
  getBaseUrl: (): Promise<string> => ipcRenderer.invoke("service:getBaseUrl"),
  openPath: (targetPath: string): Promise<string> => ipcRenderer.invoke("system:openPath", targetPath),
  showError: (title: string, content: string): Promise<void> =>
    ipcRenderer.invoke("system:showError", title, content),
};

contextBridge.exposeInMainWorld("desktopApi", desktopApi);

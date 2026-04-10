"use strict";
const electron = require("electron");
const desktopApi = {
  request: (request) => electron.ipcRenderer.invoke("service:request", request),
  getBaseUrl: () => electron.ipcRenderer.invoke("service:getBaseUrl"),
  openPath: (targetPath) => electron.ipcRenderer.invoke("system:openPath", targetPath),
  openExternal: (targetUrl) => electron.ipcRenderer.invoke("system:openExternal", targetUrl),
  showError: (title, content) => electron.ipcRenderer.invoke("system:showError", title, content)
};
electron.contextBridge.exposeInMainWorld("desktopApi", desktopApi);

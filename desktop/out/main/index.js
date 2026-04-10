"use strict";
const electron = require("electron");
const node_child_process = require("node:child_process");
const node_fs = require("node:fs");
const node_path = require("node:path");
const SERVICE_PORT = 8765;
const SERVICE_BASE_URL = `http://127.0.0.1:${SERVICE_PORT}`;
let mainWindow = null;
let serviceProcess = null;
function createWindow() {
  const window = new electron.BrowserWindow({
    width: 1420,
    height: 920,
    minWidth: 1200,
    minHeight: 780,
    backgroundColor: "#f4efe7",
    autoHideMenuBar: true,
    webPreferences: {
      preload: node_path.join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });
  if (process.env.ELECTRON_RENDERER_URL) {
    void window.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    void window.loadFile(node_path.join(__dirname, "../renderer/index.html"));
  }
  return window;
}
function getProjectRoot() {
  return node_path.resolve(process.cwd(), "..");
}
function resolvePythonCommand() {
  const projectRoot = getProjectRoot();
  const venvPython = node_path.resolve(projectRoot, ".venv", "Scripts", "python.exe");
  if (node_fs.existsSync(venvPython)) {
    return { command: venvPython, args: [] };
  }
  return { command: "python", args: [] };
}
function appendServiceOutput(current, chunk) {
  const maxLength = 4e3;
  const next = `${current}${chunk}`;
  if (next.length <= maxLength) {
    return next;
  }
  return next.slice(-maxLength);
}
function getRecentServiceOutput(output) {
  const lines = output.split(/\r?\n/).map((line) => line.trimEnd()).filter((line) => line.length > 0);
  return lines.slice(-12).join("\n");
}
function buildServiceExitError(exitCode, signal, output) {
  const exitReason = signal === null ? `退出码 ${exitCode ?? "未知"}` : `信号 ${signal}`;
  const recentOutput = getRecentServiceOutput(output);
  if (!recentOutput) {
    return new Error(`本地 Python 服务启动失败（${exitReason}）。`);
  }
  return new Error(`本地 Python 服务启动失败（${exitReason}）。

${recentOutput}`);
}
async function waitForServiceReady(startedProcess, startupState) {
  const deadline = Date.now() + 15e3;
  while (Date.now() < deadline) {
    if (startupState.failure !== null) {
      throw startupState.failure;
    }
    if (serviceProcess !== startedProcess) {
      throw startupState.failure ?? new Error("本地 Python 服务启动失败。");
    }
    try {
      const response = await fetch(`${SERVICE_BASE_URL}/api/health`);
      if (response.ok) {
        return;
      }
    } catch {
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 400));
  }
  const recentOutput = getRecentServiceOutput(startupState.output);
  if (!recentOutput) {
    throw new Error("本地 Python 服务启动超时。");
  }
  throw new Error(`本地 Python 服务启动超时。

最近输出：
${recentOutput}`);
}
async function ensurePythonService() {
  if (serviceProcess !== null) {
    return;
  }
  const projectRoot = getProjectRoot();
  const pythonCommand = resolvePythonCommand();
  const args = [
    ...pythonCommand.args,
    node_path.resolve(projectRoot, "main.py"),
    "serve",
    "--host",
    "127.0.0.1",
    "--port",
    String(SERVICE_PORT)
  ];
  const startedProcess = node_child_process.spawn(pythonCommand.command, args, {
    cwd: projectRoot,
    stdio: "pipe"
  });
  const startupState = {
    failure: null,
    output: ""
  };
  serviceProcess = startedProcess;
  startedProcess.stdout.on("data", (chunk) => {
    startupState.output = appendServiceOutput(startupState.output, String(chunk));
    process.stdout.write(`[python] ${String(chunk)}`);
  });
  startedProcess.stderr.on("data", (chunk) => {
    startupState.output = appendServiceOutput(startupState.output, String(chunk));
    process.stderr.write(`[python] ${String(chunk)}`);
  });
  startedProcess.on("error", (error) => {
    startupState.failure = new Error(`启动 Python 进程失败：${error.message}`);
    if (serviceProcess === startedProcess) {
      serviceProcess = null;
    }
  });
  startedProcess.on("exit", (code, signal) => {
    startupState.failure ??= buildServiceExitError(code, signal, startupState.output);
    if (serviceProcess === startedProcess) {
      serviceProcess = null;
    }
  });
  await waitForServiceReady(startedProcess, startupState);
}
async function stopPythonService() {
  if (serviceProcess === null) {
    return;
  }
  const currentProcess = serviceProcess;
  serviceProcess = null;
  currentProcess.kill();
}
async function proxyRequest(request) {
  await ensurePythonService();
  const response = await fetch(`${SERVICE_BASE_URL}${request.path}`, {
    method: request.method,
    headers: {
      "Content-Type": "application/json"
    },
    body: request.body === void 0 ? void 0 : JSON.stringify(request.body)
  });
  const rawText = await response.text();
  let data = null;
  if (rawText) {
    try {
      data = JSON.parse(rawText);
    } catch {
      data = rawText;
    }
  }
  let error = "";
  if (!response.ok) {
    if (data !== null && typeof data === "object" && "detail" in data) {
      error = String(data.detail ?? "");
    } else {
      error = rawText || `HTTP ${response.status}`;
    }
  }
  return {
    ok: response.ok,
    status: response.status,
    data,
    error
  };
}
function registerIpcHandlers() {
  electron.ipcMain.handle("service:request", async (_event, request) => proxyRequest(request));
  electron.ipcMain.handle("service:getBaseUrl", () => SERVICE_BASE_URL);
  electron.ipcMain.handle("system:openPath", async (_event, targetPath) => electron.shell.openPath(targetPath));
  electron.ipcMain.handle("system:openExternal", async (_event, targetUrl) => electron.shell.openExternal(targetUrl));
  electron.ipcMain.handle("system:showError", async (_event, title, content) => {
    if (mainWindow !== null) {
      await electron.dialog.showMessageBox(mainWindow, {
        type: "error",
        title,
        message: title,
        detail: content
      });
    }
  });
}
electron.app.whenReady().then(async () => {
  registerIpcHandlers();
  try {
    await ensurePythonService();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await electron.dialog.showMessageBox({
      type: "error",
      title: "服务启动失败",
      message: "本地 Python 服务未能启动",
      detail: message
    });
    electron.app.quit();
    return;
  }
  mainWindow = createWindow();
});
electron.app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    electron.app.quit();
  }
});
electron.app.on("before-quit", () => {
  void stopPythonService();
});

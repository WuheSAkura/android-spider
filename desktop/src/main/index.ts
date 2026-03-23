import { app, BrowserWindow, ipcMain, shell, dialog } from "electron";
import { spawn, ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";

const SERVICE_PORT = 8765;
const SERVICE_BASE_URL = `http://127.0.0.1:${SERVICE_PORT}`;

let mainWindow: BrowserWindow | null = null;
let serviceProcess: ChildProcessWithoutNullStreams | null = null;

type ServiceRequest = {
  method: string;
  path: string;
  body?: unknown;
};

function createWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1420,
    height: 920,
    minWidth: 1200,
    minHeight: 780,
    backgroundColor: "#f4efe7",
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  if (process.env.ELECTRON_RENDERER_URL) {
    void window.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    void window.loadFile(join(__dirname, "../renderer/index.html"));
  }

  return window;
}

function getProjectRoot(): string {
  return resolve(process.cwd(), "..");
}

function resolvePythonCommand(): { command: string; args: string[] } {
  const projectRoot = getProjectRoot();
  const venvPython = resolve(projectRoot, ".venv", "Scripts", "python.exe");
  if (existsSync(venvPython)) {
    return { command: venvPython, args: [] };
  }
  return { command: "python", args: [] };
}

async function waitForServiceReady(): Promise<void> {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${SERVICE_BASE_URL}/api/health`);
      if (response.ok) {
        return;
      }
    } catch {
      // ignore until timeout
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 400));
  }
  throw new Error("本地 Python 服务启动超时。");
}

async function ensurePythonService(): Promise<void> {
  if (serviceProcess !== null) {
    return;
  }

  const projectRoot = getProjectRoot();
  const pythonCommand = resolvePythonCommand();
  const args = [
    ...pythonCommand.args,
    resolve(projectRoot, "main.py"),
    "serve",
    "--host",
    "127.0.0.1",
    "--port",
    String(SERVICE_PORT),
  ];

  serviceProcess = spawn(pythonCommand.command, args, {
    cwd: projectRoot,
    stdio: "pipe",
  });

  serviceProcess.stdout.on("data", (chunk) => {
    process.stdout.write(`[python] ${String(chunk)}`);
  });
  serviceProcess.stderr.on("data", (chunk) => {
    process.stderr.write(`[python] ${String(chunk)}`);
  });
  serviceProcess.on("exit", () => {
    serviceProcess = null;
  });

  await waitForServiceReady();
}

async function stopPythonService(): Promise<void> {
  if (serviceProcess === null) {
    return;
  }
  const currentProcess = serviceProcess;
  serviceProcess = null;
  currentProcess.kill();
}

async function proxyRequest(request: ServiceRequest): Promise<{
  ok: boolean;
  status: number;
  data: unknown;
  error: string;
}> {
  await ensurePythonService();
  const response = await fetch(`${SERVICE_BASE_URL}${request.path}`, {
    method: request.method,
    headers: {
      "Content-Type": "application/json",
    },
    body: request.body === undefined ? undefined : JSON.stringify(request.body),
  });

  const rawText = await response.text();
  let data: unknown = null;
  if (rawText) {
    try {
      data = JSON.parse(rawText) as unknown;
    } catch {
      data = rawText;
    }
  }

  let error = "";
  if (!response.ok) {
    if (data !== null && typeof data === "object" && "detail" in (data as Record<string, unknown>)) {
      error = String((data as Record<string, unknown>).detail ?? "");
    } else {
      error = rawText || `HTTP ${response.status}`;
    }
  }

  return {
    ok: response.ok,
    status: response.status,
    data,
    error,
  };
}

function registerIpcHandlers(): void {
  ipcMain.handle("service:request", async (_event, request: ServiceRequest) => proxyRequest(request));
  ipcMain.handle("service:getBaseUrl", () => SERVICE_BASE_URL);
  ipcMain.handle("system:openPath", async (_event, targetPath: string) => shell.openPath(targetPath));
  ipcMain.handle("system:showError", async (_event, title: string, content: string) => {
    if (mainWindow !== null) {
      await dialog.showMessageBox(mainWindow, {
        type: "error",
        title,
        message: title,
        detail: content,
      });
    }
  });
}

app.whenReady().then(async () => {
  registerIpcHandlers();

  try {
    await ensurePythonService();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await dialog.showMessageBox({
      type: "error",
      title: "服务启动失败",
      message: "本地 Python 服务未能启动",
      detail: message,
    });
    app.quit();
    return;
  }

  mainWindow = createWindow();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  void stopPythonService();
});

import { spawn, type ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import express from 'express';

const PORT = Number(process.env.PORT) || 3000;
const FASTAPI_HOST = '127.0.0.1';
const DEFAULT_FASTAPI_PORT = PORT === 8081 ? 8082 : 8081;
const FASTAPI_PORT = Number(process.env.FASTAPI_PORT) || DEFAULT_FASTAPI_PORT;
const FASTAPI_URL = `http://${FASTAPI_HOST}:${FASTAPI_PORT}`;
const PYDEPS_DIR = '/tmp/pydeps';
const FRONTEND_DIR = path.resolve(process.cwd(), 'frontend');

let pythonProcess: ChildProcess | null = null;
let fastApiReady = false;
let fastApiBootPromise: Promise<void> | null = null;
let lastBootError: string | null = null;

function pythonEnv(): NodeJS.ProcessEnv {
  const existing = process.env.PYTHONPATH ? process.env.PYTHONPATH.split(path.delimiter).filter(Boolean) : [];
  const merged = [process.cwd(), PYDEPS_DIR, ...existing];
  return {
    ...process.env,
    PYTHONPATH: merged.join(path.delimiter),
  };
}

async function isFastApiReady(): Promise<boolean> {
  try {
    const res = await fetch(`${FASTAPI_URL}/api/health`);
    if (!res.ok) return false;
    const data = (await res.json()) as { service?: string };
    return data.service === 'rcyc-guest-concierge-uc3';
  } catch {
    return false;
  }
}

function hasPythonDeps(): Promise<boolean> {
  return new Promise((resolve) => {
    const check = spawn(
      'python3',
      ['-c', 'import fastapi, uvicorn, dotenv, httpx, openpyxl, pydantic'],
      { stdio: 'ignore', env: pythonEnv() },
    );
    check.on('exit', (code) => resolve(code === 0));
    check.on('error', () => resolve(false));
  });
}

function runShell(cmd: string): Promise<number> {
  return new Promise((resolve) => {
    const child = spawn('bash', ['-lc', cmd], {
      cwd: process.cwd(),
      stdio: 'inherit',
      env: pythonEnv(),
    });
    child.on('exit', (code) => resolve(code ?? 1));
    child.on('error', () => resolve(1));
  });
}

async function ensurePythonDeps(): Promise<void> {
  if (await hasPythonDeps()) return;
  console.log('[rcyc-proxy] Installing Python dependencies from requirements.txt...');

  const hasPip = (await runShell('python3 -m pip --version >/dev/null 2>&1')) === 0;
  if (!hasPip) {
    const ensurePipStatus = await runShell('python3 -m ensurepip --upgrade >/dev/null 2>&1');
    if (ensurePipStatus !== 0) {
      const pipStatus = await runShell(
        'curl -sSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py && (python3 /tmp/get-pip.py --no-warn-script-location --break-system-packages || python3 /tmp/get-pip.py --no-warn-script-location --user) && rm -f /tmp/get-pip.py',
      );
      if (pipStatus !== 0) {
        throw new Error('Failed to bootstrap pip for Python backend.');
      }
    }
  }

  fs.mkdirSync(PYDEPS_DIR, { recursive: true });
  const installStatus = await runShell(
    `python3 -m pip install --no-cache-dir --upgrade --target "${PYDEPS_DIR}" -r requirements.txt`,
  );
  if (installStatus !== 0) {
    const fallbackStatus = await runShell(
      'python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt || python3 -m pip install --no-cache-dir -r requirements.txt',
    );
    if (fallbackStatus !== 0) {
      throw new Error('Failed to install Python dependencies from requirements.txt.');
    }
  }
}

async function startFastApiInternal(): Promise<void> {
  if (await isFastApiReady()) {
    fastApiReady = true;
    lastBootError = null;
    console.log(`[rcyc-proxy] FastAPI already listening on ${FASTAPI_URL}`);
    return;
  }

  await ensurePythonDeps();

  console.log('[rcyc-proxy] Starting Python FastAPI server (uvicorn)...');
  let exitedEarly = false;
  let exitDetails = '';

  pythonProcess = spawn(
    'python3',
    ['-m', 'uvicorn', 'backend.app.main:app', '--host', FASTAPI_HOST, '--port', String(FASTAPI_PORT)],
    {
      cwd: process.cwd(),
      stdio: 'inherit',
      env: pythonEnv(),
    },
  );

  pythonProcess.on('exit', (code, signal) => {
    console.log(`[rcyc-proxy] FastAPI process exited (code=${code}, signal=${signal})`);
    exitedEarly = true;
    exitDetails = `code=${code}, signal=${signal}`;
    pythonProcess = null;
    fastApiReady = false;
    fastApiBootPromise = null;
  });

  pythonProcess.on('error', (err) => {
    exitedEarly = true;
    exitDetails = err.message;
    pythonProcess = null;
    fastApiReady = false;
    fastApiBootPromise = null;
  });

  for (let i = 0; i < 180; i++) {
    if (await isFastApiReady()) {
      fastApiReady = true;
      lastBootError = null;
      console.log(`[rcyc-proxy] FastAPI ready on ${FASTAPI_URL}`);
      return;
    }
    if (exitedEarly) {
      throw new Error(`FastAPI exited during startup (${exitDetails}).`);
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`FastAPI server failed to become ready on port ${FASTAPI_PORT}.`);
}

function ensureFastApiRunning(): Promise<void> {
  if (fastApiReady) return Promise.resolve();
  if (!fastApiBootPromise) {
    fastApiBootPromise = startFastApiInternal().catch((err) => {
      lastBootError = err instanceof Error ? err.message : String(err);
      fastApiReady = false;
      fastApiBootPromise = null;
      throw err;
    });
  }
  return fastApiBootPromise;
}

function tryServeFrontendFallback(req: express.Request, res: express.Response): boolean {
  if (req.method !== 'GET' && req.method !== 'HEAD') return false;
  if (!fs.existsSync(FRONTEND_DIR)) return false;

  let targetPath: string | null = null;
  if (req.path === '/') {
    targetPath = path.join(FRONTEND_DIR, 'index.html');
  } else if (req.path === '/styles.css') {
    targetPath = path.join(FRONTEND_DIR, 'styles.css');
  } else if (req.path === '/app.js') {
    targetPath = path.join(FRONTEND_DIR, 'app.js');
  } else if (req.path.startsWith('/static/')) {
    const rel = req.path.slice('/static/'.length);
    const resolved = path.resolve(FRONTEND_DIR, rel);
    if (resolved.startsWith(FRONTEND_DIR + path.sep)) {
      targetPath = resolved;
    }
  }

  if (!targetPath || !fs.existsSync(targetPath) || !fs.statSync(targetPath).isFile()) {
    return false;
  }

  res.sendFile(targetPath);
  return true;
}

function proxyToFastApi(req: express.Request, res: express.Response): void {
  const proxyHeaders: http.OutgoingHttpHeaders = { ...req.headers };
  for (const key of Object.keys(proxyHeaders)) {
    if (key.toLowerCase() === 'x-forwarded-for') {
      delete proxyHeaders[key];
    }
  }
  proxyHeaders.host = `${FASTAPI_HOST}:${FASTAPI_PORT}`;
  if (req.socket.remoteAddress) {
    proxyHeaders['x-forwarded-for'] = req.socket.remoteAddress;
  }

  const proxyReq = http.request(
    {
      hostname: FASTAPI_HOST,
      port: FASTAPI_PORT,
      path: req.originalUrl,
      method: req.method,
      headers: proxyHeaders,
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    },
  );

  proxyReq.on('error', (err) => {
    console.error('[rcyc-proxy] Proxy error:', err.message);
    fastApiReady = false;
    if (!res.headersSent) {
      res.status(502).json({ error: 'FastAPI backend unavailable', detail: err.message });
    }
  });

  req.pipe(proxyReq, { end: true });
}

function shutdown(): void {
  if (pythonProcess && !pythonProcess.killed) {
    pythonProcess.kill('SIGTERM');
  }
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

async function start(): Promise<void> {
  const app = express();

  app.use(async (req, res) => {
    if (!fastApiReady) {
      if (tryServeFrontendFallback(req, res)) {
        return;
      }
      try {
        await ensureFastApiRunning();
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        if (!res.headersSent) {
          res.status(503).json({
            detail: 'Backend service is starting or temporarily unavailable.',
            error: message || lastBootError,
          });
        }
        return;
      }
    }

    proxyToFastApi(req, res);
  });

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`[rcyc-proxy] Listening on http://0.0.0.0:${PORT} (FastAPI upstream: ${FASTAPI_URL})`);
  });

  void ensureFastApiRunning().catch((err) => {
    console.error('[rcyc-proxy] Initial FastAPI startup failed:', err);
  });
}

start().catch((err) => {
  console.error(err);
  process.exit(1);
});

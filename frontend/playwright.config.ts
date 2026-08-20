import { defineConfig, devices } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const bundledChrome = path.join(process.env.LOCALAPPDATA || '', 'ms-playwright', 'chromium-1234', 'chrome-win64', 'chrome.exe')
const edgeCandidates = [
  process.env['PROGRAMFILES(X86)'] ? path.join(process.env['PROGRAMFILES(X86)'], 'Microsoft', 'Edge', 'Application', 'msedge.exe') : '',
  process.env.PROGRAMFILES ? path.join(process.env.PROGRAMFILES, 'Microsoft', 'Edge', 'Application', 'msedge.exe') : '',
]
const edgeExecutable = edgeCandidates.find((candidate) => candidate && fs.existsSync(candidate))

const projects = [
  { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
]
if (edgeExecutable) {
  projects.push({
    name: 'edge',
    use: { ...devices['Desktop Chrome'], launchOptions: { executablePath: edgeExecutable } },
  })
}

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  workers: 2,
  fullyParallel: true,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    ...(fs.existsSync(bundledChrome) ? { launchOptions: { executablePath: bundledChrome } } : {}),
  },
  projects,
  webServer: {
    command: 'npm.cmd run preview -- --host 127.0.0.1 --port 4173',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
})

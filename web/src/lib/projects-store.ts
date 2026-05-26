import { config } from './config';
import { getStoredToken, handleAuthFailure, normalizeAuthError } from './auth';
import { toast } from 'sonner';

export type ProjectStatus = 'draft' | 'completed' | 'exported' | 'failed';
export type ProjectStep = 'upload' | 'subtitle' | 'config' | 'generate';
export type InferenceMode = 'fast' | 'deep' | 'frame';

export type ScriptItem = {
  id: string;
  startTime: string;
  endTime: string;
  originalSubtitle: string;
  narration: string;
  audioUrl?: string;
  audioPath?: string;
  audioStatus?: 'pending' | 'ready' | 'generating' | 'error';
  ost?: number;
  raw?: Record<string, unknown>;
};

export type Project = {
  id: string;
  name: string;
  status: ProjectStatus;
  thumbnailUrl?: string;
  videoUrl?: string;
  videoFileName?: string;
  videoDurationSec?: number;
  createdAt: string;
  updatedAt: string;
  currentStep: ProjectStep;
  inferenceMode?: InferenceMode;
  uploadedVideoPath?: string;
  uploadedSubtitlePath?: string;
  config?: Record<string, unknown>;
  scriptItems?: ScriptItem[];
};

export type Activity = { id: string; kind: 'publish' | 'comment' | 'update'; title: string; at: string };

const STORAGE_KEY = 'aivideo_projects_cache';
const ACTIVITY_KEY = 'aivideo_activities';
const pendingFlushTimers = new Map<string, number>();
const pendingPatches = new Map<string, Partial<Project>>();
let lastPatchErrorToastAt = 0;

function withBase(path: string) {
  const base = config.API_BASE_URL || '';
  return base ? `${base.replace(/\/$/, '')}${path}` : path;
}

function authHeaders(extra?: HeadersInit): HeadersInit {
  const token = getStoredToken();
  return { ...(token ? { Authorization: `Bearer ${token}` } : {}), 'Content-Type': 'application/json', ...(extra || {}) };
}

async function parseResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const body = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof body === 'string' ? body : body?.detail || body?.message || '';
    const message = detail ? `${response.status} ${response.statusText}: ${detail}` : `HTTP ${response.status}`;
    const error = new Error(message);
    if (response.status === 401) {
      handleAuthFailure(error);
      throw normalizeAuthError(error);
    }
    throw error;
  }
  return body as T;
}

function notifyProjectSyncError(error: unknown) {
  const message = error instanceof Error ? error.message : '未知错误';
  const now = Date.now();
  if (now - lastPatchErrorToastAt > 3000) {
    toast.error(`项目同步失败：${message}`);
    lastPatchErrorToastAt = now;
  }
  window.dispatchEvent(new CustomEvent('aivideo:project-sync-error', { detail: { message } }));
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(withBase(path), { ...init, headers: authHeaders(init?.headers) });
  return parseResponse<T>(response);
}

function readCache(): Project[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as Project[]) : [];
  } catch {
    return [];
  }
}

function writeCache(items: Project[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    window.dispatchEvent(new Event('aivideo:projects'));
  } catch {}
}

function sortItems(items: Project[]): Project[] {
  return [...items].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

function mergeProject(item: Project) {
  const items = readCache();
  const idx = items.findIndex((p) => p.id === item.id);
  if (idx === -1) items.unshift(item); else items[idx] = item;
  writeCache(sortItems(items));
}

function schedulePatchFlush(id: string, patch: Partial<Project>) {
  pendingPatches.set(id, { ...(pendingPatches.get(id) || {}), ...patch });
  const existing = pendingFlushTimers.get(id);
  if (existing) window.clearTimeout(existing);
  const timer = window.setTimeout(async () => {
    pendingFlushTimers.delete(id);
    const nextPatch = pendingPatches.get(id) || {};
    pendingPatches.delete(id);
    try {
      const payload = await requestJson<{ item: Project }>(`/api/v1/projects/${id}`, { method: 'PATCH', body: JSON.stringify(nextPatch) });
      if (payload?.item) mergeProject(payload.item);
    } catch (error) {
      console.error('sync project patch failed', error);
      notifyProjectSyncError(error);
    }
  }, 500);
  pendingFlushTimers.set(id, timer);
}

export async function hydrateProjects(): Promise<Project[]> {
  if (!getStoredToken()) {
    writeCache([]);
    return [];
  }
  const payload = await requestJson<{ items: Project[] }>('/api/v1/projects', { method: 'GET' });
  const items = sortItems(Array.isArray(payload?.items) ? payload.items : []);
  writeCache(items);
  return items;
}

export function listProjects(): Project[] { return sortItems(readCache()); }
export function getProject(id: string): Project | undefined { return readCache().find((p) => p.id === id); }

export async function createProject(name: string, inferenceMode: InferenceMode = 'fast'): Promise<Project> {
  const payload = await requestJson<{ item: Project }>('/api/v1/projects', { method: 'POST', body: JSON.stringify({ name, inferenceMode }) });
  if (!payload?.item) throw new Error('创建项目失败');
  mergeProject(payload.item);
  return payload.item;
}

export function updateProject(id: string, patch: Partial<Project>): Project | undefined {
  const items = readCache();
  const idx = items.findIndex((p) => p.id === id);
  if (idx === -1) return undefined;
  const next = { ...items[idx], ...patch, updatedAt: new Date().toISOString() } as Project;
  items[idx] = next;
  writeCache(sortItems(items));
  schedulePatchFlush(id, patch);
  return next;
}

export async function deleteProject(id: string): Promise<void> {
  writeCache(readCache().filter((p) => p.id !== id));
  await requestJson<{ success: boolean }>(`/api/v1/projects/${id}`, { method: 'DELETE' });
}

const SAMPLE_ACTIVITIES: Activity[] = [
  { id: 'a1', kind: 'publish', title: '项目“寂静回声”成功发布', at: '2小时前' },
  { id: 'a2', kind: 'comment', title: '「往昔私语」收到新评论', at: '1天前' },
  { id: 'a3', kind: 'update', title: '项目「明日之影」已更新', at: '3天前' },
];

export function listActivities(): Activity[] {
  try {
    const raw = localStorage.getItem(ACTIVITY_KEY);
    if (raw) return JSON.parse(raw) as Activity[];
  } catch {}
  return SAMPLE_ACTIVITIES;
}

export function seedSampleProjectsIfEmpty() {}

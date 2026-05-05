import { createClient } from '@metagptx/web-sdk';
import { config } from './config';
import { getStoredToken, handleAuthFailure, normalizeAuthError, type AuthUser } from './auth';

export const client = createClient();

export type SubtitleLine = {
  id: number;
  start: string;
  end: string;
  text: string;
};

export type JobAcceptedResponse = {
  task_id: string;
  job_type: string;
  status: string;
  progress: number;
  task_dir: string;
};

export type JobStatusResponse = {
  task_id: string;
  job_type: string;
  status: string;
  state: number;
  progress: number;
  message?: string;
  error?: string;
  task_dir?: string;
  videos?: string[];
  combined_videos?: string[];
  is_running?: boolean;
  payload?: Record<string, any>;
};

export type UploadResponse = {
  path: string;
  url: string;
  filename: string;
  size: number;
  kind: 'video' | 'subtitle';
};

export type CropVideoRequest = {
  path: string;
  start_sec: number;
  end_sec: number;
};

export type HighlightScriptRequest = {
  project_id?: string;
  video_path: string;
  mode?: string;
  target_duration_seconds?: number;
  movie_title?: string;
  highlight_profile?: string;
  subtitle_path?: string;
  narration_text?: string;
  narration_audio_path?: string;
  prefer_raw_audio?: boolean;
  visual_mode?: string;
  regenerate_subtitle?: boolean;
  subtitle_backend?: string;
};

export type ScriptBinding = {
  script_path: string;
  video_path: string;
  subtitle_path?: string;
  label?: string;
};

export type TaskLogItem = {
  task_id: string;
  status: string;
  message?: string;
  updated_at?: string;
};

export type WorkspaceInfoResponse = {
  project_root: string;
  workspace_root: string;
  config_file: string;
  project_version: string;
  layout: Record<string, string>;
  task_root: string;
};

export type RuntimeConfigResponse = {
  API_BASE_URL: string;
  project_name: string;
  project_version: string;
};

export type ProjectArtifact = {
  id: string;
  owner_email?: string | null;
  project_id?: string | null;
  task_id?: string | null;
  artifact_type: string;
  label: string;
  path: string;
  created_at: string;
  updated_at: string;
  exists: boolean;
  metadata: Record<string, any>;
};

export type ProjectResultsOverview = {
  project_id: string;
  latest_job?: JobHistoryItem | null;
  artifacts: ProjectArtifact[];
  script_items: any[];
  highlights: any[];
  highlight_narration_segments: any[];
  global_summary: Record<string, any>;
  audit: Record<string, any>;
};

export type SubtitleJobRequest = {
  project_id?: string;
  video_path: string;
  backend?: string;
  model?: string;
};

export type MovieStoryRequest = {
  project_id?: string;
  video_path: string;
  subtitle_path?: string;
  video_theme?: string;
  narration_style?: string;
  generation_mode?: string;
  visual_mode?: string;
  target_duration_minutes?: number;
  highlight_only?: boolean;
  highlight_selectivity?: 'loose' | 'balanced' | 'strict' | string;
  narrative_strategy?: string;
  accuracy_priority?: string;
  temperature?: number;
  asr_backend?: string;
};

export type VideoGenerationParams = {
  project_id?: string;
  video_clip_json?: any[];
  video_clip_json_path?: string;
  video_origin_path: string;
  video_aspect: string;
  voice_name: string;
  voice_rate: number;
  voice_pitch?: number;
  tts_engine?: string;
  subtitle_enabled: boolean;
  font_name: string;
  font_size: number;
  text_fore_color?: string;
  stroke_color?: string;
  stroke_width?: number;
  subtitle_position?: string;
  custom_position?: number;
  bgm_name?: string;
  bgm_type?: string;
  n_threads?: number;
};

function withBase(path: string) {
  const base = config.API_BASE_URL || '';
  if (!base) return path;
  return `${base.replace(/\/$/, '')}${path}`;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const body = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    const message = typeof body === 'string' ? body : body?.detail || body?.message || `HTTP ${response.status}`;
    const error = new Error(message);
    if (response.status === 401) {
      handleAuthFailure(error);
      throw normalizeAuthError(error);
    }
    throw error;
  }
  return body as T;
}

function buildHeaders(init?: RequestInit): HeadersInit {
  const token = getStoredToken();
  return {
    ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(init?.headers || {}),
  };
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(withBase(path), {
      ...init,
      headers: buildHeaders(init),
    });
  } catch (err) {
    if (err instanceof TypeError) {
      throw new Error('无法连接到后端服务（端口 18000）。请先启动后端：python local_api.py');
    }
    throw err;
  }
  return parseResponse<T>(response);
}

export type BackendUserInfo = {
  name: string;
  email: string;
  created_at: string;
};

export type BackendAuthResponse = {
  token: string;
  user: BackendUserInfo;
};

export type AuthStatusResponse = {
  has_users: boolean;
  user_count: number;
  bootstrap_enabled: boolean;
  bootstrap_email?: string | null;
  bootstrap_password?: string | null;
};

export async function fetchAuthStatus(): Promise<AuthStatusResponse> {
  return requestJson<AuthStatusResponse>('/api/v1/auth/status', { method: 'GET' });
}


export type ForgotPasswordResponse = {
  success: boolean;
  message: string;
  reset_token?: string | null;
  reset_url?: string | null;
  expires_at?: string | null;
};

export type GenericSuccessResponse = {
  success: boolean;
  message: string;
};

export function mapBackendUser(user: BackendUserInfo): AuthUser {
  return { email: user.email, username: user.name, name: user.name, verified: true, created_at: user.created_at };
}

export async function loginWithPassword(email: string, password: string): Promise<BackendAuthResponse> {
  return requestJson<BackendAuthResponse>('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
}

export async function registerWithPassword(name: string, email: string, password: string): Promise<BackendAuthResponse> {
  return requestJson<BackendAuthResponse>('/api/v1/auth/register', { method: 'POST', body: JSON.stringify({ name, email, password }) });
}

export async function requestPasswordReset(email: string): Promise<ForgotPasswordResponse> {
  return requestJson<ForgotPasswordResponse>('/api/v1/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email }) });
}

export async function resetPassword(token: string, password: string): Promise<GenericSuccessResponse> {
  return requestJson<GenericSuccessResponse>('/api/v1/auth/reset-password', { method: 'POST', body: JSON.stringify({ token, password }) });
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<GenericSuccessResponse> {
  return requestJson<GenericSuccessResponse>('/api/v1/auth/change-password', { method: 'POST', body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) });
}

export async function fetchMe(): Promise<{ user: BackendUserInfo }> {
  return requestJson<{ user: BackendUserInfo }>('/api/v1/auth/me', { method: 'GET' });
}

export async function uploadVideo(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file);
  return requestJson<UploadResponse>('/api/v1/uploads/video', { method: 'POST', body: form });
}

export async function uploadSubtitle(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file);
  return requestJson<UploadResponse>('/api/v1/uploads/subtitle', { method: 'POST', body: form });
}

export async function cropUploadedVideo(request: CropVideoRequest): Promise<UploadResponse> {
  return requestJson<UploadResponse>('/api/v1/uploads/video/crop', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function readSubtitleLines(path: string): Promise<SubtitleLine[]> {
  const url = `/api/v1/uploads/subtitle-content?path=${encodeURIComponent(path)}`;
  return requestJson<SubtitleLine[]>(url, { method: 'GET' });
}

export async function createMovieStoryJob(request: MovieStoryRequest): Promise<JobAcceptedResponse> {
  return requestJson<JobAcceptedResponse>('/api/v1/jobs/movie-story-script', {
    method: 'POST',
    body: JSON.stringify({
      project_id: request.project_id || '',
      request: {
        video_path: request.video_path,
        subtitle_path: request.subtitle_path || '',
        video_theme: request.video_theme || '',
        narration_style: request.narration_style || 'general',
        generation_mode: request.generation_mode || 'balanced',
        visual_mode: request.visual_mode || 'auto',
        target_duration_minutes: request.target_duration_minutes || 8,
        highlight_only: Boolean(request.highlight_only),
        highlight_selectivity: request.highlight_selectivity || 'balanced',
        narrative_strategy: request.narrative_strategy || 'chronological',
        accuracy_priority: request.accuracy_priority || 'high',
        temperature: request.temperature ?? 0.7,
        ...(request.asr_backend ? { asr_backend: request.asr_backend } : {}),
        cache_mode: 'clear_and_regenerate',
      },
    }),
  });
}

export async function createSubtitleJob(
  request: SubtitleJobRequest
): Promise<JobAcceptedResponse> {
  return requestJson<JobAcceptedResponse>('/api/v1/jobs/subtitle', {
    method: 'POST',
    body: JSON.stringify({
      project_id: request.project_id || '',
      request: {
        video_path: request.video_path,
        backend: request.backend || '',
        model: request.model || '',
      },
    }),
  });
}

export function extractSubtitleArtifact(snapshot: JobStatusResponse): string {
  const payload = snapshot.payload || {};
  const result = (payload.result || {}) as Record<string, any>;
  return String(result.subtitle_path || payload.subtitle_path || '') || '';
}

export async function createVideoJob(params: VideoGenerationParams): Promise<JobAcceptedResponse> {
  return requestJson<JobAcceptedResponse>('/api/v1/jobs/video', {
    method: 'POST',
    body: JSON.stringify({ params, project_id: params.project_id || '' }),
  });
}

export async function createHighlightScriptJob(
  request: HighlightScriptRequest
): Promise<JobAcceptedResponse> {
  return requestJson<JobAcceptedResponse>('/api/v1/jobs/highlight-script', {
    method: 'POST',
    body: JSON.stringify({
      project_id: request.project_id || '',
      request: {
        video_path: request.video_path,
        mode: request.mode || 'highlight_recut',
        target_duration_seconds: request.target_duration_seconds ?? 480,
        movie_title: request.movie_title || '',
        highlight_profile: request.highlight_profile || 'auto',
        subtitle_path: request.subtitle_path || '',
        narration_text: request.narration_text || '',
        narration_audio_path: request.narration_audio_path || '',
        prefer_raw_audio: request.prefer_raw_audio ?? true,
        visual_mode: request.visual_mode || 'auto',
        regenerate_subtitle: request.regenerate_subtitle ?? false,
        subtitle_backend: request.subtitle_backend || '',
      },
    }),
  });
}

export async function getScriptBindings(): Promise<ScriptBinding[]> {
  const payload = await requestJson<{ bindings: ScriptBinding[] }>(
    '/api/v1/workbench/state/script-bindings',
    { method: 'GET' }
  );
  return Array.isArray(payload?.bindings) ? payload.bindings : [];
}

export async function saveScriptBindings(bindings: ScriptBinding[]): Promise<string> {
  const payload = await requestJson<{ message: string }>(
    '/api/v1/workbench/state/script-bindings',
    { method: 'PUT', body: JSON.stringify({ bindings }) }
  );
  return payload?.message || '';
}

export async function getTaskLogs(): Promise<TaskLogItem[]> {
  const payload = await requestJson<{ items: TaskLogItem[] }>(
    '/api/v1/workbench/task-logs',
    { method: 'GET' }
  );
  return Array.isArray(payload?.items) ? payload.items : [];
}

export async function postRepairAction(title: string): Promise<string> {
  const payload = await requestJson<{ message: string }>(
    '/api/v1/workbench/actions/repair',
    { method: 'POST', body: JSON.stringify({ title }) }
  );
  return payload?.message || '';
}

export async function postTimelineFix(trackName: string): Promise<string> {
  const payload = await requestJson<{ message: string }>(
    '/api/v1/workbench/actions/timeline-fix',
    { method: 'POST', body: JSON.stringify({ track_name: trackName }) }
  );
  return payload?.message || '';
}

export async function getWorkspaceInfo(): Promise<WorkspaceInfoResponse> {
  return requestJson<WorkspaceInfoResponse>('/api/v1/system/workspace', { method: 'GET' });
}

export async function getRuntimeConfig(): Promise<RuntimeConfigResponse> {
  return requestJson<RuntimeConfigResponse>('/api/v1/system/config', { method: 'GET' });
}


export async function fetchProjectResultsOverview(projectId: string): Promise<ProjectResultsOverview> {
  return requestJson<ProjectResultsOverview>(`/api/v1/projects/${projectId}/results/overview`, { method: 'GET' });
}

export async function fetchProjectArtifacts(projectId: string): Promise<{ items: ProjectArtifact[] }> {
  return requestJson<{ items: ProjectArtifact[] }>(`/api/v1/projects/${projectId}/artifacts`, { method: 'GET' });
}

export function resolveWorkspaceFileUrl(path: string): string {
  if (!path) return '';
  return withBase(`/api/v1/projects/workspace-file?path=${encodeURIComponent(path)}`);
}

export type TtsVoice = {
  id: string;
  display_name: string;
  locale: string;
  gender: string;
  engine: string;
  tier: 'basic' | 'premium';
};

export type TtsVoicesResponse = {
  voices: TtsVoice[];
  default_engine: string;
};

export type TtsSynthesizeRequest = {
  text: string;
  voice_name: string;
  voice_rate?: number;
  voice_pitch?: number;
  tts_engine?: string;
};

export type TtsSynthesizeResponse = {
  path: string;
  url: string;
  filename: string;
  size: number;
};

export async function listTtsVoices(locales = 'zh-CN,en-US'): Promise<TtsVoicesResponse> {
  const url = `/api/v1/tts/voices?locales=${encodeURIComponent(locales)}`;
  return requestJson<TtsVoicesResponse>(url, { method: 'GET' });
}

export async function synthesizeTts(
  request: TtsSynthesizeRequest
): Promise<TtsSynthesizeResponse> {
  return requestJson<TtsSynthesizeResponse>('/api/v1/tts/synthesize', {
    method: 'POST',
    body: JSON.stringify({
      text: request.text,
      voice_name: request.voice_name,
      voice_rate: request.voice_rate ?? 1.0,
      voice_pitch: request.voice_pitch ?? 1.0,
      tts_engine: request.tts_engine || '',
    }),
  });
}

export function resolveAssetUrl(url: string, projectId = "", artifactId = ""): string {
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  if (/^\/uploads\//i.test(url)) {
    const base = config.API_BASE_URL || '';
    return base ? `${base.replace(/\/$/, '')}${url}` : url;
  }
  if (/^[A-Za-z]:[\\/]/.test(url) || url.startsWith('/')) {
    return resolveWorkspaceFileUrl(url, projectId, artifactId);
  }
  const base = config.API_BASE_URL || '';
  return base ? `${base.replace(/\/$/, '')}/${url.replace(/^\/+/, '')}` : url;
}

export async function getJobStatus(taskId: string): Promise<JobStatusResponse> {
  return requestJson<JobStatusResponse>(`/api/v1/jobs/${taskId}`, { method: 'GET' });
}

export type JobHistoryItem = {
  task_id: string;
  project_id?: string | null;
  job_type: string;
  status: string;
  progress: number;
  message: string;
  error: string;
  task_dir: string;
  created_at: string;
  updated_at: string;
};

export type JobHistoryResponse = {
  items: JobHistoryItem[];
};

export async function listJobHistory(): Promise<JobHistoryResponse> {
  return requestJson<JobHistoryResponse>('/api/v1/auth/jobs', { method: 'GET' });
}

export async function waitForJob(
  taskId: string,
  options?: {
    intervalMs?: number;
    timeoutMs?: number;
    onTick?: (snapshot: JobStatusResponse) => void;
  }
): Promise<JobStatusResponse> {
  const intervalMs = options?.intervalMs ?? 2000;
  const timeoutMs = options?.timeoutMs ?? 1000 * 60 * 30;
  const startedAt = Date.now();

  while (true) {
    const snapshot = await getJobStatus(taskId);
    options?.onTick?.(snapshot);

    if (snapshot.status === 'complete' || snapshot.state === 1) {
      return snapshot;
    }
    if (snapshot.status === 'failed' || snapshot.state === -1) {
      throw new Error(snapshot.error || snapshot.message || '任务执行失败');
    }
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error('任务等待超时');
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

export function extractMovieStoryArtifacts(snapshot: JobStatusResponse): {
  subtitlePath: string;
  scriptPath: string;
  scriptItems: any[];
} {
  const payload = snapshot.payload || {};
  const result = (payload.result || {}) as Record<string, any>;

  return {
    subtitlePath:
      String(
        result.subtitle_path ||
          result.subtitle_file ||
          payload.subtitle_path ||
          ''
      ) || '',
    scriptPath:
      String(
        result.video_clip_json_path ||
          result.script_path ||
          result.output_script_path ||
          payload.video_clip_json_path ||
          ''
      ) || '',
    scriptItems:
      (Array.isArray(result.video_clip_json) && result.video_clip_json) ||
      (Array.isArray(result.script_items) && result.script_items) ||
      (Array.isArray(result.script) && result.script) ||
      (Array.isArray(payload.video_clip_json) && payload.video_clip_json) ||
      [],
  };
}

export function extractVideoOutputs(snapshot: JobStatusResponse): string[] {
  const payload = snapshot.payload || {};
  const result = (payload.result || {}) as Record<string, any>;
  const combined = Array.isArray(snapshot.combined_videos) ? snapshot.combined_videos : [];
  const videos = Array.isArray(snapshot.videos) ? snapshot.videos : [];
  const resultVideos = Array.isArray(result.videos) ? result.videos : [];
  const outputPath = result.output_video_path ? [String(result.output_video_path)] : [];
  return [...combined, ...videos, ...resultVideos, ...outputPath].filter(Boolean);
}

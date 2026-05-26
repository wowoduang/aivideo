import { createClient } from '@metagptx/web-sdk';
import { config } from './config';
import { getStoredToken, handleAuthFailure, normalizeAuthError, type AuthUser } from './auth';

const normalizeMovieStoryStrategy = (value?: string | null): 'two_round' | 'two_round_visual' => {
  const normalized = String(value || 'two_round').trim();
  if (normalized === 'two_round_visual') {
    return 'two_round_visual';
  }
  return 'two_round';
};



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
  raw_url?: string;
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


export type SystemHealthResponse = {
  project_version: string;
  environment: string;
  workspace: Record<string, any>;
  runtime: Record<string, any>;
  asr: Record<string, any>;
  tts: Record<string, any>;
  jobs?: JobWorkerStatusResponse;
};

export type UsageSummaryResponse = {
  summary: Array<{
    event_type: string;
    provider: string;
    unit_name: string;
    event_count: number;
    total_units: number;
    total_cost: number;
  }>;
  recent: Array<Record<string, any>>;
  pricing?: {
    configured: boolean;
    rule_count: number;
    rules?: Array<Record<string, any>>;
  };
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
  understanding_script: Record<string, any>;
  segment_understandings: Array<Record<string, any>>;
  audit: Record<string, any>;
};

export type NarrationQualityReport = {
  version: string;
  created_at: string;
  summary: {
    overall_score: number;
    factuality_score: number;
    timeline_score: number;
    humanlike_score: number;
    tts_alignment_score: number;
    completeness_score: number;
    segment_count: number;
    evidence_count: number;
    blocking_issues?: string[];
    [key: string]: any;
  };
  unsupported_claims: Array<Record<string, any>>;
  segments: Array<Record<string, any>>;
  next_actions: string[];
};

export type NarrationWorkbench = {
  project_id: string;
  script_segments: Array<Record<string, any>>;
  evidence_pack: Array<Record<string, any>>;
  quality_report: NarrationQualityReport;
  timeline_blocks: Array<Record<string, any>>;
  latest_artifacts: Record<string, any>;
};

export type NarrationHumanizeResponse = {
  persona: string;
  persona_label: string;
  intensity: number;
  script_items: Array<Record<string, any>>;
  changes: Array<Record<string, any>>;
  quality_report: NarrationQualityReport;
  artifact?: ProjectArtifact | null;
};

export type NarrationScriptVersionResponse = {
  artifact: ProjectArtifact;
  quality_report: NarrationQualityReport;
};

export type HighlightSelectionItem = {
  id: string;
  source_id?: string;
  index: number;
  rank: number;
  selected: boolean;
  locked?: boolean;
  video_start: number;
  video_end: number;
  duration: number;
  title: string;
  summary?: string;
  reason?: string;
  selection_reasons?: string[];
  scores?: Record<string, any>;
  character_trace?: Record<string, any>;
  source_type?: string;
  raw?: Record<string, any>;
};

export type HighlightSelectionResponse = {
  project_id: string;
  items: HighlightSelectionItem[];
  selected_count: number;
  total_count: number;
  selected_duration_sec: number;
  latest_artifact?: ProjectArtifact | null;
  source: 'generated' | 'saved' | string;
};

export type HighlightSelectionSaveResponse = {
  project_id: string;
  artifact: ProjectArtifact;
  selection: HighlightSelectionResponse;
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
  movie_story_mode?: 'two_round' | 'two_round_visual';
  movie_story_enable_visual_evidence?: boolean;
  movie_story_strategy?: 'two_round' | 'two_round_visual' | string;
  visual_mode?: string;
  target_duration_minutes?: number;
  highlight_only?: boolean;
  highlight_selectivity?: 'loose' | 'balanced' | 'strict' | string;
  narrative_strategy?: string;
  accuracy_priority?: string;
  temperature?: number;
  asr_backend?: string;
  skip_llm?: boolean;
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

function appendAccessToken(url: string): string {
  const token = getStoredToken();
  if (!token || !/^\/uploads\//i.test(url)) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}access_token=${encodeURIComponent(token)}`;
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
        movie_story_mode: request.movie_story_mode || 'two_round',
        movie_story_feature_mode: request.movie_story_mode || 'two_round',
        movie_story_enable_visual_evidence: Boolean(request.movie_story_enable_visual_evidence),
        movie_story_strategy: normalizeMovieStoryStrategy(request.movie_story_strategy),
        visual_mode: request.visual_mode || 'auto',
        target_duration_minutes: request.target_duration_minutes || 8,
        highlight_only: Boolean(request.highlight_only),
        highlight_selectivity: request.highlight_selectivity || 'balanced',
        narrative_strategy: request.narrative_strategy || 'chronological',
        accuracy_priority: request.accuracy_priority || 'high',
        temperature: request.temperature ?? 0.7,
        ...(request.asr_backend ? { asr_backend: request.asr_backend } : {}),
        skip_llm: Boolean(request.skip_llm),
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

export async function getSystemHealth(): Promise<SystemHealthResponse> {
  return requestJson<SystemHealthResponse>('/api/v1/system/health', { method: 'GET' });
}

export async function getUsageSummary(limit = 20): Promise<UsageSummaryResponse> {
  return requestJson<UsageSummaryResponse>(`/api/v1/system/usage?limit=${encodeURIComponent(String(limit))}`, { method: 'GET' });
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

export async function fetchNarrationWorkbench(projectId: string): Promise<NarrationWorkbench> {
  return requestJson<NarrationWorkbench>(`/api/v1/projects/${projectId}/narration/workbench`, { method: 'GET' });
}

export async function fetchHighlightSelection(projectId: string): Promise<HighlightSelectionResponse> {
  return requestJson<HighlightSelectionResponse>(`/api/v1/projects/${projectId}/narration/highlights/selection`, { method: 'GET' });
}

export async function saveHighlightSelection(
  projectId: string,
  items: HighlightSelectionItem[],
  note = ''
): Promise<HighlightSelectionSaveResponse> {
  return requestJson<HighlightSelectionSaveResponse>(`/api/v1/projects/${projectId}/narration/highlights/selection`, {
    method: 'POST',
    body: JSON.stringify({ items, note }),
  });
}

export async function createNarrationQualityReport(
  projectId: string,
  scriptItems?: Array<Record<string, any>>,
  options?: { save_report?: boolean; speed?: number }
): Promise<NarrationQualityReport> {
  return requestJson<NarrationQualityReport>(`/api/v1/projects/${projectId}/narration/quality-report`, {
    method: 'POST',
    body: JSON.stringify({
      script_items: scriptItems,
      save_report: options?.save_report ?? false,
      speed: options?.speed ?? 1,
    }),
  });
}

export async function humanizeNarrationScript(
  projectId: string,
  scriptItems: Array<Record<string, any>>,
  options?: { persona?: string; intensity?: number; save_version?: boolean }
): Promise<NarrationHumanizeResponse> {
  return requestJson<NarrationHumanizeResponse>(`/api/v1/projects/${projectId}/narration/humanize`, {
    method: 'POST',
    body: JSON.stringify({
      script_items: scriptItems,
      persona: options?.persona || 'suspense',
      intensity: options?.intensity ?? 0.65,
      save_version: options?.save_version ?? false,
    }),
  });
}

export async function saveNarrationScriptVersion(
  projectId: string,
  scriptItems: Array<Record<string, any>>,
  label = '手动脚本版本',
  note = '',
  qualityReport?: NarrationQualityReport
): Promise<NarrationScriptVersionResponse> {
  return requestJson<NarrationScriptVersionResponse>(`/api/v1/projects/${projectId}/narration/scripts/versions`, {
    method: 'POST',
    body: JSON.stringify({ script_items: scriptItems, label, note, quality_report: qualityReport }),
  });
}

export async function getSignedWorkspaceFileUrl(path: string, projectId = '', artifactId = ''): Promise<string> {
  const params = new URLSearchParams();
  params.set('path', path);
  params.set('project_id', projectId);
  if (artifactId) params.set('artifact_id', artifactId);
  const payload = await requestJson<{ url: string; expires: number }>(`/api/v1/projects/workspace-file/signed-url?${params.toString()}`, { method: 'GET' });
  return withBase(payload.url);
}

export function resolveWorkspaceFileUrl(path: string, projectId = '', artifactId = ''): string {
  if (!path) return '';
  const params = new URLSearchParams();
  params.set('path', path);
  if (projectId) params.set('project_id', projectId);
  if (artifactId) params.set('artifact_id', artifactId);
  const token = getStoredToken();
  if (token) params.set('access_token', token);
  return withBase(`/api/v1/projects/workspace-file?${params.toString()}`);
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
  raw_url?: string;
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
    const protectedUrl = appendAccessToken(url);
    const base = config.API_BASE_URL || '';
    return base ? `${base.replace(/\/$/, '')}${protectedUrl}` : protectedUrl;
  }
  if (/^[A-Za-z]:[\\/]/.test(url) || url.startsWith('/')) {
    return resolveWorkspaceFileUrl(url, projectId, artifactId);
  }
  const base = config.API_BASE_URL || '';
  return base ? `${base.replace(/\/$/, '')}/${url.replace(/^\/+/, '')}` : url;
}


export async function getJobEvents(taskId: string, limit = 200): Promise<JobEventListResponse> {
  return requestJson<JobEventListResponse>(`/api/v1/jobs/${encodeURIComponent(taskId)}/events?limit=${encodeURIComponent(String(limit))}`, { method: 'GET' });
}

export async function getJobStatus(taskId: string): Promise<JobStatusResponse> {
  return requestJson<JobStatusResponse>(`/api/v1/jobs/${taskId}`, { method: 'GET' });
}

export async function cancelJob(taskId: string): Promise<{ task_id: string; status: string; message: string }> {
  return requestJson<{ task_id: string; status: string; message: string }>(`/api/v1/jobs/${taskId}/cancel`, { method: 'POST' });
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
  is_running?: boolean;
};


export type JobEventItem = {
  id: string;
  task_id: string;
  event_type: string;
  status: string;
  progress: number;
  message: string;
  project_id?: string;
  job_type?: string;
  metadata: Record<string, any>;
  created_at: string;
};

export type JobEventListResponse = {
  items: JobEventItem[];
};

export type JobWorkerStatusResponse = {
  backend: string;
  max_workers: number;
  tracked_jobs: number;
  queued: number;
  running: number;
  done: number;
  cancel_requested: number;
  active_processes?: number;
  process_tasks?: Record<string, number>;
  queue?: string;
  redis_url?: string;
  available?: boolean;
  error?: string;
};

export type JobHistoryResponse = {
  items: JobHistoryItem[];
};

export async function listJobHistory(projectId = '', limit = 60): Promise<JobHistoryResponse> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  params.set('limit', String(limit));
  return requestJson<JobHistoryResponse>(`/api/v1/jobs?${params.toString()}`, { method: 'GET' });
}

export async function getJobWorkerStatus(): Promise<JobWorkerStatusResponse> {
  return requestJson<JobWorkerStatusResponse>('/api/v1/jobs/workers/status', { method: 'GET' });
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
    if (snapshot.status === 'cancelled') {
      throw new Error(snapshot.message || '任务已取消');
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

  const scriptItems = Array.isArray(result.script_items) ? result.script_items : [];

  if (scriptItems.length === 0) {
    throw new Error(
      '后端未返回 result.script_items，无法展示解说文案预览。请检查 movie_story_script 任务结果契约。'
    );
  }

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
        result.script_path ||
          result.output_script_path ||
          result.video_clip_json_path ||
          payload.video_clip_json_path ||
          ''
      ) || '',
    scriptItems,
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

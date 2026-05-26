import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Cpu,
  Database,
  Gauge,
  Loader2,
  RefreshCw,
  Square,
  TerminalSquare,
  XCircle,
} from 'lucide-react';
import { AppLayout } from '@/components/layout/AppLayout';
import { RequireAuth } from '@/components/layout/RequireAuth';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  cancelJob,
  getJobEvents,
  getJobWorkerStatus,
  getSystemHealth,
  getUsageSummary,
  listJobHistory,
  type JobEventItem,
  type JobHistoryItem,
  type JobWorkerStatusResponse,
  type SystemHealthResponse,
  type UsageSummaryResponse,
} from '@/lib/api';
import { cn } from '@/lib/utils';
import { formatDistanceToNow } from '@/lib/time';
import { toast } from 'sonner';

type LoadState = 'idle' | 'loading' | 'loaded' | 'error';

const JOB_TYPE_LABELS: Record<string, string> = {
  video: '视频合成',
  movie_story_script: '电影解说脚本',
  'movie-story-script': '电影解说脚本',
  highlight_script: '高光粗剪脚本',
  'highlight-script': '高光粗剪脚本',
  subtitle: '字幕识别',
  tts: '配音合成',
};

const STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  processing: '处理中',
  complete: '已完成',
  completed: '已完成',
  success: '成功',
  failed: '失败',
  error: '错误',
  cancelled: '已取消',
  cancel_requested: '取消中',
};

function jobTypeLabel(value: string): string {
  return JOB_TYPE_LABELS[value] ?? value ?? '任务';
}

function statusLabel(value: string): string {
  return STATUS_LABELS[value] ?? value ?? '未知';
}

function isActiveJob(item: JobHistoryItem): boolean {
  return ['queued', 'running', 'processing', 'cancel_requested'].includes(item.status);
}

function statusTone(status: string): string {
  if (['complete', 'completed', 'success'].includes(status)) {
    return 'bg-[#46ec13]/12 text-[#7dff4d] border-[#46ec13]/25';
  }
  if (['failed', 'error'].includes(status)) {
    return 'bg-red-500/10 text-red-300 border-red-500/25';
  }
  if (['cancelled', 'cancel_requested'].includes(status)) {
    return 'bg-yellow-500/10 text-yellow-300 border-yellow-500/25';
  }
  return 'bg-indigo-500/10 text-indigo-200 border-indigo-500/25';
}

function formatBytes(value: unknown): string {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let current = bytes;
  let idx = 0;
  while (current >= 1024 && idx < units.length - 1) {
    current /= 1024;
    idx += 1;
  }
  return `${current.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function safeDate(value: string): string {
  if (!value) return '未知时间';
  try {
    return formatDistanceToNow(value);
  } catch {
    return value;
  }
}

function HealthBadge({ ok, label }: { ok: boolean; label: string }) {
  const Icon = ok ? CheckCircle2 : XCircle;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs',
        ok ? 'border-[#46ec13]/30 bg-[#46ec13]/10 text-[#7dff4d]' : 'border-red-500/25 bg-red-500/10 text-red-300'
      )}
    >
      <Icon className="h-3.5 w-3.5" /> {label}
    </span>
  );
}

function StatCard({ title, value, hint, icon: Icon }: { title: string; value: string | number; hint?: string; icon: typeof Activity }) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs text-white/45">{title}</div>
          <div className="mt-1 text-2xl font-semibold">{value}</div>
        </div>
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#46ec13]/10 text-[#46ec13]">
          <Icon className="h-5 w-5" />
        </div>
      </div>
      {hint ? <div className="mt-2 text-xs text-white/40">{hint}</div> : null}
    </div>
  );
}

function JobsPanel({
  jobs,
  worker,
  selectedTaskId,
  onSelect,
  events,
  onCancel,
  cancellingTaskId,
}: {
  jobs: JobHistoryItem[];
  worker: JobWorkerStatusResponse | null;
  selectedTaskId: string;
  onSelect: (taskId: string) => void;
  events: JobEventItem[];
  onCancel: (taskId: string) => void;
  cancellingTaskId: string;
}) {
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(360px,0.9fr)]">
      <section className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">任务中心</h2>
            <p className="text-sm text-white/45">查看排队、运行、完成和失败任务；支持取消未完成任务。</p>
          </div>
          {worker ? (
            <div className="hidden rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-xs text-white/55 md:block">
              worker {worker.running}/{worker.max_workers} · 子进程 {worker.active_processes ?? 0}
            </div>
          ) : null}
        </div>

        {jobs.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-white/45">
            暂无任务记录。创建项目并提交任务后会出现在这里。
          </div>
        ) : (
          <div className="space-y-3">
            {jobs.map((item) => {
              const selected = selectedTaskId === item.task_id;
              const active = isActiveJob(item);
              return (
                <button
                  key={item.task_id}
                  type="button"
                  onClick={() => onSelect(item.task_id)}
                  className={cn(
                    'w-full rounded-xl border p-4 text-left transition hover:border-[#46ec13]/35 hover:bg-white/[0.04]',
                    selected ? 'border-[#46ec13]/45 bg-[#46ec13]/5' : 'border-white/[0.06] bg-black/10'
                  )}
                >
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{jobTypeLabel(item.job_type)}</span>
                        <span className={cn('rounded-full border px-2 py-0.5 text-xs', statusTone(item.status))}>
                          {statusLabel(item.status)}
                        </span>
                      </div>
                      <div className="mt-1 truncate text-xs text-white/45">{item.task_id}</div>
                      {item.message || item.error ? (
                        <div className={cn('mt-2 text-sm', item.error ? 'text-red-300' : 'text-white/60')}>
                          {(item.error || item.message).slice(0, 180)}
                        </div>
                      ) : null}
                      <div className="mt-3 flex items-center gap-3">
                        <Progress value={Math.max(0, Math.min(100, Number(item.progress || 0)))} className="h-2" />
                        <span className="w-10 text-right text-xs text-white/50">{item.progress || 0}%</span>
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-col items-start gap-2 md:items-end">
                      <span className="text-xs text-white/40">{safeDate(item.updated_at)}</span>
                      {active ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="border-red-400/30 bg-red-500/10 text-red-200 hover:bg-red-500/20"
                          disabled={cancellingTaskId === item.task_id}
                          onClick={(event) => {
                            event.stopPropagation();
                            onCancel(item.task_id);
                          }}
                        >
                          {cancellingTaskId === item.task_id ? (
                            <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Square className="mr-1 h-3.5 w-3.5" />
                          )}
                          取消
                        </Button>
                      ) : null}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">
        <div className="mb-4 flex items-center gap-2">
          <TerminalSquare className="h-5 w-5 text-[#46ec13]" />
          <div>
            <h2 className="text-lg font-semibold">任务事件</h2>
            <p className="text-sm text-white/45">展示 queued/running/progress/子进程事件。</p>
          </div>
        </div>
        {!selectedTaskId ? (
          <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-white/45">
            选择左侧任务查看事件日志。
          </div>
        ) : events.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-white/45">
            暂无事件。旧任务可能没有事件记录。
          </div>
        ) : (
          <ol className="relative space-y-4 border-l border-white/10 pl-5">
            {events.map((event) => (
              <li key={event.id} className="relative">
                <span className="absolute -left-[27px] top-1 h-3 w-3 rounded-full border border-[#46ec13]/60 bg-[#0b110d]" />
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium">{statusLabel(event.event_type) || event.event_type}</div>
                    <div className="mt-0.5 text-xs text-white/45">{event.status ? statusLabel(event.status) : ''} {event.progress ? `· ${event.progress}%` : ''}</div>
                  </div>
                  <span className="shrink-0 text-xs text-white/35">{safeDate(event.created_at)}</span>
                </div>
                {event.message ? <div className="mt-1 text-sm text-white/60">{event.message}</div> : null}
                {event.metadata && Object.keys(event.metadata).length > 0 ? (
                  <pre className="mt-2 max-h-32 overflow-auto rounded-lg bg-black/30 p-2 text-xs text-white/45">
                    {JSON.stringify(event.metadata, null, 2)}
                  </pre>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

function HealthPanel({ health, worker }: { health: SystemHealthResponse | null; worker: JobWorkerStatusResponse | null }) {
  const workspace = health?.workspace || {};
  const runtime = health?.runtime || {};
  const asr = health?.asr || {};
  const tts = health?.tts || {};
  const ffmpeg = runtime.ffmpeg || {};
  const processTasks = worker?.process_tasks || {};

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-4">
        <StatCard title="磁盘剩余" value={formatBytes(workspace.free_bytes)} hint={`总容量 ${formatBytes(workspace.total_bytes)}`} icon={Database} />
        <StatCard title="运行中任务" value={worker?.running ?? 0} hint={`排队 ${worker?.queued ?? 0} · 总追踪 ${worker?.tracked_jobs ?? 0}`} icon={Activity} />
        <StatCard title="活跃子进程" value={worker?.active_processes ?? 0} hint="FFmpeg / ffprobe / 外部命令" icon={Cpu} />
        <StatCard title="最大 worker" value={worker?.max_workers ?? runtime.local_job_max_workers ?? 0} hint={`${worker?.backend || 'local'}${worker?.queue ? ` · ${worker.queue}` : ''}`} icon={Gauge} />
      </div>

      <section className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">
        <h2 className="mb-4 text-lg font-semibold">系统健康检查</h2>
        <div className="flex flex-wrap gap-2">
          <HealthBadge ok={Boolean(workspace.exists)} label="Workspace" />
          <HealthBadge ok={Boolean(ffmpeg.available)} label="FFmpeg" />
          <HealthBadge ok={Boolean(runtime.imagemagick_configured)} label="ImageMagick 配置" />
          <HealthBadge ok={Boolean(asr.bailian_key_configured)} label="百炼 ASR Key" />
          <HealthBadge ok={Boolean(asr.funasr_model_path_exists)} label="FunASR 模型" />
          <HealthBadge ok={Boolean(asr.sensevoice_model_path_exists)} label="SenseVoice 模型" />
          <HealthBadge ok={Boolean(tts.qwen_key_configured)} label="Qwen TTS Key" />
          <HealthBadge ok={Boolean(tts.azure_key_configured)} label="Azure TTS Key" />
        </div>
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-white/10 bg-black/20 p-4">
            <div className="text-sm font-medium">运行环境</div>
            <dl className="mt-3 space-y-2 text-sm text-white/55">
              <div className="flex justify-between gap-4"><dt>版本</dt><dd>{health?.project_version || '-'}</dd></div>
              <div className="flex justify-between gap-4"><dt>环境</dt><dd>{health?.environment || '-'}</dd></div>
              <div className="flex justify-between gap-4"><dt>公开 uploads</dt><dd>{runtime.public_uploads_enabled ? '开启' : '关闭'}</dd></div>
              <div className="flex justify-between gap-4"><dt>任务后端</dt><dd>{worker?.backend || 'local'}{worker?.available === false ? '（不可用）' : ''}</dd></div>
              {worker?.queue ? <div className="flex justify-between gap-4"><dt>队列</dt><dd>{worker.queue}</dd></div> : null}
              {worker?.error ? <div className="flex justify-between gap-4 text-red-300"><dt>队列错误</dt><dd className="truncate text-right">{worker.error}</dd></div> : null}
              <div className="flex justify-between gap-4"><dt>FFmpeg</dt><dd className="truncate text-right">{ffmpeg.path || '-'}</dd></div>
            </dl>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 p-4">
            <div className="text-sm font-medium">活跃子进程任务</div>
            {Object.keys(processTasks).length === 0 ? (
              <div className="mt-3 text-sm text-white/45">当前没有活跃子进程。</div>
            ) : (
              <div className="mt-3 space-y-2">
                {Object.entries(processTasks).map(([taskId, count]) => (
                  <div key={taskId} className="flex items-center justify-between gap-4 rounded-lg bg-white/[0.03] px-3 py-2 text-sm">
                    <span className="truncate text-white/55">{taskId}</span>
                    <span className="text-[#46ec13]">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function UsagePanel({ usage }: { usage: UsageSummaryResponse | null }) {
  const summary = usage?.summary || [];
  const recent = usage?.recent || [];
  const totalEvents = summary.reduce((sum, row) => sum + Number(row.event_count || 0), 0);
  const totalUnits = summary.reduce((sum, row) => sum + Number(row.total_units || 0), 0);
  const totalCost = summary.reduce((sum, row) => sum + Number(row.total_cost || 0), 0);
  const pricing = usage?.pricing;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-4">
        <StatCard title="Usage 类型" value={summary.length} hint="按 event/provider/unit 分组" icon={Gauge} />
        <StatCard title="事件数" value={totalEvents} hint="当前用户累计" icon={Activity} />
        <StatCard title="总单位量" value={totalUnits} hint="tokens / chars / bytes / seconds 混合汇总" icon={Database} />
        <StatCard title="估算成本" value={totalCost.toFixed(4)} hint={pricing?.configured ? `价格规则 ${pricing.rule_count}` : '未配置价格规则'} icon={Cpu} />
      </div>

      {!pricing?.configured ? (
        <div className="rounded-xl border border-yellow-500/20 bg-yellow-500/10 p-4 text-sm text-yellow-100">
          当前未配置成本价格表，Usage 面板只统计调用量。可通过 AIVIDEO_USAGE_PRICES_JSON 配置估算单价。
        </div>
      ) : null}

      <section className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">
        <h2 className="mb-4 text-lg font-semibold">Usage 汇总</h2>
        {summary.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-white/45">暂无用量记录。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="text-left text-xs text-white/45">
                <tr className="border-b border-white/10">
                  <th className="py-2 pr-4">类型</th>
                  <th className="py-2 pr-4">Provider</th>
                  <th className="py-2 pr-4">单位</th>
                  <th className="py-2 pr-4 text-right">事件数</th>
                  <th className="py-2 pr-4 text-right">单位总量</th>
                  <th className="py-2 text-right">估算成本</th>
                </tr>
              </thead>
              <tbody>
                {summary.map((row, index) => (
                  <tr key={`${row.event_type}-${row.provider}-${row.unit_name}-${index}`} className="border-b border-white/[0.06] last:border-0">
                    <td className="py-3 pr-4 text-white/80">{row.event_type}</td>
                    <td className="py-3 pr-4 text-white/60">{row.provider || '-'}</td>
                    <td className="py-3 pr-4 text-white/60">{row.unit_name}</td>
                    <td className="py-3 pr-4 text-right text-white/70">{row.event_count}</td>
                    <td className="py-3 pr-4 text-right text-white/70">{row.total_units}</td>
                    <td className="py-3 text-right text-white/70">{Number(row.total_cost || 0).toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">
        <h2 className="mb-4 text-lg font-semibold">最近 Usage 事件</h2>
        {recent.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-white/45">暂无最近事件。</div>
        ) : (
          <div className="space-y-3">
            {recent.map((row) => (
              <div key={String(row.id)} className="rounded-xl border border-white/[0.06] bg-black/10 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-medium">{row.event_type}</div>
                  <div className="text-xs text-white/40">{safeDate(String(row.created_at || ''))}</div>
                </div>
                <div className="mt-1 text-sm text-white/55">
                  {row.provider || '-'} · {row.units} {row.unit_name}
                </div>
                {row.metadata && Object.keys(row.metadata).length > 0 ? (
                  <pre className="mt-2 max-h-28 overflow-auto rounded-lg bg-black/30 p-2 text-xs text-white/45">
                    {JSON.stringify(row.metadata, null, 2)}
                  </pre>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function OperationsInner() {
  const [tab, setTab] = useState<'jobs' | 'health' | 'usage'>('jobs');
  const [loadState, setLoadState] = useState<LoadState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobHistoryItem[]>([]);
  const [worker, setWorker] = useState<JobWorkerStatusResponse | null>(null);
  const [health, setHealth] = useState<SystemHealthResponse | null>(null);
  const [usage, setUsage] = useState<UsageSummaryResponse | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState('');
  const [events, setEvents] = useState<JobEventItem[]>([]);
  const [cancellingTaskId, setCancellingTaskId] = useState('');

  const activeJobs = useMemo(() => jobs.filter(isActiveJob).length, [jobs]);

  const refresh = async () => {
    setLoadState((prev) => (prev === 'idle' ? 'loading' : prev));
    try {
      const [jobResp, workerResp, healthResp, usageResp] = await Promise.all([
        listJobHistory('', 120),
        getJobWorkerStatus(),
        getSystemHealth(),
        getUsageSummary(30),
      ]);
      const sortedJobs = [...jobResp.items].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
      setJobs(sortedJobs);
      setWorker(workerResp);
      setHealth(healthResp);
      setUsage(usageResp);
      setError(null);
      setLoadState('loaded');
      if (!selectedTaskId && sortedJobs[0]) {
        setSelectedTaskId(sortedJobs[0].task_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载运维数据失败');
      setLoadState('error');
    }
  };

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 10000);
    return () => window.clearInterval(timer);
    // selectedTaskId intentionally excluded: refresh should not restart polling when user selects a task.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadEvents = async () => {
      if (!selectedTaskId) {
        setEvents([]);
        return;
      }
      try {
        const resp = await getJobEvents(selectedTaskId, 200);
        if (!cancelled) setEvents(resp.items || []);
      } catch (err) {
        if (!cancelled) setEvents([]);
      }
    };
    void loadEvents();
    const timer = window.setInterval(loadEvents, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selectedTaskId]);

  const handleCancel = async (taskId: string) => {
    setCancellingTaskId(taskId);
    try {
      const resp = await cancelJob(taskId);
      toast.success(resp.message || '已请求取消任务');
      await refresh();
      if (selectedTaskId === taskId) {
        const eventsResp = await getJobEvents(taskId, 200);
        setEvents(eventsResp.items || []);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '取消任务失败');
    } finally {
      setCancellingTaskId('');
    }
  };

  return (
    <AppLayout>
      <div className="container-page py-10">
        <header className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-3xl font-bold">运维中心</h1>
            <p className="mt-1 text-sm text-white/55">任务中心、系统健康和用量统计的最小闭环页面。</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-white/55">
              <Clock3 className="h-3.5 w-3.5" /> 活跃任务 {activeJobs}
            </span>
            <Button
              type="button"
              variant="outline"
              className="border-white/15 bg-white/[0.03] text-white hover:bg-white/[0.08]"
              onClick={() => void refresh()}
              disabled={loadState === 'loading'}
            >
              <RefreshCw className={cn('mr-2 h-4 w-4', loadState === 'loading' ? 'animate-spin' : '')} />
              刷新
            </Button>
          </div>
        </header>

        {error ? (
          <div className="mb-6 flex items-start gap-3 rounded-xl border border-red-500/25 bg-red-500/10 p-4 text-sm text-red-200">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>加载失败：{error}</div>
          </div>
        ) : null}

        <div className="mb-6 inline-flex rounded-full border border-white/10 bg-white/[0.03] p-1">
          {([
            ['jobs', '任务中心'],
            ['health', '系统健康'],
            ['usage', '用量统计'],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={cn(
                'rounded-full px-4 py-2 text-sm transition',
                tab === key ? 'bg-[#46ec13] font-semibold text-[#060a07]' : 'text-white/65 hover:text-white'
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {loadState === 'loading' ? (
          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-12 text-center text-white/50">
            <Loader2 className="mx-auto mb-3 h-6 w-6 animate-spin" /> 正在加载运维数据...
          </div>
        ) : tab === 'jobs' ? (
          <JobsPanel
            jobs={jobs}
            worker={worker}
            selectedTaskId={selectedTaskId}
            onSelect={setSelectedTaskId}
            events={events}
            onCancel={handleCancel}
            cancellingTaskId={cancellingTaskId}
          />
        ) : tab === 'health' ? (
          <HealthPanel health={health} worker={worker} />
        ) : (
          <UsagePanel usage={usage} />
        )}
      </div>
    </AppLayout>
  );
}

export default function Operations() {
  return (
    <RequireAuth>
      <OperationsInner />
    </RequireAuth>
  );
}

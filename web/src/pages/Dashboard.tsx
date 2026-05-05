import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  CheckCircle2,
  Film,
  FolderOpen,
  Loader2,
  Plus,
  Rocket,
  ArrowRight,
} from 'lucide-react';
import { AppLayout } from '@/components/layout/AppLayout';
import { RequireAuth } from '@/components/layout/RequireAuth';
import { Button } from '@/components/ui/button';
import {
  listProjects,
  hydrateProjects,
  createProject,
  type Project,
} from '@/lib/projects-store';
import { formatDistanceToNow } from '@/lib/time';
import { listJobHistory, type JobHistoryItem } from '@/lib/api';
import { isAuthError } from '@/lib/auth';
import { toast } from 'sonner';
import CreateProjectModal, { type InferenceMode } from '@/components/workspace/CreateProjectModal';

const JOB_TYPE_LABELS: Record<string, string> = {
  video: '视频合成',
  'movie-story-script': '电影解说脚本',
  'highlight-script': '高光脚本',
  subtitle: '字幕识别',
  tts: '配音合成',
};

function jobTypeLabel(type: string): string {
  return JOB_TYPE_LABELS[type] ?? type;
}

function jobIcon(status: string): typeof Rocket {
  if (status === 'completed' || status === 'success') return CheckCircle2;
  if (status === 'failed' || status === 'error') return AlertTriangle;
  if (status === 'running' || status === 'pending') return Loader2;
  return Rocket;
}

function jobTitle(item: JobHistoryItem): string {
  const label = jobTypeLabel(item.job_type);
  if (item.status === 'completed' || item.status === 'success') {
    return `${label} 已完成`;
  }
  if (item.status === 'failed' || item.status === 'error') {
    return `${label} 失败${item.error ? `：${item.error.slice(0, 40)}` : ''}`;
  }
  if (item.status === 'running') {
    return `${label} 进行中${item.progress ? `（${item.progress}%）` : ''}`;
  }
  return `${label} · ${item.status}`;
}

function DashboardInner() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [jobs, setJobs] = useState<JobHistoryItem[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  useEffect(() => {
    const loadProjects = async () => {
      try {
        await hydrateProjects();
      } catch (err) {
        if (!isAuthError(err)) console.error('加载项目失败:', err);
      } finally {
        setProjects(listProjects().slice(0, 3));
      }
    };
    void loadProjects();
    const onProjectsChanged = () => setProjects(listProjects().slice(0, 3));
    window.addEventListener('aivideo:projects', onProjectsChanged);
    return () => window.removeEventListener('aivideo:projects', onProjectsChanged);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const resp = await listJobHistory();
        if (cancelled) return;
        // 最新的在前，截取前 8 条
        const sorted = [...resp.items].sort((a, b) =>
          b.updated_at.localeCompare(a.updated_at)
        );
        setJobs(sorted.slice(0, 8));
        setJobsError(null);
      } catch (err) {
        if (cancelled) return;
        if (isAuthError(err)) { setJobs([]); setJobsError(null); return; }
        setJobsError(err instanceof Error ? err.message : '加载任务历史失败');
      } finally {
        if (!cancelled) setJobsLoading(false);
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const quickCreate = async (name: string, mode: InferenceMode) => {
    try {
      const p = await createProject(name, mode);
      setCreateOpen(false);
      toast.success('项目已创建');
      navigate(`/projects/${p.id}/material`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '创建项目失败');
    }
  };

  return (
    <AppLayout>
      <div className="container-page py-10">
        <header className="mb-10">
          <h1 className="text-3xl font-bold">仪表盘</h1>
          <p className="text-sm text-white/55 mt-1">欢迎回来。这里是您最近活动的快照。</p>
        </header>

        <section className="mb-10">
          <h2 className="text-base font-semibold mb-4">最近项目</h2>
          <div className="grid md:grid-cols-3 gap-5">
            {projects.length === 0 ? (
              <div className="col-span-full rounded-2xl border border-dashed border-white/10 p-10 text-center text-white/50">
                还没有项目，立即创建你的第一个视频项目。
              </div>
            ) : (
              projects.map((p) => (
                <Link
                  key={p.id}
                  to={`/projects/${p.id}/material`}
                  className="group rounded-2xl overflow-hidden bg-white/[0.03] border border-white/[0.06] hover:border-[#46ec13]/40 transition"
                >
                  <div className="aspect-[16/9] bg-white/[0.04] flex items-center justify-center overflow-hidden">
                    {p.thumbnailUrl ? (
                      <img
                        src={p.thumbnailUrl}
                        alt={p.name}
                        className="w-full h-full object-cover group-hover:scale-105 transition"
                        loading="lazy"
                      />
                    ) : (
                      <span className="text-white/40 text-sm">无预览图</span>
                    )}
                  </div>
                  <div className="p-4">
                    <div className="font-semibold text-sm">{p.name}</div>
                    <div className="text-xs text-white/45 mt-1">
                      {formatDistanceToNow(p.updatedAt)}最后编辑
                    </div>
                  </div>
                </Link>
              ))
            )}
          </div>
        </section>

        <div className="grid md:grid-cols-2 gap-8">
          <section>
            <h2 className="text-base font-semibold mb-4">快速操作</h2>
            <div className="flex gap-3 flex-wrap">
              <Button
                onClick={() => setCreateOpen(true)}
                className="bg-[#46ec13] hover:bg-[#37c00c] text-[#060a07] font-semibold rounded-full px-5"
              >
                <Plus className="w-4 h-4 mr-1" /> 创建项目
              </Button>
              <Link to="/projects">
                <Button variant="outline" className="rounded-full px-5 border-white/15 bg-white/[0.03] text-white hover:bg-white/10">
                  <FolderOpen className="w-4 h-4 mr-1" /> 查看所有项目
                </Button>
              </Link>
              <Link to="/pricing">
                <Button variant="ghost" className="rounded-full px-5 text-white/70 hover:text-white">
                  <Film className="w-4 h-4 mr-1" /> 升级套餐
                </Button>
              </Link>
            </div>
          </section>

          <section>
            <h2 className="text-base font-semibold mb-4">任务动态</h2>
            {jobsLoading ? (
              <div className="flex items-center gap-2 text-sm text-white/55">
                <Loader2 className="w-4 h-4 animate-spin" />
                正在加载任务历史…
              </div>
            ) : jobsError ? (
              <div className="rounded-xl p-3 bg-red-500/10 border border-red-500/30 text-sm text-red-300">
                加载失败：{jobsError}
              </div>
            ) : jobs.length === 0 ? (
              <div className="rounded-xl p-6 bg-white/[0.03] border border-dashed border-white/10 text-sm text-white/50 text-center">
                还没有任务记录，去创建一个新项目开始吧。
              </div>
            ) : (
              <ul className="space-y-3">
                {jobs.map((item) => {
                  const Icon = jobIcon(item.status);
                  const spinning = item.status === 'running' || item.status === 'pending';
                  return (
                    <li
                      key={item.task_id}
                      className="flex items-start gap-3 rounded-xl p-3 bg-white/[0.03] border border-white/[0.06]"
                    >
                      <div
                        className="w-9 h-9 rounded-full flex items-center justify-center shrink-0"
                        style={{
                          background: 'rgba(70,236,19,0.12)',
                          color: '#46ec13',
                        }}
                      >
                        <Icon className={`w-4 h-4 ${spinning ? 'animate-spin' : ''}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm truncate">{jobTitle(item)}</div>
                        <div className="text-xs text-white/45 mt-0.5">
                          {formatDistanceToNow(item.updated_at)}
                          {item.message ? ` · ${item.message.slice(0, 50)}` : ''}
                        </div>
                      </div>
                      <ArrowRight className="w-4 h-4 text-white/30 mt-2" />
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      </div>

      <CreateProjectModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreate={(name, mode) => { void quickCreate(name, mode); }}
      />
    </AppLayout>
  );
}

export default function Dashboard() {
  return (
    <RequireAuth>
      <DashboardInner />
    </RequireAuth>
  );
}

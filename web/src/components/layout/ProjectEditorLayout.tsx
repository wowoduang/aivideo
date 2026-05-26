import { useEffect, useMemo, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate, useParams } from 'react-router-dom';
import { AlertTriangle, Bell, ChevronDown, LogOut } from 'lucide-react';
import { BrandLogo } from '@/components/brand/Logo';
import { cn } from '@/lib/utils';
import { isAuthError, useAuth } from '@/lib/auth';
import { getProject, hydrateProjects, type Project } from '@/lib/projects-store';
import { RequireAuth } from '@/components/layout/RequireAuth';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { toast } from 'sonner';

const TABS = [
  { key: 'material', label: '素材' },
  { key: 'highlights', label: '高光复选' },
  { key: 'analysis', label: '脚本' },
  { key: 'dubbing', label: '配音' },
];

export function ProjectEditorLayoutInner() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [project, setProject] = useState<Project | undefined>();
  const [loadError, setLoadError] = useState('');

  const displayName = user?.name || user?.username || (user?.email ? user.email.split('@')[0] : 'hello');
  const initial = displayName.charAt(0).toUpperCase();

  useEffect(() => {
    if (!id) return;
    const refresh = () => setProject(getProject(id));
    refresh();
    void hydrateProjects()
      .then(() => {
        setLoadError('');
        refresh();
      })
      .catch((err) => {
        if (!isAuthError(err)) {
          const message = err instanceof Error ? err.message : '加载项目详情失败';
          console.error('加载项目详情失败:', err);
          setLoadError(message);
          toast.error(`加载项目失败：${message}`);
        }
      })
      .finally(refresh);
    window.addEventListener('aivideo:projects', refresh);
    return () => window.removeEventListener('aivideo:projects', refresh);
  }, [id]);

  useEffect(() => {
    const onSyncError = (event: Event) => {
      const message = String((event as CustomEvent<{ message?: string }>).detail?.message || '项目同步失败');
      setLoadError(message);
    };
    window.addEventListener('aivideo:project-sync-error', onSyncError);
    return () => window.removeEventListener('aivideo:project-sync-error', onSyncError);
  }, []);

  const tabBase = useMemo(() => `/projects/${id}`, [id]);

  if (!id) return null;

  return (
    <div className="min-h-screen flex flex-col bg-[#060a07] text-white">
      <header className="sticky top-0 z-40 border-b border-white/5 bg-[#060a07]/90 backdrop-blur">
        <div className="container-page h-16 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2">
            <BrandLogo />
          </Link>
          <nav className="flex-1 flex justify-center">
            <div className="inline-flex items-center bg-white/[0.04] border border-white/5 rounded-full p-1">
              {TABS.map((t) => (
                <NavLink
                  key={t.key}
                  to={`${tabBase}/${t.key}`}
                  className={({ isActive }) =>
                    cn(
                      'px-4 py-1.5 rounded-full text-sm transition-all',
                      isActive
                        ? 'bg-[#46ec13] text-[#060a07] font-semibold'
                        : 'text-white/70 hover:text-white'
                    )
                  }
                >
                  {t.label}
                </NavLink>
              ))}
            </div>
          </nav>
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="relative w-9 h-9 flex items-center justify-center rounded-full border border-white/10 text-white/70 hover:bg-white/5"
              aria-label="Notifications"
            >
              <Bell className="w-4 h-4" />
            </button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-2 rounded-full pl-1 pr-2 py-1 border border-white/10 hover:bg-white/5">
                  <span
                    className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold"
                    style={{
                      background:
                        'radial-gradient(circle at 30% 30%, #7dff4d, #2cb90a 70%)',
                      color: '#060a07',
                    }}
                  >
                    {initial}
                  </span>
                  <div className="hidden sm:flex flex-col items-start leading-tight">
                    <span className="text-xs text-white">{displayName}</span>
                    <span className="text-[10px] text-[#46ec13]">已验证</span>
                  </div>
                  <ChevronDown className="w-3.5 h-3.5 text-white/60" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="bg-[#0b110d] border-white/10 text-white">
                <DropdownMenuItem onClick={() => navigate('/dashboard')} className="cursor-pointer focus:bg-white/5">
                  返回仪表盘
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={async () => {
                    await logout();
                    navigate('/');
                  }}
                  className="cursor-pointer focus:bg-white/5 text-red-400"
                >
                  <LogOut className="w-4 h-4 mr-2" /> 退出登录
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      <main className="flex-1 flex flex-col">
        {loadError ? (
          <div className="border-b border-red-500/20 bg-red-500/10 px-6 py-3 text-sm text-red-100">
            <div className="container-page flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-300" />
              <div>
                <div className="font-medium">项目加载或同步失败</div>
                <div className="mt-0.5 text-red-100/80">{loadError}</div>
              </div>
            </div>
          </div>
        ) : null}
        <Outlet context={{ project }} />
      </main>
    </div>
  );
}

export function ProjectEditorLayout() {
  return (
    <RequireAuth>
      <ProjectEditorLayoutInner />
    </RequireAuth>
  );
}

export default ProjectEditorLayout;

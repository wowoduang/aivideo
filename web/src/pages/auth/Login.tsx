import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Eye, EyeOff, Lock, Mail } from 'lucide-react';
import { AuthShell } from './AuthShell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/lib/auth';
import { fetchAuthStatus, loginWithPassword, mapBackendUser, type AuthStatusResponse } from '@/lib/api';
import { toast } from 'sonner';

function loginErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : '';
  if (message === 'invalid_credentials') return '邮箱或密码错误';
  if (message === 'no_users_registered') return '当前还没有本地账户，请先注册';
  if (message === 'invalid_email') return '请输入有效邮箱';
  return message || '登录失败';
}

export default function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const redirect = params.get('redirect') || '/dashboard';
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [authStatus, setAuthStatus] = useState<AuthStatusResponse | null>(null);

  useEffect(() => {
    let mounted = true;
    void fetchAuthStatus()
      .then((resp) => {
        if (!mounted) return;
        setAuthStatus(resp);
        if (!resp.has_users && resp.bootstrap_email) {
          setEmail(resp.bootstrap_email);
          setPassword(resp.bootstrap_password || '12345678');
        }
      })
      .catch(() => undefined);
    return () => { mounted = false; };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) return toast.error('请输入邮箱和密码');
    setLoading(true);
    try {
      const resp = await loginWithPassword(email, password);
      login(resp.token, mapBackendUser(resp.user));
      toast.success('登录成功');
      navigate(redirect, { replace: true });
    } catch (err) {
      toast.error(loginErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="欢迎回来，继续你的 AI 视频创作" subtitle="登录后可同步你的项目、脚本和任务历史。">
      <h3 className="text-base font-semibold">登录账户</h3>
      <p className="text-xs text-white/55 mt-1">使用本地账户登录工作台</p>
      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        {authStatus && !authStatus.has_users ? (
          <div className="rounded-lg border border-yellow-400/30 bg-yellow-400/10 p-3 text-xs text-yellow-100">
            当前还没有本地账户。你可以直接使用系统自动准备的本地演示账号登录，或点击下方注册链接创建自己的账号。
            {authStatus.bootstrap_email ? (
              <div className="mt-2 space-y-1 text-yellow-50/90">
                <div>邮箱：{authStatus.bootstrap_email}</div>
                <div>密码：{authStatus.bootstrap_password || '12345678'}</div>
              </div>
            ) : null}
          </div>
        ) : null}
        <div className="space-y-2">
          <Label htmlFor="email" className="text-xs text-white/70">邮箱地址</Label>
          <div className="relative">
            <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/40" />
            <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="yourname@company.com" className="pl-9 bg-[#0f1611] border-white/10 focus-visible:ring-[#46ec13]/30" />
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="password" className="text-xs text-white/70">登录密码</Label>
          <div className="relative">
            <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/40" />
            <Input id="password" type={showPwd ? 'text' : 'password'} autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="请输入密码" className="pl-9 pr-10 bg-[#0f1611] border-white/10 focus-visible:ring-[#46ec13]/30" />
            <button type="button" onClick={() => setShowPwd((v) => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-white/45 hover:text-white" aria-label={showPwd ? '隐藏密码' : '显示密码'}>{showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>
          </div>
        </div>
        <div className="flex items-center justify-between text-xs">
          <Link to="/register" className="text-[#46ec13] hover:underline">还没有账户？立即注册</Link>
          <Link to="/forgot-password" className="text-white/60 hover:text-white">忘记密码？</Link>
        </div>
        <Button type="submit" disabled={loading} className="w-full text-white font-semibold rounded-lg h-11" style={{ background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%)' }}>{loading ? '登录中…' : '登录工作台'}</Button>
      </form>
    </AuthShell>
  );
}

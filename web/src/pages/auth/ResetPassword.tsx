import { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Eye, EyeOff, Lock } from 'lucide-react';
import { AuthShell } from './AuthShell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { resetPassword } from '@/lib/api';
import { toast } from 'sonner';

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = useMemo(() => params.get('token') || '', [params]);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return toast.error('缺少重置令牌，请重新生成链接');
    if (password !== confirm) return toast.error('两次输入的密码不一致');
    setLoading(true);
    try {
      const resp = await resetPassword(token, password);
      toast.success(resp.message || '密码已重置');
      navigate('/login', { replace: true });
    } catch (err) {
      const msg = err instanceof Error ? err.message : '重置失败';
      toast.error(msg === 'invalid_or_expired_reset_token' ? '重置链接无效或已过期' : msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="设置新密码" subtitle="输入新密码后即可返回登录页重新登录。">
      <h3 className="text-base font-semibold">重置密码</h3>
      <p className="text-xs text-white/55 mt-1">请为你的账户设置一个新的登录密码</p>
      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <div className="space-y-2"><Label htmlFor="password" className="text-xs text-white/70">新密码</Label><div className="relative"><Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/40" /><Input id="password" type={showPwd ? 'text' : 'password'} minLength={6} required value={password} onChange={(e) => setPassword(e.target.value)} className="pl-9 pr-10 bg-[#0f1611] border-white/10 focus-visible:ring-[#46ec13]/30" /><button type="button" onClick={() => setShowPwd((v) => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-white/45 hover:text-white">{showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button></div></div>
        <div className="space-y-2"><Label htmlFor="confirm" className="text-xs text-white/70">确认新密码</Label><div className="relative"><Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/40" /><Input id="confirm" type={showPwd ? 'text' : 'password'} required value={confirm} onChange={(e) => setConfirm(e.target.value)} className="pl-9 bg-[#0f1611] border-white/10 focus-visible:ring-[#46ec13]/30" /></div></div>
        <Button type="submit" disabled={loading} className="w-full h-11 bg-[#46ec13] hover:bg-[#37c00c] text-[#060a07] font-semibold rounded-lg">{loading ? '提交中…' : '确认重置'}</Button>
      </form>
      <div className="mt-4 text-xs text-white/60 text-center"><Link to="/login" className="text-[#46ec13] hover:underline">返回登录</Link></div>
    </AuthShell>
  );
}

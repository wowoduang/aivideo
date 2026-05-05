import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Lock, Mail, User, Eye, EyeOff } from 'lucide-react';
import { AuthShell } from './AuthShell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/lib/auth';
import { mapBackendUser, registerWithPassword } from '@/lib/api';
import { toast } from 'sonner';

function registerErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : '';
  if (message === 'email_exists') return '该邮箱已注册，请直接登录';
  if (message === 'invalid_email') return '请输入有效邮箱';
  return message || '注册失败';
}

export default function RegisterPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) return toast.error('请完整填写邮箱和密码');
    if (password !== confirm) return toast.error('两次输入的密码不一致');
    setLoading(true);
    try {
      const resp = await registerWithPassword(username || email.split('@')[0], email, password);
      login(resp.token, mapBackendUser(resp.user));
      toast.success('注册成功，已自动登录');
      navigate('/dashboard', { replace: true });
    } catch (err) {
      toast.error(registerErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="创建账户，开启 AI 视频创作之旅" subtitle="注册后即可使用本地账号保存项目、脚本与任务记录。">
      <h3 className="text-base font-semibold">注册账户</h3>
      <p className="text-xs text-white/55 mt-1">填写信息创建 AIVideo 本地账号</p>
      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <div className="space-y-2"><Label htmlFor="username" className="text-xs text-white/70">昵称</Label><div className="relative"><User className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/40" /><Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="可选，将作为展示名" className="pl-9 bg-[#0f1611] border-white/10 focus-visible:ring-[#46ec13]/30" /></div></div>
        <div className="space-y-2"><Label htmlFor="email" className="text-xs text-white/70">邮箱地址</Label><div className="relative"><Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/40" /><Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="yourname@company.com" className="pl-9 bg-[#0f1611] border-white/10 focus-visible:ring-[#46ec13]/30" /></div></div>
        <div className="space-y-2"><Label htmlFor="password" className="text-xs text-white/70">登录密码</Label><div className="relative"><Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/40" /><Input id="password" type={showPwd ? 'text' : 'password'} required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="至少 6 位密码" className="pl-9 pr-10 bg-[#0f1611] border-white/10 focus-visible:ring-[#46ec13]/30" /><button type="button" onClick={() => setShowPwd((v) => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-white/45 hover:text-white">{showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button></div></div>
        <div className="space-y-2"><Label htmlFor="confirm" className="text-xs text-white/70">确认密码</Label><div className="relative"><Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/40" /><Input id="confirm" type={showPwd ? 'text' : 'password'} required value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="再次输入密码" className="pl-9 bg-[#0f1611] border-white/10 focus-visible:ring-[#46ec13]/30" /></div></div>
        <Button type="submit" disabled={loading} className="w-full text-[#060a07] font-semibold rounded-lg h-11 bg-[#46ec13] hover:bg-[#37c00c]">{loading ? '创建中…' : '创建账户'}</Button>
        <div className="text-xs text-center text-white/60">已有账户？<Link to="/login" className="text-[#46ec13] ml-1 hover:underline">立即登录</Link></div>
      </form>
    </AuthShell>
  );
}

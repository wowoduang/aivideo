import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Copy, KeyRound, Mail } from 'lucide-react';
import { AuthShell } from './AuthShell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { requestPasswordReset } from '@/lib/api';
import { toast } from 'sonner';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [resetUrl, setResetUrl] = useState('');
  const [expiresAt, setExpiresAt] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const resp = await requestPasswordReset(email);
      setSent(true);
      setResetUrl(resp.reset_url || '');
      setExpiresAt(resp.expires_at || '');
      toast.success(resp.message || '重置方式已生成');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '发送失败');
    } finally {
      setLoading(false);
    }
  };

  const copyLink = async () => {
    if (!resetUrl) return;
    await navigator.clipboard.writeText(`${window.location.origin}${resetUrl}`);
    toast.success('重置链接已复制');
  };

  return (
    <AuthShell title="忘记密码？我们来帮你找回" subtitle="输入注册邮箱，本地模式下会直接生成重置链接。">
      <div className="flex items-center gap-2 mb-4"><div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(70,236,19,0.15)', color: '#46ec13' }}><KeyRound className="w-4 h-4" /></div><div><h3 className="text-base font-semibold">重置密码</h3><p className="text-xs text-white/55">发送重置链接到你的邮箱</p></div></div>
      {sent ? (
        <div className="space-y-3 rounded-xl border border-[#46ec13]/40 bg-[#0d1a0e] p-5 text-sm">
          <div>如果该邮箱已注册，系统已生成密码重置方式。</div>
          {resetUrl ? (<><div className="break-all rounded-lg bg-black/20 px-3 py-2 text-[#46ec13]">{window.location.origin}{resetUrl}</div><div className="flex gap-2"><Button type="button" onClick={copyLink} variant="outline" className="border-white/15 bg-transparent text-white hover:bg-white/5"><Copy className="w-4 h-4 mr-1.5" /> 复制链接</Button><Link to={resetUrl}><Button type="button" className="bg-[#46ec13] hover:bg-[#37c00c] text-[#060a07]">立即重置</Button></Link></div>{expiresAt ? <div className="text-xs text-white/55">有效期至：{new Date(expiresAt).toLocaleString()}</div> : null}</>) : <div className="text-white/70">若未返回链接，请确认该邮箱已注册。</div>}
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4"><div className="space-y-2"><Label htmlFor="email" className="text-xs text-white/70">邮箱地址</Label><div className="relative"><Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/40" /><Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="yourname@company.com" className="pl-9 bg-[#0f1611] border-white/10 focus-visible:ring-[#46ec13]/30" /></div></div><Button type="submit" disabled={loading} className="w-full h-11 bg-[#46ec13] hover:bg-[#37c00c] text-[#060a07] font-semibold rounded-lg">{loading ? '生成中…' : '生成重置链接'}</Button></form>
      )}
      <div className="mt-4 text-xs text-white/60 text-center">想起来了？<Link to="/login" className="text-[#46ec13] ml-1 hover:underline">返回登录</Link></div>
    </AuthShell>
  );
}

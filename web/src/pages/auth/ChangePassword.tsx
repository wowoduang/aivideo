import { useState } from 'react';
import { Eye, EyeOff, Lock } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { AuthShell } from './AuthShell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { changePassword } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { toast } from 'sonner';

export default function ChangePasswordPage() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) return toast.error('两次输入的新密码不一致');
    setLoading(true);
    try {
      const resp = await changePassword(currentPassword, newPassword);
      toast.success(resp.message || '密码已更新，请重新登录');
      await logout();
      navigate('/login', { replace: true });
    } catch (err) {
      const msg = err instanceof Error ? err.message : '修改密码失败';
      toast.error(msg === 'invalid_current_password' ? '当前密码不正确' : msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="修改密码" subtitle="更新当前账户密码后，需要重新登录。">
      <h3 className="text-base font-semibold">安全设置</h3>
      <p className="text-xs text-white/55 mt-1">请输入当前密码并设置新的登录密码</p>
      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        {[{ id: 'currentPassword', label: '当前密码', value: currentPassword, setValue: setCurrentPassword }, { id: 'newPassword', label: '新密码', value: newPassword, setValue: setNewPassword }, { id: 'confirmPassword', label: '确认新密码', value: confirmPassword, setValue: setConfirmPassword }].map((field) => (
          <div className="space-y-2" key={field.id}><Label htmlFor={field.id} className="text-xs text-white/70">{field.label}</Label><div className="relative"><Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/40" /><Input id={field.id} type={showPwd ? 'text' : 'password'} minLength={6} required value={field.value} onChange={(e) => field.setValue(e.target.value)} className="pl-9 pr-10 bg-[#0f1611] border-white/10 focus-visible:ring-[#46ec13]/30" /><button type="button" onClick={() => setShowPwd((v) => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-white/45 hover:text-white">{showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button></div></div>
        ))}
        <Button type="submit" disabled={loading} className="w-full h-11 bg-[#46ec13] hover:bg-[#37c00c] text-[#060a07] font-semibold rounded-lg">{loading ? '提交中…' : '更新密码'}</Button>
      </form>
    </AuthShell>
  );
}

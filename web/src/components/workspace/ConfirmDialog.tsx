import { useEffect } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';

type ConfirmDialogProps = {
  open: boolean;
  title?: string;
  description?: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  tone?: 'danger' | 'default';
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  open,
  title = '确认操作',
  description,
  confirmText = '确定',
  cancelText = '取消',
  tone = 'danger',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
      if (e.key === 'Enter') onConfirm();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onCancel, onConfirm]);

  if (!open) return null;

  const accent = tone === 'danger' ? '#ef4444' : '#46ec13';
  const accentBg = tone === 'danger' ? 'bg-red-500 hover:bg-red-600 text-white' : 'bg-[#46ec13] hover:bg-[#37c00c] text-[#060a07]';

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        className="w-[420px] max-w-[92vw] rounded-2xl border border-white/10 bg-[#0b110d] px-7 py-6 shadow-[0_0_60px_-12px_rgba(0,0,0,0.8)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-start gap-3">
          <div
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full"
            style={{ background: `${accent}1a`, border: `1px solid ${accent}55` }}
          >
            <AlertTriangle className="h-5 w-5" style={{ color: accent }} />
          </div>
          <div className="flex-1">
            <h2 className="text-base font-semibold text-white">{title}</h2>
            {description ? (
              <div className="mt-2 text-sm text-white/65 leading-relaxed">{description}</div>
            ) : null}
          </div>
        </div>

        <div className="mt-6 flex items-center justify-end gap-2">
          <Button
            variant="outline"
            onClick={onCancel}
            className="h-9 rounded-lg border-white/10 bg-white/[0.03] text-white/80 hover:bg-white/10 hover:text-white"
          >
            {cancelText}
          </Button>
          <Button
            onClick={onConfirm}
            className={`h-9 rounded-lg font-semibold ${accentBg}`}
          >
            {confirmText}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmDialog;

import { useEffect, useState } from 'react';
import { Trash2 } from 'lucide-react';

type DeleteProgressModalProps = {
  open: boolean;
  projectName: string;
  /** Called when the simulated progress reaches 100%. */
  onFinished?: () => void;
  /** Total duration in ms; defaults to ~1.6s. */
  durationMs?: number;
};

export function DeleteProgressModal({
  open,
  projectName,
  onFinished,
  durationMs = 1600,
}: DeleteProgressModalProps) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (!open) {
      setProgress(0);
      return;
    }
    const start = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const pct = Math.min(100, ((now - start) / durationMs) * 100);
      setProgress(pct);
      if (pct < 100) {
        raf = requestAnimationFrame(step);
      } else {
        onFinished?.();
      }
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [open, durationMs, onFinished]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-[440px] max-w-[92vw] rounded-2xl border border-[#46ec13]/20 bg-[#0b110d] px-8 py-10 text-center shadow-[0_0_60px_-12px_rgba(70,236,19,0.25)]">
        <div className="relative mx-auto flex h-28 w-28 items-center justify-center">
          <span
            className="absolute inset-0 rounded-full border-2 border-[#46ec13]/20"
            aria-hidden
          />
          <span
            className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-[#46ec13]"
            aria-hidden
          />
          <span className="flex h-20 w-20 items-center justify-center rounded-full border border-[#46ec13]/40 bg-[#46ec13]/[0.06]">
            <Trash2 className="h-9 w-9 text-[#46ec13]" />
          </span>
        </div>

        <h2 className="mt-6 text-lg font-semibold text-white">正在删除项目</h2>
        <p className="mt-2 text-sm font-medium text-[#46ec13]">{projectName}</p>
        <p className="mt-3 text-xs text-white/55">
          需要同步清理相关文件，可能需要一点时间，请耐心等待。
        </p>

        <div className="mt-5 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
          <div
            className="h-full rounded-full bg-[#46ec13] transition-[width] duration-150 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>

        <p className="mt-3 text-[11px] text-white/40">系统正在安全删除媒体和脚本资源...</p>
      </div>
    </div>
  );
}

export default DeleteProgressModal;

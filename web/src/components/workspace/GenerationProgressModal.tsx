import { Check, Loader2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export type GenerationStepStatus = 'pending' | 'running' | 'done' | 'error';

export interface GenerationStep {
  key: string;
  label: string;
  status: GenerationStepStatus;
  hint?: string;
}

interface GenerationProgressModalProps {
  open: boolean;
  title?: string;
  subtitle?: string;
  steps: GenerationStep[];
  onCancel?: () => void;
  onClose?: () => void;
  cancelDisabled?: boolean;
  cancelLabel?: string;
  showStepList?: boolean;
}

export default function GenerationProgressModal({
  open,
  title = '正在请求大模型...',
  subtitle,
  steps,
  onCancel,
  onClose,
  cancelDisabled,
  cancelLabel = '取消生成',
  showStepList = true,
}: GenerationProgressModalProps) {
  if (!open) return null;

  const doneCount = steps.filter((s) => s.status === 'done').length;
  const total = steps.length || 1;
  const runningStep = steps.find((s) => s.status === 'running');
  const pct = Math.round((doneCount / total) * 100);
  const hint =
    runningStep?.hint || (runningStep ? 'AI 正在匹配画面，请稍候...' : 'AI 正在创作文案，请稍候…');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" />
      <div className="relative w-full max-w-xl bg-[#0B110D] border border-white/[0.08] rounded-2xl shadow-2xl overflow-hidden">
        <div className="px-8 pt-7 pb-4 flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-2 text-[#46ec13] text-sm">
              <span>智能分析</span>
              <span className="text-white/40">·</span>
              <span>智能分析</span>
            </div>
            <h2 className="text-xl font-semibold text-white">{title}</h2>
          </div>
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              className="text-white/60 hover:text-white text-sm flex items-center gap-1"
              title="关闭"
            >
              关闭
              <X className="w-4 h-4" />
            </button>
          ) : null}
        </div>

        <div className="px-8 pb-4">
          <p className="text-sm text-white/70 mb-3">{subtitle || hint}</p>
          <div className="h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
            <div
              className="h-full bg-[#46ec13] transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="flex items-center justify-between text-xs mt-2">
            <span className="text-white/50">进度</span>
            <span className="text-white/70">{pct}%</span>
          </div>
        </div>

        {showStepList ? (
          <div className="px-8 pb-4">
            <div className="h-px bg-white/5 mb-4" />
            <div className="text-sm text-white/70 mb-3">分析步骤：</div>
            <div className="space-y-2">
              {steps.map((s, idx) => (
                <div key={s.key} className="flex items-start gap-3 text-sm">
                  <span className="mt-0.5 w-5 h-5 shrink-0 flex items-center justify-center">
                    {s.status === 'done' ? (
                      <span className="w-5 h-5 rounded-full bg-[#46ec13] text-[#060a07] flex items-center justify-center">
                        <Check className="w-3 h-3" />
                      </span>
                    ) : s.status === 'running' ? (
                      <Loader2 className="w-4 h-4 text-[#46ec13] animate-spin" />
                    ) : (
                      <span className="text-white/40">{idx + 1}.</span>
                    )}
                  </span>
                  <div
                    className={cn(
                      'flex-1',
                      s.status === 'running' && 'text-[#46ec13]',
                      s.status === 'done' && 'text-white/80',
                      s.status === 'pending' && 'text-white/40',
                      s.status === 'error' && 'text-red-400'
                    )}
                  >
                    {s.label}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {onCancel ? (
          <div className="px-8 py-4 border-t border-white/[0.06] flex justify-end">
            <Button
              variant="outline"
              onClick={onCancel}
              disabled={cancelDisabled}
              className="border-white/[0.1] bg-transparent text-white hover:bg-white/[0.05]"
            >
              {cancelLabel}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

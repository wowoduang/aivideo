import { useEffect, useState } from 'react';
import { X, RefreshCcw, ArrowRight, Lightbulb } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface CopywritingPreviewDialogProps {
  open: boolean;
  initialText?: string;
  tokenIn?: number;
  tokenOut?: number;
  onClose: () => void;
  onRegenerate?: () => void;
  onConfirm: (text: string) => void;
  regenerating?: boolean;
}

export default function CopywritingPreviewDialog({
  open,
  initialText = '',
  tokenIn,
  tokenOut,
  onClose,
  onRegenerate,
  onConfirm,
  regenerating,
}: CopywritingPreviewDialogProps) {
  const [text, setText] = useState(initialText);

  useEffect(() => {
    if (open) setText(initialText);
  }, [open, initialText]);

  if (!open) return null;

  const resolvedIn = tokenIn ?? Math.max(Math.round(text.length * 3.8), 0);
  const resolvedOut = tokenOut ?? Math.max(Math.round(text.length * 1.68), 0);
  const total = resolvedIn + resolvedOut;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-4xl bg-[#0B110D] border border-white/[0.08] rounded-2xl shadow-2xl overflow-hidden max-h-[92vh] flex flex-col">
        {/* Header */}
        <div className="px-8 pt-7 pb-5 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-2xl font-semibold text-white">文案预览</h2>
            <p className="text-sm text-white/55 mt-1">
              AI 已生成文案，您可以预览并编辑后继续匹配画面
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-white/60 hover:text-white transition-colors p-1.5 rounded-lg hover:bg-white/[0.05]"
            aria-label="关闭"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Token stats */}
        <div className="mx-8 mb-5 rounded-xl border border-white/[0.06] bg-white/[0.02] px-6 py-5">
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <div className="text-xs text-white/55 mb-1.5">输入 Tokens</div>
              <div className="text-2xl font-semibold text-white font-mono">
                {resolvedIn.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="text-xs text-white/55 mb-1.5">输出 Tokens</div>
              <div className="text-2xl font-semibold text-white font-mono">
                {resolvedOut.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="text-xs text-white/55 mb-1.5">总计 Tokens</div>
              <div className="text-2xl font-semibold text-[#46ec13] font-mono">
                {total.toLocaleString()}
              </div>
            </div>
          </div>
        </div>

        {/* Body: label + editable content */}
        <div className="px-8 flex-1 min-h-0 flex flex-col">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-semibold">生成的文案内容</div>
            <div className="text-xs text-white/55">{text.length} 字符</div>
          </div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="flex-1 min-h-[260px] p-4 rounded-xl bg-white/[0.02] border border-white/[0.08] text-sm text-white/90 leading-relaxed resize-none focus:outline-none focus:border-[#46ec13]/50 focus:ring-1 focus:ring-[#46ec13]/20"
            placeholder="AI 生成的解说文案将显示在此处..."
          />
          <div className="mt-3 flex items-start gap-2 text-xs text-white/55">
            <Lightbulb className="w-3.5 h-3.5 text-amber-300 mt-0.5 shrink-0" />
            <span>
              您可以在上方编辑文案内容，修改后点击"继续匹配"将使用您编辑后的版本。
            </span>
          </div>
        </div>

        {/* Footer */}
        <div className="px-8 py-5 mt-5 border-t border-white/[0.06] flex items-center justify-between gap-3">
          {onRegenerate ? (
            <Button
              variant="outline"
              onClick={onRegenerate}
              disabled={regenerating}
              className="border-white/[0.1] bg-transparent text-white hover:bg-white/[0.05] gap-2 h-10 px-5"
            >
              <RefreshCcw className={regenerating ? 'w-4 h-4 animate-spin' : 'w-4 h-4'} />
              {regenerating ? '重新生成中…' : '重新生成'}
            </Button>
          ) : (
            <span />
          )}
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              onClick={onClose}
              className="text-white/80 hover:text-white hover:bg-white/[0.05] h-10 px-5"
            >
              取消
            </Button>
            <Button
              onClick={() => onConfirm(text)}
              className="bg-[#46ec13] hover:bg-[#37c00c] text-[#060a07] font-semibold rounded-lg px-6 h-10 brand-glow"
            >
              继续匹配 <ArrowRight className="w-4 h-4 ml-1" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

import { useState } from 'react';
import { X, Zap, Brain, Clapperboard } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export type InferenceMode = 'fast' | 'deep' | 'frame';

interface CreateProjectModalProps {
  open: boolean;
  onClose: () => void;
  onCreate: (name: string, mode: InferenceMode) => void;
}

type ModeDef = {
  key: InferenceMode;
  icon: React.ReactNode;
  iconBg: string;
  label: string;
  badge?: string;
  status?: string;
  cost: string;
  suited: string;
  hint?: string;
  headline: string;
  desc: string;
  feeFactor: string;
  disabled?: boolean;
};

const MODES: ModeDef[] = [
  {
    key: 'fast',
    icon: <Zap className="w-5 h-5" />,
    iconBg: 'rgba(234,179,8,0.12)',
    label: '快速推理',
    cost: '0.5x 视频时长',
    suited: '适用于有字幕的视频',
    headline: '平衡质量和速度，推荐日常使用',
    desc: '基于视频字幕进行快速分析，在辅助说明中填写剧情信息可获得最佳效果。处理速度快，资源消耗低，适合日常批量处理。',
    feeFactor: 'x1',
  },
  {
    key: 'deep',
    icon: <Brain className="w-5 h-5" />,
    iconBg: 'rgba(236,72,153,0.12)',
    label: '深度推理',
    badge: 'BETA',
    status: '开发中',
    cost: '1.2x 视频时长',
    suited: '适用所有类型的视频',
    hint: '深度推理仍在开发中，暂未开放',
    headline: '更细致的情节理解，适合长视频',
    desc: '综合字幕与画面进行深度语义分析，生成更贴合剧情的解说。适合电影解析、纪录片等长视频。',
    feeFactor: 'x2.5',
    disabled: true,
  },
  {
    key: 'frame',
    icon: <Clapperboard className="w-5 h-5" />,
    iconBg: 'rgba(59,130,246,0.12)',
    label: '逐帧推理',
    badge: 'BETA',
    status: '开发中',
    cost: '2.0x 视频时长',
    suited: '适用于没有字幕的视频',
    hint: '逐帧推理仍在开发中，暂未开放',
    headline: '无字幕视频的逐帧画面理解',
    desc: '对视频关键帧进行画面识别，无需原始字幕即可生成解说，适合纯画面、无台词的视频素材。',
    feeFactor: 'x4',
    disabled: true,
  },
];

export default function CreateProjectModal({ open, onClose, onCreate }: CreateProjectModalProps) {
  const [projectName, setProjectName] = useState('');
  const [mode, setMode] = useState<InferenceMode>('fast');

  if (!open) return null;

  const current = MODES.find((m) => m.key === mode) ?? MODES[0];

  const reset = () => {
    setProjectName('');
    setMode('fast');
  };

  const handleCreate = () => {
    if (!projectName.trim()) return;
    onCreate(projectName.trim(), mode);
    reset();
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={handleClose} />
      <div className="relative w-full max-w-3xl bg-[#0B110D] border border-white/[0.08] rounded-2xl shadow-2xl overflow-hidden max-h-[92vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
          <h2 className="text-lg font-semibold text-white">创建新项目</h2>
          <button
            onClick={handleClose}
            className="text-slate-400 hover:text-white transition-colors p-1 rounded-lg hover:bg-white/[0.05]"
            aria-label="关闭"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-6 overflow-y-auto">
          <div>
            <label className="block text-sm font-medium text-slate-200 mb-2">
              项目名称 <span className="text-[#46ec13]">*</span>
            </label>
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="输入项目名称"
              autoFocus
              className="w-full px-4 py-3 rounded-xl bg-white/[0.03] border border-white/[0.08] text-white placeholder-slate-500 text-sm focus:outline-none focus:border-[#46ec13]/50 focus:ring-1 focus:ring-[#46ec13]/20 transition-all"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-200 mb-3">
              推理模式 <span className="text-[#46ec13]">*</span>
            </label>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {MODES.map((m) => {
                const active = m.key === mode;
                return (
                  <button
                    key={m.key}
                    type="button"
                    onClick={() => !m.disabled && setMode(m.key)}
                    disabled={m.disabled}
                    className={cn(
                      'relative p-4 rounded-xl border text-left transition-all min-h-[170px] flex flex-col',
                      active
                        ? 'border-[#46ec13] bg-[#46ec13]/[0.06] shadow-[0_0_0_1px_rgba(70,236,19,0.35)]'
                        : 'border-white/[0.08] bg-white/[0.02] hover:border-white/20',
                      m.disabled && 'opacity-75 cursor-not-allowed'
                    )}
                  >
                    <span
                      className={cn(
                        'absolute top-3 right-3 w-4 h-4 rounded-full border flex items-center justify-center',
                        active ? 'border-[#46ec13]' : 'border-white/30'
                      )}
                    >
                      {active ? <span className="w-2.5 h-2.5 rounded-full bg-[#46ec13]" /> : null}
                    </span>
                    <div
                      className="w-9 h-9 rounded-lg flex items-center justify-center mb-3"
                      style={{ background: m.iconBg, color: active ? '#46ec13' : '#e2e8f0' }}
                    >
                      {m.icon}
                    </div>
                    <div className="flex items-center flex-wrap gap-1.5 mb-2">
                      <span className={cn('font-semibold text-base', active ? 'text-[#46ec13]' : 'text-white')}>
                        {m.label}
                      </span>
                      {m.badge ? (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-yellow-400/15 text-yellow-300 border border-yellow-400/25">
                          {m.badge}
                        </span>
                      ) : null}
                      {m.status ? (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-white/[0.06] text-slate-400 border border-white/10">
                          {m.status}
                        </span>
                      ) : null}
                    </div>
                    <p className="text-xs text-slate-300 mb-1">
                      耗时 <span className="text-slate-200">{m.cost}</span>
                    </p>
                    <p className="text-xs text-slate-400 mb-1">适用: {m.suited}</p>
                    {m.hint ? (
                      <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">{m.hint}</p>
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="rounded-xl border border-[#46ec13]/25 bg-[#46ec13]/[0.04] p-4">
            <div className="flex items-center gap-3 mb-3">
              <div
                className="w-9 h-9 rounded-lg flex items-center justify-center text-[#46ec13]"
                style={{ background: current.iconBg }}
              >
                {current.icon}
              </div>
              <div>
                <div className="text-[#46ec13] font-semibold text-base">{current.label}</div>
                <div className="text-xs text-slate-400 mt-0.5">
                  预计耗时: <span className="text-slate-200">{current.cost}</span>
                  <span className="mx-3 text-slate-600">|</span>
                  费用系数: <span className="text-slate-200">{current.feeFactor}</span>
                </div>
              </div>
            </div>
            <div className="text-sm text-white font-medium mb-1">{current.headline}</div>
            <p className="text-xs text-slate-400 leading-relaxed">{current.desc}</p>
          </div>
        </div>

        <div className="px-6 py-4 border-t border-white/[0.06] flex items-center justify-end gap-3">
          <Button
            variant="ghost"
            onClick={handleClose}
            className="text-slate-300 hover:text-white hover:bg-white/[0.05]"
          >
            取消
          </Button>
          <Button
            onClick={handleCreate}
            disabled={!projectName.trim()}
            className="bg-[#46ec13] hover:bg-[#37c00c] text-[#060a07] font-semibold rounded-lg disabled:opacity-40 disabled:pointer-events-none px-6"
          >
            创建
          </Button>
        </div>
      </div>
    </div>
  );
}

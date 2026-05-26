import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate, useOutletContext, useParams } from 'react-router-dom';
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  CheckCircle2,
  Clock3,
  Lock,
  RefreshCcw,
  Save,
  Sparkles,
  Unlock,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import {
  fetchHighlightSelection,
  saveHighlightSelection,
  type HighlightSelectionItem,
  type HighlightSelectionResponse,
} from '@/lib/api';
import { type Project } from '@/lib/projects-store';

type Ctx = { project?: Project };

type LoadState = 'idle' | 'loading' | 'ready' | 'error';

function formatSeconds(value: number): string {
  const total = Math.max(0, Number(value) || 0);
  const minutes = Math.floor(total / 60);
  const seconds = Math.floor(total % 60);
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    const remain = minutes % 60;
    return `${hours}:${String(remain).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function scorePercent(item: HighlightSelectionItem): number {
  const scores = item.scores || {};
  const raw =
    scores.highlight_score ??
    scores.story_score ??
    scores.information_score ??
    scores.emotion_score ??
    scores.visual_score ??
    0;
  const numeric = Number(raw);
  if (!Number.isFinite(numeric)) return 0;
  return Math.round(Math.max(0, Math.min(1, numeric > 1 ? numeric / 100 : numeric)) * 100);
}

function sortItems(items: HighlightSelectionItem[]): HighlightSelectionItem[] {
  return items.map((item, index) => ({ ...item, rank: index + 1, index: index + 1 }));
}

function selectionLabel(payload: HighlightSelectionResponse | null): string {
  if (!payload) return '尚未加载';
  if (payload.source === 'saved') return '已读取上次复选结果';
  return '基于最新高光候选生成';
}

export default function HighlightsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { project } = useOutletContext<Ctx>();
  const [state, setState] = useState<LoadState>('idle');
  const [payload, setPayload] = useState<HighlightSelectionResponse | null>(null);
  const [items, setItems] = useState<HighlightSelectionItem[]>([]);
  const [saving, setSaving] = useState(false);

  const reload = async () => {
    if (!id) return;
    setState('loading');
    try {
      const result = await fetchHighlightSelection(id);
      setPayload(result);
      setItems(sortItems(result.items || []));
      setState('ready');
    } catch (err) {
      setState('error');
      toast.error(err instanceof Error ? err.message : '加载高光候选失败');
    }
  };

  useEffect(() => {
    void reload();
  }, [id]);

  const stats = useMemo(() => {
    const selected = items.filter((item) => item.selected);
    const duration = selected.reduce((sum, item) => sum + (Number(item.duration) || 0), 0);
    const locked = items.filter((item) => item.locked).length;
    return { selectedCount: selected.length, total: items.length, duration, locked };
  }, [items]);

  if (!id || !project) {
    return <div className="container-workspace py-20 text-center text-white/60">项目不存在。</div>;
  }

  const patchItem = (rowId: string, patch: Partial<HighlightSelectionItem>) => {
    setItems((prev) => prev.map((item) => (item.id === rowId ? { ...item, ...patch } : item)));
  };

  const moveRow = (rowId: string, dir: -1 | 1) => {
    setItems((prev) => {
      const idx = prev.findIndex((item) => item.id === rowId);
      const target = idx + dir;
      if (idx < 0 || target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      [next[idx], next[target]] = [next[target], next[idx]];
      return sortItems(next);
    });
  };

  const selectAll = (checked: boolean) => {
    setItems((prev) => prev.map((item) => ({ ...item, selected: item.locked ? item.selected : checked })));
  };

  const save = async (next = items, message = '高光复选已保存') => {
    setSaving(true);
    try {
      const result = await saveHighlightSelection(id, sortItems(next), '前端高光复选页保存');
      setPayload(result.selection);
      setItems(sortItems(result.selection.items || []));
      toast.success(message);
      return true;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存高光复选失败');
      return false;
    } finally {
      setSaving(false);
    }
  };

  const continueToScript = async () => {
    const ok = await save(items, '高光复选已保存，进入脚本编辑');
    if (ok) navigate(`/projects/${id}/analysis`);
  };

  return (
    <div className="container-workspace py-8 pb-36">
      <header className="flex items-start justify-between mb-6 flex-wrap gap-4">
        <div>
          <h1 className="text-[2rem] font-bold">高光候选复选</h1>
          <p className="text-sm text-white/55 mt-1">项目：{project.name}</p>
          <p className="text-xs text-white/40 mt-2">{selectionLabel(payload)}。这里负责人工确认、排序和锁定，不直接改写视频裁剪时间。</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap ml-auto">
          <Button size="sm" variant="outline" onClick={() => navigate(`/projects/${id}/material`)} className="border-white/15 bg-transparent text-white hover:bg-white/5 h-10 px-4">
            <ArrowLeft className="w-4 h-4 mr-1.5" /> 返回素材
          </Button>
          <Button size="sm" variant="outline" onClick={reload} disabled={state === 'loading'} className="border-white/15 bg-transparent text-white hover:bg-white/5 h-10 px-4">
            <RefreshCcw className="w-4 h-4 mr-1.5" /> 刷新
          </Button>
          <Button size="sm" variant="outline" onClick={() => void save()} disabled={saving || items.length === 0} className="border-white/15 bg-transparent text-white hover:bg-white/5 h-10 px-4">
            <Save className="w-4 h-4 mr-1.5" /> 保存复选
          </Button>
          <Button size="sm" onClick={continueToScript} disabled={saving || stats.selectedCount === 0} className="bg-[#46ec13] hover:bg-[#37c00c] text-[#060a07] font-semibold h-10 px-4">
            进入脚本 <ArrowRight className="w-4 h-4 ml-1.5" />
          </Button>
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-4 mb-6">
        <MetricCard label="候选片段" value={String(stats.total)} hint="来自 Movie Story 高光结果" />
        <MetricCard label="已选择" value={`${stats.selectedCount}/${stats.total || 0}`} hint="只保存人工确认后的选择" accent />
        <MetricCard label="预计画面时长" value={formatSeconds(stats.duration)} hint="按 video_start / video_end 统计" />
        <MetricCard label="锁定片段" value={String(stats.locked)} hint="锁定后批量选择不会改变" />
      </section>

      <section className="rounded-2xl border border-white/[0.06] bg-white/[0.02] overflow-hidden">
        <div className="flex items-center justify-between px-6 py-5 border-b border-white/5 flex-wrap gap-3">
          <div>
            <h3 className="font-semibold text-base">候选列表</h3>
            <p className="text-xs text-white/45 mt-1">勾选保留、拖前后顺序用上移/下移控制，保存后会生成 highlight_selection 产物。</p>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={() => selectAll(true)} className="text-white/70 hover:text-white hover:bg-white/5">全选</Button>
            <Button size="sm" variant="ghost" onClick={() => selectAll(false)} className="text-white/70 hover:text-white hover:bg-white/5">全不选</Button>
          </div>
        </div>

        {state === 'loading' ? (
          <div className="py-20 text-center text-white/55">正在加载高光候选...</div>
        ) : items.length === 0 ? (
          <div className="py-20 flex flex-col items-center gap-4 text-sm text-white/60">
            <div className="w-14 h-14 rounded-full flex items-center justify-center bg-[#46ec13]/10 text-[#46ec13]"><Sparkles className="w-6 h-6" /></div>
            <div className="font-semibold text-white">暂无高光候选</div>
            <p className="max-w-lg text-center text-white/45">请先在「分析」页运行 Movie Story，生成高光列表后再回来复选。</p>
            <Button size="sm" onClick={() => navigate(`/projects/${id}/analysis`)} className="bg-[#46ec13] hover:bg-[#37c00c] text-[#060a07] font-semibold">去生成脚本</Button>
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {items.map((item, idx) => (
              <HighlightRow
                key={item.id}
                item={item}
                index={idx}
                isFirst={idx === 0}
                isLast={idx === items.length - 1}
                onPatch={(patch) => patchItem(item.id, patch)}
                onMove={moveRow}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function MetricCard({ label, value, hint, accent = false }: { label: string; value: string; hint: string; accent?: boolean }) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.025] p-4">
      <div className="text-xs text-white/45">{label}</div>
      <div className={cn('mt-2 text-2xl font-semibold', accent ? 'text-[#46ec13]' : 'text-white')}>{value}</div>
      <div className="mt-1 text-xs text-white/35">{hint}</div>
    </div>
  );
}

function HighlightRow({
  item,
  index,
  isFirst,
  isLast,
  onPatch,
  onMove,
}: {
  item: HighlightSelectionItem;
  index: number;
  isFirst: boolean;
  isLast: boolean;
  onPatch: (patch: Partial<HighlightSelectionItem>) => void;
  onMove: (id: string, dir: -1 | 1) => void;
}) {
  const reasons = item.selection_reasons || [];
  const score = scorePercent(item);
  return (
    <article className={cn('p-5 transition', item.selected ? 'bg-[#46ec13]/[0.025]' : 'bg-red-500/[0.025] opacity-75')}>
      <div className="grid gap-4 lg:grid-cols-[auto_1fr_auto] items-start">
        <div className="flex items-start gap-3">
          <Checkbox checked={item.selected} disabled={item.locked} onCheckedChange={(v) => onPatch({ selected: Boolean(v) })} />
          <div className="w-10 h-10 rounded-xl border border-white/10 bg-white/[0.035] flex items-center justify-center text-sm font-mono text-white/70">{index + 1}</div>
        </div>

        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="font-semibold text-white truncate">{item.title || `高光 ${index + 1}`}</h4>
            <span className={cn('text-[11px] px-2 py-0.5 rounded-full border', item.selected ? 'text-[#46ec13] border-[#46ec13]/30 bg-[#46ec13]/10' : 'text-red-300 border-red-300/20 bg-red-300/10')}>
              {item.selected ? '保留' : '排除'}
            </span>
            {item.locked ? <span className="text-[11px] px-2 py-0.5 rounded-full border border-blue-300/20 bg-blue-300/10 text-blue-200">已锁定</span> : null}
          </div>
          <div className="mt-2 flex items-center gap-3 text-xs text-white/45 flex-wrap">
            <span className="inline-flex items-center gap-1"><Clock3 className="w-3.5 h-3.5" /> {formatSeconds(item.video_start)} - {formatSeconds(item.video_end)}</span>
            <span>时长 {formatSeconds(item.duration)}</span>
            <span>推荐分 {score}%</span>
            <span>来源 {item.source_type || 'highlight'}</span>
          </div>
          {item.summary ? <p className="mt-3 text-sm text-white/80 leading-relaxed">{item.summary}</p> : null}
          {reasons.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {reasons.slice(0, 4).map((reason) => (
                <span key={reason} className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.035] px-2.5 py-1 text-[11px] text-white/60">
                  <CheckCircle2 className="w-3 h-3 text-[#46ec13]" /> {reason}
                </span>
              ))}
            </div>
          ) : item.reason ? (
            <p className="mt-3 text-xs text-white/45">推荐理由：{item.reason}</p>
          ) : null}
        </div>

        <div className="flex items-center justify-end gap-1">
          <IconButton title={item.locked ? '解除锁定' : '锁定片段'} onClick={() => onPatch({ locked: !item.locked })}>
            {item.locked ? <Lock className="w-3.5 h-3.5" /> : <Unlock className="w-3.5 h-3.5" />}
          </IconButton>
          <IconButton title="上移" disabled={isFirst} onClick={() => onMove(item.id, -1)}><ArrowUp className="w-3.5 h-3.5" /></IconButton>
          <IconButton title="下移" disabled={isLast} onClick={() => onMove(item.id, 1)}><ArrowDown className="w-3.5 h-3.5" /></IconButton>
        </div>
      </div>
    </article>
  );
}

function IconButton({ children, title, disabled, onClick }: { children: ReactNode; title: string; disabled?: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className="w-8 h-8 inline-flex items-center justify-center rounded-lg text-white/55 hover:text-white hover:bg-white/5 disabled:opacity-30 disabled:pointer-events-none"
    >
      {children}
    </button>
  );
}

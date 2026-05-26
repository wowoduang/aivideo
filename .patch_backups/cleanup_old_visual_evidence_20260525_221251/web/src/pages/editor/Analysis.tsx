import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate, useOutletContext, useParams } from 'react-router-dom';
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Copy,
  Download,
  Plus,
  RefreshCcw,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  Wand2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  type Project,
  type ScriptItem,
  updateProject,
} from '@/lib/projects-store';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import {
  createMovieStoryJob,
  createNarrationQualityReport,
  extractMovieStoryArtifacts,
  fetchNarrationWorkbench,
  fetchProjectResultsOverview,
  humanizeNarrationScript,
  saveNarrationScriptVersion,
  waitForJob,
  type NarrationQualityReport,
} from '@/lib/api';
import GenerationProgressModal, {
  type GenerationStep,
} from '@/components/workspace/GenerationProgressModal';

const normalizeMovieStoryStrategy = (value?: string | null): 'two_round' | 'two_round_visual' => {
  const normalized = String(value || 'two_round').trim();
  if (normalized === 'two_round_visual') {
    return 'two_round_visual';
  }
  return 'two_round';
};



function normalizeScriptItems(items: unknown[]): ScriptItem[] {
  if (!Array.isArray(items)) return [];
  return items.map((raw, index) => {
    const item = (raw || {}) as Record<string, unknown>;
    const timestamp = String(item.timestamp ?? '');
    const [ts0 = '', ts1 = ''] = timestamp.split('-');
    const startTime = String(ts0 || item.start || item.startTime || '');
    const endTime = String(ts1 || item.end || item.endTime || '');
    const narration = String(item.narration || item.new_content || item.content || item.text || '');
    const originalSubtitle = String(
      item.original_subtitle || item.originalSubtitle || item.subtitle_text || item.original || ''
    );
    return {
      id: String(item.id || item._id || item.segment_id || item.highlight_id || `s${index + 1}`),
      startTime: startTime || '00:00:00,000',
      endTime: endTime || '00:00:00,000',
      originalSubtitle,
      narration,
      raw: item,
    };
  });
}

type Ctx = { project?: Project };

function newItem(): ScriptItem {
  return {
    id: `s-${Date.now()}`,
    startTime: '00.00s',
    endTime: '05.00s',
    originalSubtitle: '',
    narration: '',
  };
}

function formatTime(value: string): string {
  const match = value.match(/^(\d+):(\d+):(\d+)[.,]?(\d*)$/);
  if (match) {
    const h = parseInt(match[1], 10);
    const m = parseInt(match[2], 10);
    const s = parseInt(match[3], 10);
    const ms = match[4] ? parseInt(match[4].slice(0, 3).padEnd(3, '0'), 10) : 0;
    const total = h * 3600 + m * 60 + s + ms / 1000;
    return `${total.toFixed(2)}s`;
  }
  if (/^\d+(\.\d+)?s?$/.test(value)) {
    return value.endsWith('s') ? value : `${value}s`;
  }
  return value;
}

function scorePct(value?: number): number {
  const raw = Number(value ?? 0);
  if (!Number.isFinite(raw)) return 0;
  return Math.max(0, Math.min(100, Math.round(raw * 100)));
}

export default function AnalysisPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { project } = useOutletContext<Ctx>();
  const [items, setItems] = useState<ScriptItem[]>(project?.scriptItems ?? []);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [editing, setEditing] = useState<{ id: string; field: keyof ScriptItem } | null>(null);
  const [rematching, setRematching] = useState(false);
  const [rematchSteps, setRematchSteps] = useState<GenerationStep[]>([]);
  const [rematchError, setRematchError] = useState('');
  const [qualityReport, setQualityReport] = useState<NarrationQualityReport | null>(null);
  const [qualityBusy, setQualityBusy] = useState(false);

  const persist = (next: ScriptItem[]) => {
    setItems(next);
    if (id) updateProject(id, { scriptItems: next });
  };

  useEffect(() => {
    setItems(project?.scriptItems ?? []);
  }, [project?.id, project?.scriptItems]);

  useEffect(() => {
    if (!id || !project) return;
    let cancelled = false;
    void fetchNarrationWorkbench(id)
      .then((workbench) => {
        if (cancelled) return;
        setQualityReport(workbench.quality_report);
        if ((project.scriptItems?.length || 0) === 0 && workbench.script_segments?.length) {
          const restored = normalizeScriptItems(workbench.script_segments);
          if (restored.length > 0) {
            persist(restored);
            toast.success(`已从解说工作台恢复 ${restored.length} 段脚本`);
          }
        }
      })
      .catch((err) => {
        console.error('load narration workbench failed', err);
      });
    return () => {
      cancelled = true;
    };
  }, [id, project?.id]);

  useEffect(() => {
    if (!id || !project) return;
    if ((project.scriptItems?.length || 0) > 0) return;
    let cancelled = false;
    void fetchProjectResultsOverview(id)
      .then((overview) => {
        if (cancelled) return;
        const restored = normalizeScriptItems(overview.script_items || []);
        if (restored.length > 0) {
          persist(restored);
          toast.success(`已从后端恢复 ${restored.length} 段脚本`);
        }
      })
      .catch((err) => {
        console.error('load project results failed', err);
      });
    return () => {
      cancelled = true;
    };
  }, [id, project?.id]);

  const stats = useMemo(() => {
    const total = items.length;
    const narrated = items.filter((i) => i.narration.trim().length > 0).length;
    const selectedCount = items.filter((i) => selected[i.id]).length;
    return { total, narrated, selectedCount };
  }, [items, selected]);

  if (!id || !project) {
    return (
      <div className="container-workspace py-20 text-center text-white/60">
        项目不存在。
      </div>
    );
  }

  const add = () => persist([...items, newItem()]);
  const remove = (rowId: string) => persist(items.filter((x) => x.id !== rowId));
  const patch = (rowId: string, patchObj: Partial<ScriptItem>) =>
    persist(items.map((x) => (x.id === rowId ? { ...x, ...patchObj } : x)));

  const copyRow = (rowId: string) => {
    const idx = items.findIndex((x) => x.id === rowId);
    if (idx === -1) return;
    const clone: ScriptItem = { ...items[idx], id: `s-${Date.now()}` };
    const next = [...items];
    next.splice(idx + 1, 0, clone);
    persist(next);
  };

  const moveRow = (rowId: string, dir: -1 | 1) => {
    const idx = items.findIndex((x) => x.id === rowId);
    const target = idx + dir;
    if (idx === -1 || target < 0 || target >= items.length) return;
    const next = [...items];
    [next[idx], next[target]] = [next[target], next[idx]];
    persist(next);
  };

  const exportJson = () => {
    const payload = items.map((s, i) => ({
      序号: i + 1,
      开始时间: s.startTime,
      结束时间: s.endTime,
      原始字幕: s.originalSubtitle,
      解说词: s.narration,
    }));
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${project.name || 'script'}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('脚本已导出');
  };

  const refreshQuality = async (saveReport = false) => {
    setQualityBusy(true);
    try {
      const report = await createNarrationQualityReport(id, items as unknown as Array<Record<string, any>>, { save_report: saveReport });
      setQualityReport(report);
      toast.success(saveReport ? '质量报告已保存到项目产物' : '质量评分已更新');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '质量评分失败');
    } finally {
      setQualityBusy(false);
    }
  };

  const applyHumanize = async () => {
    if (items.length === 0) {
      toast.error('请先生成或添加脚本');
      return;
    }
    setQualityBusy(true);
    try {
      const result = await humanizeNarrationScript(id, items as unknown as Array<Record<string, any>>, {
        persona: 'suspense',
        intensity: 0.65,
        save_version: true,
      });
      const nextItems = normalizeScriptItems(result.script_items);
      persist(nextItems);
      setQualityReport(result.quality_report);
      toast.success(`已完成真人口播优化，改写 ${result.changes.length} 段并保存版本`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '真人口播优化失败');
    } finally {
      setQualityBusy(false);
    }
  };

  const saveVersion = async () => {
    setQualityBusy(true);
    try {
      const label = `脚本版本 · ${new Date().toLocaleString()}`;
      await saveNarrationScriptVersion(id, items as unknown as Array<Record<string, any>>, label, '前端脚本编辑器手动保存', qualityReport || undefined);
      toast.success('脚本版本已保存，可在项目产物中回溯');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存版本失败');
    } finally {
      setQualityBusy(false);
    }
  };

  const setStepStatus = (key: string, status: GenerationStep['status'], hint?: string) => {
    setRematchSteps((prev) => prev.map((s) => (s.key === key ? { ...s, status, ...(hint ? { hint } : {}) } : s)));
  };

  const regenerate = async () => {
    if (!project.uploadedVideoPath) {
      toast.error('视频尚未上传到服务端，请先返回材料页重新上传视频');
      return;
    }
    const steps: GenerationStep[] = [
      { key: 'submit', label: '提交重新生成任务至后端', status: 'running' },
      { key: 'llm', label: '等待智能模型合成解说脚本', status: 'pending', hint: 'AI 正在匹配画面，请稍候...' },
      { key: 'save', label: '自动保存脚本', status: 'pending' },
    ];
    setRematchSteps(steps);
    setRematchError('');
    setRematching(true);
    try {
      const job = await createMovieStoryJob({
        project_id: id,
        video_path: project.uploadedVideoPath,
        subtitle_path: project.uploadedSubtitlePath || undefined,
        video_theme: project.name || '',
        narration_style: String(project.config?.narrationStyle || project.config?.style || 'general'),
        movie_story_strategy: normalizeMovieStoryStrategy(project.config?.movieStoryStrategy),
      movie_story_feature_mode: normalizeMovieStoryStrategy(project.config?.movieStoryStrategy),
        movie_story_mode: normalizeMovieStoryStrategy(project.config?.movieStoryStrategy),
        movie_story_enable_visual_evidence: normalizeMovieStoryStrategy(project.config?.movieStoryStrategy) === 'two_round_visual',
        generation_mode: 'balanced',
        visual_mode: project.config?.generationMode === 'manual' ? 'off' : 'auto',
        skip_llm: project.config?.generationMode === 'manual' || project.config?.skipLlm === true,
      });
      setStepStatus('submit', 'done');
      setStepStatus('llm', 'running');

      const snapshot = await waitForJob(job.task_id, {
        intervalMs: 2000,
        onTick: (snap) => {
          if (snap.message) setStepStatus('llm', 'running', snap.message);
        },
      });

      const artifacts = extractMovieStoryArtifacts(snapshot);
      const nextItems = normalizeScriptItems(artifacts.scriptItems);
      if (nextItems.length === 0) throw new Error('后端未返回解说脚本');
      setStepStatus('llm', 'done');
      setStepStatus('save', 'running');
      persist(nextItems);
      setStepStatus('save', 'done');
      toast.success(`重新生成完成，共 ${nextItems.length} 段脚本`);
      void refreshQuality(false);
      setTimeout(() => {
        setRematching(false);
        setRematchSteps([]);
        setRematchError('');
      }, 500);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '重新生成失败';
      setRematchError(msg);
      setRematchSteps((prev) => prev.map((s) => (s.status === 'running' ? { ...s, status: 'error', hint: msg } : s)));
      toast.error(msg);
    }
  };

  const next = () => {
    navigate(`/projects/${id}/dubbing`);
  };

  return (
    <div className="container-workspace py-8 pb-36">
      <header className="flex items-start justify-between mb-6 flex-wrap gap-4">
        <div>
          <h1 className="text-[2rem] font-bold">剪辑脚本编辑</h1>
          <p className="text-sm text-white/55 mt-1">项目：{project.name}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap ml-auto">
          <Button size="sm" variant="ghost" onClick={exportJson} className="text-white/80 hover:text-white hover:bg-white/5 h-10 px-4">
            <Download className="w-4 h-4 mr-1.5" /> 导出
          </Button>
          <Button size="sm" variant="outline" onClick={saveVersion} disabled={qualityBusy} className="border-white/15 bg-transparent text-white hover:bg-white/5 h-10 px-4">
            <Save className="w-4 h-4 mr-1.5" /> 保存版本
          </Button>
          <Button size="sm" variant="outline" onClick={() => refreshQuality(true)} disabled={qualityBusy} className="border-white/15 bg-transparent text-white hover:bg-white/5 h-10 px-4">
            <ShieldCheck className="w-4 h-4 mr-1.5" /> 质量评分
          </Button>
          <Button size="sm" variant="outline" onClick={applyHumanize} disabled={qualityBusy} className="border-white/15 bg-transparent text-white hover:bg-white/5 h-10 px-4">
            <Wand2 className="w-4 h-4 mr-1.5" /> 真人口播优化
          </Button>
          <Button size="sm" variant="outline" onClick={regenerate} className="border-white/15 bg-transparent text-white hover:bg-white/5 h-10 px-4">
            <Sparkles className="w-4 h-4 mr-1.5" /> 重新生成
          </Button>
        </div>
      </header>

      <QualityPanel report={qualityReport} loading={qualityBusy} selectedCount={stats.selectedCount} />

      <section className="rounded-2xl border border-white/[0.06] bg-white/[0.02]">
        <div className="flex items-center justify-between px-6 py-5 border-b border-white/5 flex-wrap gap-3">
          <div className="flex items-baseline gap-3">
            <h3 className="font-semibold text-base">剪辑脚本</h3>
            <span className="text-xs text-white/50">共 {stats.total} 项</span>
            {stats.narrated > 0 ? <span className="text-xs text-[#46ec13]">已填解说 {stats.narrated}</span> : null}
          </div>
          <Button size="sm" onClick={add} variant="ghost" className="text-white/70 hover:text-white hover:bg-white/5">
            <Plus className="w-4 h-4 mr-1" /> 添加
          </Button>
        </div>

        {items.length === 0 ? (
          <div className="py-16 flex flex-col items-center justify-center gap-4 text-sm">
            <div className="w-14 h-14 rounded-full flex items-center justify-center" style={{ background: 'rgba(70,236,19,0.12)', color: '#46ec13' }}>
              <Sparkles className="w-6 h-6" />
            </div>
            <div className="font-semibold">还没有脚本数据</div>
            <p className="text-white/50 max-w-md text-center">点击「重新生成」可再次匹配画面，或点击下方按钮手动添加第一项。</p>
            <div className="flex gap-2">
              <Button size="sm" onClick={add} variant="outline" className="border-white/15 bg-transparent text-white hover:bg-white/5">
                <Plus className="w-4 h-4 mr-1" /> 添加第一项
              </Button>
              <Button size="sm" onClick={regenerate} className="bg-[#46ec13] hover:bg-[#37c00c] text-[#060a07] font-semibold">
                <RefreshCcw className="w-4 h-4 mr-1" /> 重新生成
              </Button>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[1100px]">
              <thead className="text-white/50 text-left">
                <tr>
                  <th className="px-5 py-3 font-normal w-10">
                    <Checkbox
                      checked={items.length > 0 && items.every((i) => selected[i.id])}
                      onCheckedChange={(v) => {
                        const nextSel: Record<string, boolean> = {};
                        if (v) items.forEach((i) => (nextSel[i.id] = true));
                        setSelected(nextSel);
                      }}
                    />
                  </th>
                  <th className="px-3 py-3 font-normal w-14">序号</th>
                  <th className="px-3 py-3 font-normal w-28">开始时间</th>
                  <th className="px-3 py-3 font-normal w-28">结束时间</th>
                  <th className="px-3 py-3 font-normal w-[28%]">原始字幕</th>
                  <th className="px-3 py-3 font-normal">解说词</th>
                  <th className="px-3 py-3 font-normal w-36 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row, idx) => {
                  const isChecked = !!selected[row.id];
                  return (
                    <tr key={row.id} className={cn('border-t border-white/5 align-middle transition-colors', isChecked ? 'bg-[#46ec13]/[0.04]' : 'hover:bg-white/[0.02]')}>
                      <td className="px-5 py-5">
                        <Checkbox checked={isChecked} onCheckedChange={(v) => setSelected((s) => ({ ...s, [row.id]: Boolean(v) }))} />
                      </td>
                      <td className="px-3 py-5 text-white/70 font-mono">{idx + 1}</td>
                      <EditableCell value={row.startTime} display={formatTime(row.startTime)} isEditing={editing?.id === row.id && editing.field === 'startTime'} onEditStart={() => setEditing({ id: row.id, field: 'startTime' })} onEditEnd={() => setEditing(null)} onChange={(v) => patch(row.id, { startTime: v })} displayClass="text-[#46ec13] font-mono" cellClass="w-28" />
                      <EditableCell value={row.endTime} display={formatTime(row.endTime)} isEditing={editing?.id === row.id && editing.field === 'endTime'} onEditStart={() => setEditing({ id: row.id, field: 'endTime' })} onEditEnd={() => setEditing(null)} onChange={(v) => patch(row.id, { endTime: v })} displayClass="text-white/90 font-mono" cellClass="w-28" />
                      <EditableCell value={row.originalSubtitle} display={row.originalSubtitle || '—'} isEditing={editing?.id === row.id && editing.field === 'originalSubtitle'} onEditStart={() => setEditing({ id: row.id, field: 'originalSubtitle' })} onEditEnd={() => setEditing(null)} onChange={(v) => patch(row.id, { originalSubtitle: v })} displayClass={row.originalSubtitle ? 'text-white/85 leading-relaxed' : 'text-white/30'} multiline />
                      <EditableCell value={row.narration} display={row.narration || '—'} isEditing={editing?.id === row.id && editing.field === 'narration'} onEditStart={() => setEditing({ id: row.id, field: 'narration' })} onEditEnd={() => setEditing(null)} onChange={(v) => patch(row.id, { narration: v })} displayClass={row.narration ? 'text-white/90 leading-relaxed' : 'text-white/30'} multiline />
                      <td className="px-3 py-5">
                        <div className="flex items-center justify-end gap-1">
                          <RowIcon title="复制行" onClick={() => copyRow(row.id)}><Copy className="w-3.5 h-3.5" /></RowIcon>
                          <RowIcon title="上移" disabled={idx === 0} onClick={() => moveRow(row.id, -1)}><ArrowUp className="w-3.5 h-3.5" /></RowIcon>
                          <RowIcon title="下移" disabled={idx === items.length - 1} onClick={() => moveRow(row.id, 1)}><ArrowDown className="w-3.5 h-3.5" /></RowIcon>
                          <RowIcon title="删除" danger onClick={() => remove(row.id)}><Trash2 className="w-3.5 h-3.5" /></RowIcon>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <GenerationProgressModal
        open={rematching}
        title={rematchError ? '生成失败' : '正在请求大模型...'}
        subtitle={rematchError || '智能分析 · 智能分析'}
        steps={rematchSteps}
        cancelLabel={rematchError ? '关闭' : '取消分析'}
        onCancel={() => {
          setRematching(false);
          setRematchSteps([]);
          setRematchError('');
          if (!rematchError) toast.info('已取消匹配');
        }}
      />
      <div className="fixed bottom-0 left-0 right-0 z-30 border-t border-white/[0.06] bg-[#0a0a0f]/95 backdrop-blur">
        <div className="container-workspace py-4 flex items-center justify-between flex-wrap gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate(`/projects/${id}/material`)} className="text-white/90 hover:text-white hover:bg-white/5 h-10 px-3">
            <ArrowLeft className="w-4 h-4 mr-1.5" /> 返回
          </Button>
          <div className="flex items-center gap-3 flex-wrap">
            <Button variant="outline" size="sm" onClick={() => { updateProject(id, { currentStep: 'upload' }); navigate(`/projects/${id}/material`); }} className="border-white/15 bg-transparent text-white hover:bg-white/5 h-10 px-4">
              <RefreshCcw className="w-4 h-4 mr-1.5" /> 重新上传
            </Button>
            <Button size="sm" onClick={next} className="bg-[#46ec13] hover:bg-[#37c00c] text-[#060a07] font-semibold h-10 px-5 brand-glow">
              <ArrowRight className="w-4 h-4 mr-1.5" /> 下一步
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function QualityPanel({ report, loading, selectedCount }: { report: NarrationQualityReport | null; loading: boolean; selectedCount: number }) {
  if (!report) {
    return (
      <section className="mb-6 rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5 text-sm text-white/55">
        解说质量报告尚未生成。点击「质量评分」可检查证据支撑、真人口播感和 TTS 时长匹配。
      </section>
    );
  }
  const summary = report.summary;
  return (
    <section className="mb-6 rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-sm text-white/50 mb-1">证据驱动解说质量</div>
          <div className="text-2xl font-semibold">综合 {scorePct(summary.overall_score)} 分</div>
          <p className="text-xs text-white/45 mt-1">覆盖 {summary.segment_count || 0} 段脚本 / {summary.evidence_count || 0} 条证据{selectedCount ? ` · 当前选中 ${selectedCount} 段` : ''}</p>
        </div>
        {loading ? <span className="text-xs text-[#46ec13]">正在计算...</span> : null}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-5">
        <QualityMetric label="准确性" value={summary.factuality_score} />
        <QualityMetric label="时间线" value={summary.timeline_score} />
        <QualityMetric label="真人感" value={summary.humanlike_score} />
        <QualityMetric label="配音匹配" value={summary.tts_alignment_score} />
        <QualityMetric label="完整度" value={summary.completeness_score} />
      </div>
      {(summary.blocking_issues?.length || report.unsupported_claims.length || report.next_actions.length) ? (
        <div className="mt-5 grid md:grid-cols-2 gap-4 text-xs">
          <div className="rounded-xl bg-black/20 border border-white/[0.06] p-4">
            <div className="text-white/70 mb-2">风险提醒</div>
            <ul className="space-y-1 text-white/50 list-disc list-inside">
              {(summary.blocking_issues || []).slice(0, 3).map((x) => <li key={x}>{x}</li>)}
              {report.unsupported_claims.slice(0, 2).map((x, idx) => <li key={`${x.segment_id || 'claim'}-${idx}`}>无证据强判断：{String(x.text || '')}</li>)}
              {!(summary.blocking_issues?.length || report.unsupported_claims.length) ? <li>未发现阻断项</li> : null}
            </ul>
          </div>
          <div className="rounded-xl bg-black/20 border border-white/[0.06] p-4">
            <div className="text-white/70 mb-2">下一步建议</div>
            <ul className="space-y-1 text-white/50 list-disc list-inside">
              {report.next_actions.slice(0, 4).map((x) => <li key={x}>{x}</li>)}
            </ul>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function QualityMetric({ label, value }: { label: string; value?: number }) {
  const pct = scorePct(value);
  return (
    <div className="rounded-xl bg-black/20 border border-white/[0.06] p-3">
      <div className="text-xs text-white/45 mb-1">{label}</div>
      <div className="text-lg font-semibold text-white">{pct}</div>
      <div className="h-1.5 rounded-full bg-white/10 mt-2 overflow-hidden">
        <div className="h-full bg-[#46ec13]" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function EditableCell({
  value,
  display,
  isEditing,
  onEditStart,
  onEditEnd,
  onChange,
  displayClass,
  cellClass,
  multiline,
}: {
  value: string;
  display: string;
  isEditing: boolean;
  onEditStart: () => void;
  onEditEnd: () => void;
  onChange: (v: string) => void;
  displayClass?: string;
  cellClass?: string;
  multiline?: boolean;
}) {
  return (
    <td className={cn('px-3 py-5', cellClass)}>
      {isEditing ? (
        multiline ? (
          <textarea autoFocus value={value} onChange={(e) => onChange(e.target.value)} onBlur={onEditEnd} className="w-full min-h-[60px] bg-[#0f1611] border border-[#46ec13]/40 rounded-md px-2 py-1.5 text-sm text-white/90 resize-none focus:outline-none" />
        ) : (
          <input autoFocus value={value} onChange={(e) => onChange(e.target.value)} onBlur={onEditEnd} onKeyDown={(e) => { if (e.key === 'Enter') onEditEnd(); }} className="w-full bg-[#0f1611] border border-[#46ec13]/40 rounded-md h-8 px-2 text-xs font-mono text-white focus:outline-none" />
        )
      ) : (
        <button type="button" onClick={onEditStart} className={cn('text-left w-full cursor-text', displayClass)}>
          {display}
        </button>
      )}
    </td>
  );
}

function RowIcon({ onClick, title, disabled, danger, children }: { onClick: () => void; title: string; disabled?: boolean; danger?: boolean; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        'w-8 h-8 rounded-md flex items-center justify-center transition',
        disabled ? 'text-white/20 cursor-not-allowed' : danger ? 'text-white/55 hover:text-red-400 hover:bg-white/5' : 'text-white/55 hover:text-white hover:bg-white/5'
      )}
    >
      {children}
    </button>
  );
}

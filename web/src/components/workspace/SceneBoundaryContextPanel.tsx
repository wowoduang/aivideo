import { useMemo, useState } from 'react';
import { AlertTriangle, RefreshCcw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  previewSceneBoundaryContext,
  type SceneBoundaryContextPreviewResponse,
} from '../../lib/scene-boundary-context-api';

type SceneBoundaryContextPanelProps = {
  mediaPath: string;
  subtitleSegments: Array<Record<string, unknown>>;
};

function formatSeconds(value: unknown): string {
  const seconds = Number(value || 0);
  if (!Number.isFinite(seconds)) return '00:00';
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const remain = total % 60;
  return `${String(minutes).padStart(2, '0')}:${String(remain).padStart(2, '0')}`;
}

function normalizeNumberInput(value: string, fieldName: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${fieldName} 必须是数字`);
  }
  return parsed;
}

function formatGeneratedAt(value: Date | null): string {
  if (!value) return '未生成';
  return value.toLocaleTimeString();
}

export function SceneBoundaryContextPanel({
  mediaPath,
  subtitleSegments,
}: SceneBoundaryContextPanelProps): JSX.Element {
  const [result, setResult] = useState<SceneBoundaryContextPreviewResponse | null>(null);
  const [targetSceneCount, setTargetSceneCount] = useState('80');
  const [isRunning, setIsRunning] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [generatedAt, setGeneratedAt] = useState<Date | null>(null);
  const [runCount, setRunCount] = useState(0);

  const subtitleCount = subtitleSegments.length;
  const hasMediaPath = mediaPath.trim().length > 0;
  const canRun = hasMediaPath && subtitleCount > 0 && !isRunning;

  const summaryText = useMemo(() => {
    if (!result) return '尚未生成场景边界';
    const total = Number(result.scene_source?.scene_count_total || result.scene_count || 0);
    return `统一场景 ${total} 个 · 输出 ${result.scene_count} 个`;
  }, [result]);

  const handleGenerate = async (): Promise<void> => {
    setErrorMessage('');
    setIsRunning(true);
    setResult(null);

    try {
      if (!mediaPath.trim()) {
        throw new Error('缺少视频路径，不能生成场景边界');
      }
      if (subtitleSegments.length === 0) {
        throw new Error('缺少字幕片段，不能生成场景边界');
      }

      const target = normalizeNumberInput(targetSceneCount, '输出场景上限');

      const payload = await previewSceneBoundaryContext({
        video_path: mediaPath,
        subtitle_segments: subtitleSegments,
        target_scene_count: target,
      });
      if (!payload.scene_boundary_context.trim()) {
        throw new Error('后端返回的 scene_boundary_context 为空');
      }
      setResult(payload);
      setGeneratedAt(new Date());
      setRunCount((current) => current + 1);
    } catch (error) {
      const message = error instanceof Error ? error.message : '生成场景边界失败';
      setErrorMessage(message);
      setGeneratedAt(null);
      setResult(null);
    } finally {
      setIsRunning(false);
    }
  };

  const buttonLabel = result ? '重新生成场景边界' : '生成场景边界';

  return (
    <section className="rounded-2xl border border-white/10 bg-[#090b10] p-5 shadow-[0_0_0_1px_rgba(255,255,255,0.02)]">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="text-base font-semibold text-white">场景边界</div>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">
            使用统一场景切分链路生成 scene_boundary_context。这里展示场景时间范围、关键帧锚点和覆盖字幕；不做人名识别，不写剧情解释。
          </p>
        </div>
        <Button
          type="button"
          disabled={!canRun}
          onClick={() => {
            void handleGenerate();
          }}
          className="bg-[#39ff14] px-5 font-semibold text-black hover:bg-[#39ff14]/90 disabled:bg-slate-800 disabled:text-slate-500"
        >
          {isRunning ? (
            <>
              <RefreshCcw className="mr-2 h-4 w-4 animate-spin" />
              生成中
            </>
          ) : (
            buttonLabel
          )}
        </Button>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <label className="text-xs font-medium text-slate-400">
          输出场景上限
          <input
            className="mt-1 w-full rounded-xl border border-white/10 bg-[#11141a] px-3 py-2 text-sm text-white outline-none focus:border-[#39ff14]/70"
            type="number"
            min={1}
            max={300}
            value={targetSceneCount}
            onChange={(event) => setTargetSceneCount(event.target.value)}
          />
        </label>
      </div>

      <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-xs leading-5 text-slate-400">
        <div>视频路径：{hasMediaPath ? mediaPath : '未提供'}</div>
        <div>字幕片段：{subtitleCount} 条</div>
        <div>当前结果：{summaryText}</div>
        <div>生成状态：第 {runCount} 次 · {formatGeneratedAt(generatedAt)}</div>
      </div>

      {!hasMediaPath || subtitleCount === 0 ? (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>需要先上传视频并生成或上传字幕，才能生成场景边界。</div>
        </div>
      ) : null}

      {errorMessage ? (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <pre className="whitespace-pre-wrap font-sans">{errorMessage}</pre>
        </div>
      ) : null}

      {isRunning ? (
        <div className="mt-4 rounded-xl border border-[#39ff14]/30 bg-[#39ff14]/10 p-3 text-xs text-[#c8ffc0]">
          正在调用统一场景切分链路并生成 scene_boundary_context...
        </div>
      ) : null}

      {result ? (
        <div className="mt-4 space-y-3">
          <div className="grid gap-2 md:grid-cols-3">
            {result.scene_boundaries.slice(0, 6).map((scene) => (
              <div key={scene.scene_id} className="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-xs">
                <div className="font-semibold text-[#39ff14]">{scene.scene_id}</div>
                <div className="mt-1 text-slate-400">
                  {formatSeconds(scene.start)}~{formatSeconds(scene.end)} · {Math.round(Number(scene.duration || 0))}秒
                </div>
                <div className="mt-1 text-slate-500">
                  字幕 {scene.subtitle_count ?? 0} 条 · 关键帧 {scene.keyframe_count ?? 0} 个
                </div>
              </div>
            ))}
          </div>

          <textarea
            className="h-80 w-full rounded-xl border border-[#39ff14]/30 bg-black p-3 font-mono text-xs leading-5 text-[#c8ffc0] outline-none"
            readOnly
            value={result.scene_boundary_context}
          />
        </div>
      ) : null}
    </section>
  );
}

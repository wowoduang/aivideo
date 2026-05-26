import { useEffect, useRef, useState } from 'react';
import { useNavigate, useOutletContext, useParams } from 'react-router-dom';
import { CheckCircle2, RefreshCcw, Save, Wand2, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  type Project,
  type ScriptItem,
  updateProject,
} from '@/lib/projects-store';
import { toast } from 'sonner';
import { normalizePhase, type Phase as ProjectPhase } from '@/lib/project-flow';
import {
  createMovieStoryJob,
  createSubtitleJob,
  extractMovieStoryArtifacts,
  extractSubtitleArtifact,
  readSubtitleLines,
  uploadSubtitle,
  uploadVideo,
  cropUploadedVideo,
  waitForJob,
  type SubtitleLine,
} from '@/lib/api';
import VideoUploadStep from '@/components/workspace/VideoUploadStep';
import SubtitleStep from '@/components/workspace/SubtitleStep';
import ConfigStep, {
  type ConfigFormValue,
} from '@/components/workspace/ConfigStep';
import CopywritingPreviewDialog from '@/components/workspace/CopywritingPreviewDialog';
import GenerationProgressModal, {

  type GenerationStep,
} from '@/components/workspace/GenerationProgressModal';
import { SpeakerContextPanel } from '../../components/workspace/SpeakerContextPanel';
import { SceneBoundaryContextPanel } from '../../components/workspace/SceneBoundaryContextPanel';

const normalizeMovieStoryStrategy = (value?: string | null): 'two_round' | 'two_round_visual' => {
  const normalized = String(value || 'two_round').trim();
  if (normalized === 'two_round_visual') {
    return 'two_round_visual';
  }
  return 'two_round';
};



type Ctx = { project?: Project };
type Phase = ProjectPhase;

type AsrBackend =
  | 'videocaptioner'
  | 'bailian_qwen3_filetrans'
  | 'bailian_qwen3_flash'
  | 'bailian_fun_asr'
  | 'whisper';

type ActiveJob = {
  type: 'subtitle' | 'movie_story_script';
  taskId: string;
  backend?: string;
  model?: string;
};

const ASR_BACKENDS: Array<{ key: AsrBackend; label: string; desc: string; backend: string; model?: string }> = [
  { key: 'videocaptioner', label: '高质量 · VideoCaptioner', desc: '时间轴更稳，适合正式字幕', backend: 'videocaptioner_shell' },
  { key: 'bailian_qwen3_filetrans', label: '阿里 · qwen3 filetrans', desc: '文件转写，优先用于较长视频', backend: 'bailian', model: 'qwen3-asr-flash-filetrans' },
  { key: 'bailian_qwen3_flash', label: '阿里 · qwen3 flash', desc: '速度快，时间轴不稳定时仅建议预览', backend: 'bailian', model: 'qwen3-asr-flash' },
  { key: 'bailian_fun_asr', label: '阿里 · Fun-ASR（文本测试）', desc: '仅测试文字准确率；当前后端不保证稳定时间轴，失败可切换其他模型', backend: 'bailian', model: 'fun-asr' },
  { key: 'whisper', label: '本地 · Whisper', desc: '本地兜底，速度取决于电脑配置', backend: 'faster_whisper' },
];

function normalizeAsrBackend(value: unknown): AsrBackend {
  const raw = String(value || '').trim().toLowerCase();
  if (raw === 'bailian_qwen3_filetrans' || raw === 'qwen3-asr-flash-filetrans') return 'bailian_qwen3_filetrans';
  if (raw === 'bailian' || raw === 'bailian_flash' || raw === 'bailian_qwen3_flash' || raw === 'qwen3-asr-flash') return 'bailian_qwen3_flash';
  if (raw === 'bailian_fun_asr' || raw === 'fun-asr' || raw === 'fun_asr') return 'bailian_fun_asr';
  if (raw === 'whisper' || raw === 'faster_whisper' || raw === 'faster-whisper') return 'whisper';
  return 'videocaptioner';
}

const STEPS: Array<{ key: Phase; label: string }> = [
  { key: 'upload', label: '上传视频' },
  { key: 'subtitle', label: '字幕识别与编辑' },
  { key: 'config', label: '生成配置' },
  { key: 'generate', label: '生成结果' },
];

const defaultConfig: ConfigFormValue = {
  editMode: 'smart_insert',
  originalRatio: 35,
  videoLanguage: 'zh',
  narrationLanguage: 'zh',
  generationMode: 'auto',
  movieStoryStrategy: 'two_round',
  speechSpeed: 'moderate',
  wordCount: 'default',
  perspective: 'third',
  narrationStyle: 'default',
  scriptType: 'standard',
  temperature: 0.7,
  ttsEngine: 'edge-tts',
  voiceRole: 'female_gentle',
  speed: 1,
  aspectRatio: '16:9',
  videoQuality: 'high',
  subtitleFont: 'default',
  subtitleSize: 24,
  subtitleEnabled: true,
};

function resolveHighlightSelectivity(editMode: ConfigFormValue['editMode'], originalRatio: number): 'loose' | 'balanced' | 'strict' {
  if (editMode === 'original_only') return 'loose';
  if (editMode === 'commentary_only') return 'strict';
  if (originalRatio >= 50) return 'loose';
  if (originalRatio <= 30) return 'strict';
  return 'balanced';
}

function resolveGenerationMode(config: ConfigFormValue): 'fast' | 'balanced' | 'quality' {
  if (config.editMode === 'original_only') return 'fast';
  if (config.wordCount === '1200-1800' || config.wordCount === '1800-2500' || config.wordCount === '2500-3500') {
    return 'quality';
  }
  return 'balanced';
}

function normalizeScriptItems(items: any[]): ScriptItem[] {
  if (!Array.isArray(items)) return [];
  return items.map((item, index) => {
    const startTime = String(item?.timestamp?.split('-')?.[0] || item?.start || item?.startTime || '');
    const endTime = String(item?.timestamp?.split('-')?.[1] || item?.end || item?.endTime || '');
    const narration = String(item?.narration || item?.new_content || item?.content || item?.text || '');
    const originalSubtitle = String(
      item?.original_subtitle || item?.originalSubtitle || item?.subtitle_text || item?.original || ''
    );
    return {
      id: String(item?.id || item?._id || `s${index + 1}`),
      startTime: startTime || '00:00:00,000',
      endTime: endTime || '00:00:00,000',
      originalSubtitle,
      narration,
    };
  });
}

function secondsToSrtTime(seconds: number): string {
  const safe = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
  const h = Math.floor(safe / 3600);
  const m = Math.floor((safe % 3600) / 60);
  const s = Math.floor(safe % 60);
  const ms = Math.round((safe - Math.floor(safe)) * 1000);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(ms).padStart(3, '0')}`;
}

function toSrtTimestamp(value: string, fallbackSeconds: number): string {
  const raw = String(value || '').trim();
  const clock = raw.match(/^(\d{1,2}:\d{2}:\d{2})([,.])(\d{1,3})$/);
  if (clock) return `${clock[1]},${clock[3].padEnd(3, '0').slice(0, 3)}`;
  const secMatch = raw.match(/^([0-9]+(?:\.[0-9]+)?)s?$/i);
  if (secMatch) return secondsToSrtTime(Number(secMatch[1]));
  return secondsToSrtTime(fallbackSeconds);
}

function subtitlesToSrt(lines: SubtitleLine[]): string {
  return lines.map((line, idx) => {
    const start = toSrtTimestamp(line.start, idx * 5);
    const end = toSrtTimestamp(line.end, idx * 5 + 5);
    return `${idx + 1}\n${start} --> ${end}\n${String(line.text || '').trim()}\n`;
  }).join('\n');
}

function makeSubtitleFile(lines: SubtitleLine[], projectId: string): File {
  const content = subtitlesToSrt(lines);
  return new File([content], `edited_subtitles_${projectId}_${Date.now()}.srt`, { type: 'text/plain;charset=utf-8' });
}

function getActiveJob(project?: Project): ActiveJob | null {
  const cfg = (project?.config || {}) as Record<string, any>;
  const job = cfg.activeJob;
  if (!job || typeof job !== 'object') return null;
  if (!job.taskId || !job.type) return null;
  if (job.type !== 'subtitle' && job.type !== 'movie_story_script') return null;
  return {
    type: job.type,
    taskId: String(job.taskId),
    backend: String(job.backend || ''),
    model: String(job.model || ''),
  };
}

function MissingState({
  title,
  desc,
  primaryLabel,
  onPrimary,
  secondaryLabel,
  onSecondary,
}: {
  title: string;
  desc: string;
  primaryLabel?: string;
  onPrimary?: () => void;
  secondaryLabel?: string;
  onSecondary?: () => void;
}) {
  return (
    <div className="flex-1 flex items-center justify-center px-6 py-12 text-center">
      <div className="w-full max-w-md rounded-2xl border border-white/[0.06] bg-white/[0.02] p-8">
        <div className="w-14 h-14 rounded-full bg-amber-500/10 border border-amber-500/20 flex items-center justify-center mx-auto mb-4">
          <AlertTriangle className="w-6 h-6 text-amber-400" />
        </div>
        <h3 className="text-lg font-semibold text-white mb-2">{title}</h3>
        <p className="text-sm text-slate-500 leading-6 mb-6">{desc}</p>
        <div className="flex items-center justify-center gap-3">
          {secondaryLabel && onSecondary && (
            <Button variant="outline" onClick={onSecondary} className="border-white/15 bg-transparent text-white hover:bg-white/5">
              {secondaryLabel}
            </Button>
          )}
          {primaryLabel && onPrimary && (
            <Button onClick={onPrimary} className="bg-[#46ec13] hover:bg-[#37c00c] text-[#060a07] font-semibold">
              {primaryLabel}
            </Button>
          )}
        </div>
      </div>

    </div>
  );
}

export default function MaterialPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { project } = useOutletContext<Ctx>();

  const [phase, setPhase] = useState<Phase>(() => normalizePhase(project));
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | undefined>(project?.videoUrl);
  const [uploadedVideoPath, setUploadedVideoPath] = useState<string>(project?.uploadedVideoPath || '');
  const [uploadedSubtitlePath, setUploadedSubtitlePath] = useState<string>(project?.uploadedSubtitlePath || '');
  const [isUploadingVideo, setIsUploadingVideo] = useState(false);
  const [isCroppingVideo, setIsCroppingVideo] = useState(false);

  const [subtitleMode, setSubtitleMode] = useState<'auto' | 'upload' | null>(null);
  const [isRecognizing, setIsRecognizing] = useState(false);
  const [recognitionDone, setRecognitionDone] = useState(false);
  const [subtitles, setSubtitlesState] = useState<SubtitleLine[]>([]);
  const [subtitleDirty, setSubtitleDirty] = useState(false);
  const [subtitleError, setSubtitleError] = useState('');
  const [asrBackend, setAsrBackend] = useState<AsrBackend>(() =>
    normalizeAsrBackend(project?.config?.asrBackend)
  );

  const [config, setConfig] = useState<ConfigFormValue>({
    ...defaultConfig,
    ...(project?.config || {}),
  } as ConfigFormValue);

  const [generating, setGenerating] = useState(false);
  const [progressSteps, setProgressSteps] = useState<GenerationStep[]>([]);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewText, setPreviewText] = useState('');
  const [pendingScript, setPendingScript] = useState<ScriptItem[]>([]);

  const uploadTokenRef = useRef(0);
  const subtitleJobTokenRef = useRef(0);
  const generationJobTokenRef = useRef(0);
  const generationSubmitLockRef = useRef(false);
  const resumedJobRef = useRef('');
  const localPreviewUrlRef = useRef<string | null>(null);

  const hasVideo = Boolean(uploadedVideoPath && videoUrl);
  const hasSubtitle = Boolean(uploadedSubtitlePath || subtitles.length > 0);
  const hasConfig = Boolean(config);
  const activeStepIdx = Math.max(0, STEPS.findIndex((s) => s.key === phase));

  const updateProjectConfig = (patch: Record<string, any>) => {
    if (!id || !project) return;
    updateProject(id, {
      config: {
        ...(project.config || {}),
        ...config,
        asrBackend,
        ...patch,
      },
    });
  };

  const clearActiveJob = () => {
    updateProjectConfig({ activeJob: undefined });
  };

  const updateSubtitles = (next: SubtitleLine[]) => {
    setSubtitlesState(next);
    setSubtitleDirty(true);
    setRecognitionDone(next.length > 0);
  };

  const replaceSubtitlesFromFile = (next: SubtitleLine[]) => {
    setSubtitlesState(next);
    setSubtitleDirty(false);
    setSubtitleError('');
    setRecognitionDone(next.length > 0);
  };

  useEffect(() => {
    if (!project) return;
    setPhase(normalizePhase(project));
    setVideoUrl(project.videoUrl || undefined);
    setUploadedVideoPath(project.uploadedVideoPath || '');
    setUploadedSubtitlePath(project.uploadedSubtitlePath || '');
    setAsrBackend(normalizeAsrBackend(project.config?.asrBackend));
    setConfig({ ...defaultConfig, ...(project.config || {}) } as ConfigFormValue);
    setSubtitleMode(project.uploadedSubtitlePath ? 'auto' : null);
    setSubtitleDirty(false);
    setPreviewOpen(false);
    setPendingScript([]);
    setPreviewText('');
  }, [project?.id]);

  useEffect(() => {
    return () => {
      if (localPreviewUrlRef.current) {
        URL.revokeObjectURL(localPreviewUrlRef.current);
        localPreviewUrlRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!uploadedSubtitlePath) {
      if (!subtitleDirty) {
        setSubtitlesState([]);
        setRecognitionDone(false);
      }
      return;
    }

    let cancelled = false;
    readSubtitleLines(uploadedSubtitlePath)
      .then((lines) => {
        if (cancelled) return;
        replaceSubtitlesFromFile(lines);
        if (lines.length > 0) setSubtitleMode('auto');
      })
      .catch((err) => {
        if (!cancelled) {
          toast.error(`读取字幕失败：${err instanceof Error ? err.message : '未知错误'}`);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [uploadedSubtitlePath, project?.id]);

  const finishSubtitleJob = async (taskId: string, token: number) => {
    try {
      const snapshot = await waitForJob(taskId, { intervalMs: 1500 });
      if (token !== subtitleJobTokenRef.current) return;
      const subtitlePath = extractSubtitleArtifact(snapshot);
      if (!subtitlePath) {
        throw new Error('后端未返回字幕文件路径');
      }
      const lines = await readSubtitleLines(subtitlePath);
      if (token !== subtitleJobTokenRef.current) return;

      setSubtitleError('');
      setUploadedSubtitlePath(subtitlePath);
      replaceSubtitlesFromFile(lines);
      setSubtitleMode('auto');
      updateProject(id!, {
        uploadedSubtitlePath: subtitlePath,
        scriptItems: [],
        status: 'draft',
        currentStep: 'subtitle',
      });
      clearActiveJob();
      toast.success(`字幕识别完成，共 ${lines.length} 条`);
    } catch (err) {
      if (token !== subtitleJobTokenRef.current) return;
      const msg = err instanceof Error ? err.message : '未知错误';
      clearActiveJob();
      setSubtitleError(msg);
      setPhase('subtitle');

      // 失败只停在字幕页，不跳流程；已有字幕不丢，没有字幕则回识别入口。
      const stillHasSubtitle = Boolean(uploadedSubtitlePath || subtitles.length > 0);
      if (!stillHasSubtitle) {
        setSubtitleMode(null);
        setRecognitionDone(false);
      } else {
        setSubtitleMode('auto');
        setRecognitionDone(true);
      }

      updateProject(id!, {
        status: 'draft',
        currentStep: 'subtitle',
        config: {
          ...(project.config || {}),
          ...config,
          activeJob: undefined,
        },
      });
      toast.error(`字幕识别失败：${msg}`);
    } finally {
      if (token === subtitleJobTokenRef.current) setIsRecognizing(false);
    }
  };

  const finishGenerationJob = async (taskId: string, token: number) => {
    try {
      const snapshot = await waitForJob(taskId, {
        intervalMs: 2000,
        onTick: (snap) => {
          if (snap.message) setStepStatus('llm', 'running', snap.message);
        },
      });
      if (token !== generationJobTokenRef.current) return;
      const artifacts = extractMovieStoryArtifacts(snapshot);
      const items = normalizeScriptItems(artifacts.scriptItems);
      if (items.length === 0) {
        throw new Error('后端未返回解说脚本，请检查日志');
      }
      setStepStatus('llm', 'done');
      setStepStatus('parse', 'done');
      setPendingScript(items);
      setPreviewText(items.map((s) => s.narration).join('\n\n'));
      setGenerating(false);
      setProgressSteps([]);
      clearActiveJob();
      toast.success('解说文案已生成，请预览并确认');
      setPreviewOpen(true);
    } catch (err) {
      if (token !== generationJobTokenRef.current) return;
      clearActiveJob();
      toast.error(err instanceof Error ? err.message : '生成失败');
      setProgressSteps((prev) => prev.map((s) => (s.status === 'running' ? { ...s, status: 'error' } : s)));
      setGenerating(false);
      setTimeout(() => setProgressSteps([]), 600);
    }
  };

  useEffect(() => {
    const activeJob = getActiveJob(project);
    if (!activeJob || !id) return;
    if (resumedJobRef.current === activeJob.taskId) return;
    resumedJobRef.current = activeJob.taskId;

    if (activeJob.type === 'subtitle') {
      const token = ++subtitleJobTokenRef.current;
      setIsRecognizing(true);
      setSubtitleMode('auto');
      void finishSubtitleJob(activeJob.taskId, token);
      return;
    }

    if (activeJob.type === 'movie_story_script') {
      const token = ++generationJobTokenRef.current;
      setGenerating(true);
      setProgressSteps([
        { key: 'check', label: '校验视频与配置', status: 'done' },
        { key: 'llm', label: '正在请求大模型', status: 'running', hint: '已从刷新前的任务恢复轮询…' },
        { key: 'parse', label: '解析生成结果', status: 'pending' },
      ]);
      void finishGenerationJob(activeJob.taskId, token);
    }
  }, [project?.id]);

  if (!id || !project) {
    return (
      <div className="container-workspace py-20 text-center text-white/60">
        项目不存在或已被删除。
        <Button className="ml-3" onClick={() => navigate('/projects')}>
          返回项目列表
        </Button>
      </div>
    );
  }

  const clearVideoDependentState = () => {
    setUploadedSubtitlePath('');
    setSubtitlesState([]);
    setSubtitleDirty(false);
    setRecognitionDone(false);
    setSubtitleMode(null);
    setPendingScript([]);
    setPreviewText('');
    setPreviewOpen(false);
  };

  const goPhase = (next: Phase) => {
    setPhase(next);
    updateProject(id, { currentStep: next });
  };

  const goBack = () => {
    if (phase === 'subtitle') goPhase('upload');
    if (phase === 'config') goPhase('subtitle');
    if (phase === 'generate') goPhase('config');
  };

  const goNext = async () => {
    if (phase === 'upload') {
      if (!uploadedVideoPath) {
        toast.info(isUploadingVideo ? '视频仍在上传，请稍候' : '请先上传视频');
        return;
      }
      goPhase('subtitle');
      return;
    }
    if (phase === 'subtitle') {
      if (!hasSubtitle) {
        toast.info('请先识别字幕或上传字幕');
        return;
      }
      const saved = await ensureSubtitleSaved();
      if (!saved) return;
      goPhase('config');
      return;
    }
    if (phase === 'config') {
      updateProject(id, {
        config: { ...(project.config || {}), ...config, asrBackend },
        currentStep: 'generate',
      });
      setPhase('generate');
    }
  };

  const onVideoPicked = async (file: File | null) => {
    const token = ++uploadTokenRef.current;
    setUploadedFile(file);
    setUploadedVideoPath('');
    clearVideoDependentState();
    setPhase('upload');

    if (!file) {
      setVideoUrl(undefined);
      updateProject(id, {
        videoFileName: undefined,
        videoUrl: undefined,
        uploadedVideoPath: undefined,
        uploadedSubtitlePath: undefined,
        scriptItems: [],
        status: 'draft',
        currentStep: 'upload',
      });
      return;
    }

    const url = URL.createObjectURL(file);
    if (localPreviewUrlRef.current) URL.revokeObjectURL(localPreviewUrlRef.current);
    localPreviewUrlRef.current = url;
    setVideoUrl(url);
    updateProject(id, {
      videoFileName: file.name,
      videoUrl: url,
      uploadedVideoPath: undefined,
      uploadedSubtitlePath: undefined,
      scriptItems: [],
      status: 'draft',
      currentStep: 'upload',
    });

    setIsUploadingVideo(true);
    try {
      const resp = await uploadVideo(file);
      if (token !== uploadTokenRef.current) return;
      const nextVideoUrl = (resp as any).url || url;
      setUploadedVideoPath(resp.path);
      setVideoUrl(nextVideoUrl);
      updateProject(id, {
        uploadedVideoPath: resp.path,
        videoUrl: nextVideoUrl,
        uploadedSubtitlePath: undefined,
        scriptItems: [],
        status: 'draft',
        currentStep: 'upload',
      });
      toast.success('视频上传完成，可以点击下一步进入字幕页');
    } catch (err) {
      if (token !== uploadTokenRef.current) return;
      toast.error(`视频上传到服务端失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      if (token === uploadTokenRef.current) setIsUploadingVideo(false);
    }
  };

  const handleSkipCrop = () => {
    if (!uploadedVideoPath) {
      toast.info(isUploadingVideo ? '视频仍在上传，请稍候' : '请先上传视频');
      return;
    }
    goPhase('subtitle');
  };

  const handleConfirmCrop = async (payload: { startSec: number; endSec: number }) => {
    if (!uploadedVideoPath) {
      toast.info(isUploadingVideo ? '视频仍在上传，请稍候' : '请先上传视频');
      return;
    }
    setIsCroppingVideo(true);
    try {
      const resp = await cropUploadedVideo({
        path: uploadedVideoPath,
        start_sec: payload.startSec,
        end_sec: payload.endSec,
      });
      setUploadedVideoPath(resp.path);
      setVideoUrl(resp.url);
      clearVideoDependentState();
      updateProject(id, {
        uploadedVideoPath: resp.path,
        videoUrl: resp.url,
        uploadedSubtitlePath: undefined,
        scriptItems: [],
        status: 'draft',
        currentStep: 'upload',
      });
      toast.success('视频裁剪完成，可以进入字幕页');
    } catch (err) {
      toast.error(`裁剪失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setIsCroppingVideo(false);
    }
  };

  const resetSubtitleFailureView = () => {
    setPhase('subtitle');
    setSubtitleError('');
    setIsRecognizing(false);

    const hasExistingSubtitle = Boolean(uploadedSubtitlePath || subtitles.length > 0);
    if (hasExistingSubtitle) {
      setSubtitleMode('auto');
      setRecognitionDone(true);
    } else {
      setSubtitleMode(null);
      setRecognitionDone(false);
    }

    updateProject(id, {
      status: 'draft',
      currentStep: 'subtitle',
      config: {
        ...(project.config || {}),
        ...config,
        asrBackend,
        activeJob: undefined,
      },
    });
  };

  const onSubtitleStart = async () => {
    if (!uploadedVideoPath) {
      toast.info(isUploadingVideo ? '视频仍在上传，请稍候' : '请先上传视频');
      return;
    }

    const selected = ASR_BACKENDS.find((item) => item.key === asrBackend) || ASR_BACKENDS[0];
    const token = ++subtitleJobTokenRef.current;
    const hadExistingSubtitle = Boolean(uploadedSubtitlePath || subtitles.length > 0);

    setPhase('subtitle');
    setSubtitleMode('auto');
    setSubtitleError('');
    setIsRecognizing(true);
    setRecognitionDone(hadExistingSubtitle);

    // 不立即清空旧字幕。新模型成功后再覆盖；失败后旧字幕仍可用。
    if (!hadExistingSubtitle) {
      setSubtitlesState([]);
      setUploadedSubtitlePath('');
      setSubtitleDirty(false);
    }

    updateProject(id, {
      status: 'draft',
      currentStep: 'subtitle',
      config: {
        ...(project.config || {}),
        ...config,
        asrBackend,
        activeJob: undefined,
      },
    });

    try {
      const job = await createSubtitleJob({
        project_id: id,
        video_path: uploadedVideoPath,
        backend: selected.backend,
        model: selected.model || '',
      });
      updateProject(id, {
        status: 'draft',
        currentStep: 'subtitle',
        config: {
          ...(project.config || {}),
          ...config,
          asrBackend,
          activeJob: {
            type: 'subtitle',
            taskId: job.task_id,
            backend: selected.backend,
            model: selected.model || '',
          },
        },
      });
      await finishSubtitleJob(job.task_id, token);
    } catch (err) {
      if (token !== subtitleJobTokenRef.current) return;
      const msg = err instanceof Error ? err.message : '未知错误';
      clearActiveJob();
      setIsRecognizing(false);
      setSubtitleError(msg);

      if (!hadExistingSubtitle) {
        setSubtitleMode(null);
        setRecognitionDone(false);
      } else {
        setSubtitleMode('auto');
        setRecognitionDone(true);
      }

      updateProject(id, {
        status: 'draft',
        currentStep: 'subtitle',
        config: {
          ...(project.config || {}),
          ...config,
          asrBackend,
          activeJob: undefined,
        },
      });

      toast.error(`字幕识别失败：${msg}`);
    }
  };

  const onSubtitleFileUploaded = async (file: File, parsed: SubtitleLine[]) => {
    setPhase('subtitle');
    replaceSubtitlesFromFile(parsed);
    setSubtitleMode('upload');

    try {
      const resp = await uploadSubtitle(file);
      setUploadedSubtitlePath(resp.path);
      updateProject(id, {
        uploadedSubtitlePath: resp.path,
        scriptItems: [],
        status: 'draft',
        currentStep: 'subtitle',
      });
      toast.success(`字幕上传完成，共 ${parsed.length} 条`);
    } catch (err) {
      toast.error(`字幕文件上传到服务端失败：${err instanceof Error ? err.message : '未知错误'}`);
    }
  };

  const ensureSubtitleSaved = async (): Promise<string> => {
    if (uploadedSubtitlePath && !subtitleDirty) return uploadedSubtitlePath;
    if (subtitles.length === 0) {
      toast.info('当前没有字幕可保存');
      return '';
    }
    try {
      const file = makeSubtitleFile(subtitles, id);
      const resp = await uploadSubtitle(file);
      setUploadedSubtitlePath(resp.path);
      setSubtitleDirty(false);
      updateProject(id, {
        uploadedSubtitlePath: resp.path,
        scriptItems: [],
        status: 'draft',
      });
      return resp.path;
    } catch (err) {
      toast.error(`保存当前字幕失败：${err instanceof Error ? err.message : '未知错误'}`);
      return '';
    }
  };

  const handleConfigChange = (next: ConfigFormValue) => {
    setConfig(next);
    updateProject(id, {
      config: {
        ...(project.config || {}),
        ...next,
        asrBackend,
      },
    });
  };

  const setStepStatus = (key: string, status: GenerationStep['status'], hint?: string) => {
    setProgressSteps((prev) => prev.map((s) => (s.key === key ? { ...s, status, ...(hint ? { hint } : {}) } : s)));
  };

  const generate = async () => {
    if (generationSubmitLockRef.current) {
      toast.info('正在生成中，请稍候');
      return;
    }
    generationSubmitLockRef.current = true;

    try {
    if (!uploadedVideoPath) {
      toast.info('缺少视频，请返回上传视频页');
      return;
    }
    if (!hasSubtitle) {
      toast.info('缺少字幕，请返回字幕页识别或上传字幕');
      return;
    }

    const subtitlePath = await ensureSubtitleSaved();
    if (!subtitlePath) return;

    const token = ++generationJobTokenRef.current;
    setGenerating(true);
    const stepsDef: GenerationStep[] = [
      { key: 'check', label: '校验视频与配置', status: 'running' },
      { key: 'llm', label: '正在请求大模型', status: 'pending', hint: 'AI 正在创作解说文案…' },
      { key: 'parse', label: '解析生成结果', status: 'pending' },
    ];
    setProgressSteps(stepsDef);
    try {
      setStepStatus('check', 'done');
      setStepStatus('llm', 'running');
      updateProject(id, {
        currentStep: 'generate',
        status: 'draft',
        config: { ...(project.config || {}), ...config, asrBackend, activeJob: undefined },
      });

      const job = await createMovieStoryJob({
        project_id: id,
        video_path: uploadedVideoPath,
        subtitle_path: subtitlePath,
        video_theme: project?.name || '',
        narration_style: config.narrationStyle === 'default' ? 'general' : config.narrationStyle,
        movie_story_strategy: normalizeMovieStoryStrategy(config.movieStoryStrategy),
        movie_story_feature_mode: normalizeMovieStoryStrategy(config.movieStoryStrategy),
        movie_story_mode: normalizeMovieStoryStrategy(config.movieStoryStrategy),
        generation_mode: config.generationMode === 'auto' ? 'balanced' : config.generationMode,
        visual_mode: config.generationMode === 'manual' ? 'off' : 'auto',
        target_duration_minutes: 8,
        highlight_only: config.editMode === 'original_only',
        skip_llm: config.generationMode === 'manual',
      });
      updateProject(id, {
        config: {
          ...(project.config || {}),
          ...config,
          asrBackend,
          activeJob: { type: 'movie_story_script', taskId: job.task_id },
        },
      });
      await finishGenerationJob(job.task_id, token);
    } catch (err) {
      if (token !== generationJobTokenRef.current) return;
      clearActiveJob();
      toast.error(err instanceof Error ? err.message : '生成失败');
      setProgressSteps((prev) => prev.map((s) => (s.status === 'running' ? { ...s, status: 'error' } : s)));
      setGenerating(false);
      setTimeout(() => setProgressSteps([]), 600);
    }
    } finally {
      generationSubmitLockRef.current = false;
    }
  };

  const saveConfigDraft = () => {
    updateProject(id, {
      currentStep: 'config',
      config: {
        ...(project?.config || {}),
        ...config,
        asrBackend,
      },
    });
    toast.success('配置已保存');
  };

  const confirmPreview = (text: string) => {
    const lines = text.split(/\n\n+/).filter(Boolean);
    const next = pendingScript.map((s, i) => ({ ...s, narration: lines[i] ?? s.narration }));
    updateProject(id, {
      status: 'completed',
      currentStep: 'generate',
      scriptItems: next,
      config: { ...(project.config || {}), ...config, asrBackend, activeJob: undefined },
    });
    const now = new Date();
    toast.success(`脚本已保存，共 ${next.length} 段 · ${now.toLocaleTimeString()}`);
    setPreviewOpen(false);
    navigate(`/projects/${id}/analysis`);
  };

  const renderGenerateContent = () => {
    if (!uploadedVideoPath) {
      return (
        <MissingState
          title="缺少视频"
          desc="当前项目还没有可用于生成的视频。页面不会自动跳转，请点击下方按钮返回上传页。"
          primaryLabel="返回上传视频"
          onPrimary={() => goPhase('upload')}
          secondaryLabel="返回配置"
          onSecondary={() => goPhase('config')}
        />
      );
    }
    if (!hasSubtitle) {
      return (
        <MissingState
          title="缺少字幕"
          desc="生成脚本前需要字幕。你可以返回字幕页重新识别、换模型识别，或上传已有字幕。"
          primaryLabel="返回字幕页"
          onPrimary={() => goPhase('subtitle')}
          secondaryLabel="返回配置"
          onSecondary={() => goPhase('config')}
        />
      );
    }

    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-12">
        <div className="w-16 h-16 rounded-full flex items-center justify-center mb-5" style={{ background: 'rgba(70,236,19,0.12)', color: '#46ec13' }}>
          <Wand2 className="w-7 h-7" />
        </div>
        <h3 className="text-lg font-semibold">准备好生成剪辑脚本</h3>
        <p className="text-sm text-white/55 mt-2 max-w-md">
          点击“开始生成”后，系统将基于当前视频、字幕和配置生成解说文案。返回不会清空已有内容；重新生成才会重做本步骤。
        </p>
        <div className="mt-6 flex items-center gap-3">
          <Button variant="outline" onClick={() => goPhase('config')} className="border-white/15 bg-transparent text-white hover:bg-white/5">
            返回配置
          </Button>
          <Button type="button" onClick={() => void generate()} disabled={generating} className="bg-[#46ec13] hover:bg-[#37c00c] text-[#060a07] font-semibold rounded-lg px-6 brand-glow">
            {generating ? (
              <>
                <RefreshCcw className="w-4 h-4 mr-1 animate-spin" /> 生成中…
              </>
            ) : (
              <>
                <Wand2 className="w-4 h-4 mr-1" /> 开始生成
              </>
            )}
          </Button>
        </div>
      </div>
    );
  };

  return (
    <div className="container-workspace py-8 flex-1 flex flex-col">
      <header className="mb-6 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-bold">
            项目名称：<span className="text-[#46ec13]">{project.name}</span>
          </h2>
          <p className="text-sm text-white/55 mt-1">
            上传您的视频文件，系统将自动提取音频并识别字幕
          </p>
        </div>

        {phase === 'config' ? (
          <Button
            variant="outline"
            size="sm"
            onClick={saveConfigDraft}
            className="border-[#46ec13]/30 text-[#46ec13] hover:bg-[#46ec13]/10 shrink-0"
          >
            <Save className="w-4 h-4 mr-1.5" />保存配置
          </Button>
        ) : null}
      </header>

      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4 mb-6">
        <div className="flex items-center gap-2 text-sm flex-wrap">
          {STEPS.map((s, i) => {
            const active = phase === s.key;
            const done = activeStepIdx > i;
            return (
              <div key={s.key} className="flex items-center gap-2 flex-1 min-w-[160px]">
                <button
                  type="button"
                  onClick={() => goPhase(s.key)}
                  className={cn(
                    'flex items-center gap-2 px-3 py-1.5 rounded-full transition',
                    active ? 'text-[#46ec13]' : done ? 'text-white/85 hover:text-white' : 'text-white/50 hover:text-white'
                  )}
                >
                  <span
                    className={cn(
                      'w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-semibold border',
                      active
                        ? 'bg-[#46ec13] text-[#060a07] border-[#46ec13]'
                        : done
                          ? 'bg-[#46ec13]/90 text-[#060a07] border-[#46ec13]/90'
                          : 'bg-white/5 text-white/60 border-white/15'
                    )}
                  >
                    {done ? <CheckCircle2 className="w-3.5 h-3.5" /> : i + 1}
                  </span>
                  <span className="text-sm">{s.label}</span>
                </button>
                {i < STEPS.length - 1 ? <div className={cn('flex-1 h-px', done ? 'bg-[#46ec13]/50' : 'bg-white/10')} /> : null}
              </div>
            );
          })}
        </div>
      </div>


      <div
        className={cn(
          'rounded-2xl border border-white/[0.06] bg-[#0a0a0f] overflow-hidden flex flex-col',
          phase === 'subtitle' ? 'shrink-0' : 'flex-1 min-h-[640px]'
        )}
        style={phase === 'subtitle' ? { height: 720 } : undefined}
      >
        {phase === 'upload' && (
          <VideoUploadStep
            uploadedFile={uploadedFile}
            videoUrl={videoUrl}
            onFileSelect={onVideoPicked}
            onBack={undefined}
            onNext={() => void goNext()}
            canContinue={Boolean(uploadedVideoPath)}
            isCropping={isCroppingVideo}
            onSkipCrop={handleSkipCrop}
            onConfirmCrop={handleConfirmCrop}
          />
        )}

        {phase === 'subtitle' && (
          <SubtitleStep
            subtitleMode={subtitleMode}
            onModeSelect={setSubtitleMode}
            isRecognizing={isRecognizing}
            recognitionDone={recognitionDone}
            subtitleError={subtitleError}
            onResetFailure={resetSubtitleFailureView}
            onStartRecognition={() => void onSubtitleStart()}
            asrOptions={ASR_BACKENDS.map(({ key, label, desc }) => ({ key, label, desc }))}
            selectedAsrBackend={asrBackend}
            onAsrBackendChange={(key) => {
              const next = normalizeAsrBackend(key);
              setAsrBackend(next);
              setSubtitleError('');
              updateProject(id, { config: { ...(project.config || {}), ...config, asrBackend: next } });
            }}
            subtitles={subtitles}
            onSubtitlesChange={updateSubtitles}
            onSubtitleFileSelect={(file, parsed) => void onSubtitleFileUploaded(file, parsed)}
            videoFile={uploadedFile}
            videoUrl={videoUrl}
            onReupload={() => goPhase('upload')}
            onBack={goBack}
            onNext={() => void goNext()}
          />
        )}

        {phase === 'config' && (
          !hasSubtitle ? (
            <MissingState
              title="缺少字幕"
              desc="配置页可以停留在这里，但要继续下一步需要先回到字幕页识别或上传字幕。"
              primaryLabel="返回字幕页"
              onPrimary={() => goPhase('subtitle')}
              secondaryLabel="返回上传页"
              onSecondary={() => goPhase('upload')}
            />
          ) : (
            <ConfigStep
              projectType="movie"
              value={config}
              onChange={handleConfigChange}
              onBack={goBack}
              onReupload={() => goPhase('upload')}
              onGenerate={() => void goNext()}
              generating={generating}
            />
          )
        )}

        {phase === 'generate' && renderGenerateContent()}
      </div>

      {phase === 'subtitle' ? (
        <div className="space-y-4">
          <SpeakerContextPanel
            mediaPath={uploadedVideoPath || ''}
            subtitleSegments={subtitles as unknown as Array<Record<string, unknown>>}
          />
          <SceneBoundaryContextPanel
            mediaPath={uploadedVideoPath || ''}
            subtitleSegments={subtitles as unknown as Array<Record<string, unknown>>}
          />
        </div>
      ) : null}


      <GenerationProgressModal
        open={generating}
        steps={progressSteps}
        onCancel={() => {
          setGenerating(false);
          setProgressSteps([]);
          clearActiveJob();
          toast.info('已取消前端等待；后端任务若已提交，可能仍会继续执行');
        }}
      />

      <CopywritingPreviewDialog
        open={previewOpen}
        initialText={previewText}
        onClose={() => setPreviewOpen(false)}
        onRegenerate={() => {
          setPreviewOpen(false);
          void generate();
        }}
        onConfirm={confirmPreview}
      />
    
</div>
  );
}

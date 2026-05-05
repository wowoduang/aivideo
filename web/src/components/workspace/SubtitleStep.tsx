import { useEffect, useRef, useState } from 'react';
import { Upload, FileText, Play, Video, Maximize2, RefreshCw, Download, Settings, ArrowLeft, ArrowRight, CloudUpload, Info, FileVideo, Volume2, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { resolveAssetUrl, type SubtitleLine } from '@/lib/api';

type AsrOption = { key: string; label: string; desc: string };

interface SubtitleStepProps {
  subtitleMode: 'auto' | 'upload' | null;
  onModeSelect: (mode: 'auto' | 'upload') => void;
  isRecognizing: boolean;
  recognitionDone: boolean;
  subtitleError?: string;
  onResetFailure?: () => void;
  onStartRecognition: () => void;
  asrOptions?: AsrOption[];
  selectedAsrBackend?: string;
  onAsrBackendChange?: (key: string) => void;
  subtitles: SubtitleLine[];
  onSubtitlesChange: (subs: SubtitleLine[]) => void;
  onSubtitleFileSelect?: (file: File, parsed: SubtitleLine[]) => void;
  videoFile?: File | null;
  videoUrl?: string;
  onReupload?: () => void;
  onBack?: () => void;
  onNext?: () => void;
}

function parseSRT(srt: string): SubtitleLine[] {
  // 先清理行尾空格，然后用一个或多个空白行（可能包含空格）分割
  const cleaned = srt.replace(/[ \t]+\n/g, '\n');
  const blocks = cleaned.trim().split(/\r?\n\s*\r?\n+/);

  return blocks
    .map((block, index) => {
      const lines = block.split(/\r?\n/).filter((line) => line.trim().length > 0);
      const timeLine = lines.find((line) => line.includes('-->')) || '';
      const textLines = lines.filter((line) => !/^\d+$/.test(line.trim()) && !line.includes('-->'));
      const timeMatch = timeLine.match(/(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)/);

      return {
        id: index + 1,
        start: timeMatch ? timeMatch[1].replace(',', '.') : `${index * 5}.0s`,
        end: timeMatch ? timeMatch[2].replace(',', '.') : `${index * 5 + 5}.0s`,
        text: textLines.join(' ').trim() || `字幕 ${index + 1}`,
      };
    })
    .filter((item) => item.text.length > 0);
}

// 格式化时间显示："00:00:21.500" -> "21.5s"
function formatTimeDisplay(timeStr: string): string {
  const match = timeStr.match(/(\d+):(\d+):(\d+)[.,]?(\d*)/);
  if (!match) return timeStr;
  const [, h, m, s, ms] = match;
  const totalSeconds = parseInt(h) * 3600 + parseInt(m) * 60 + parseInt(s);
  const firstDecimal = ms ? ms.padEnd(3, '0').slice(0, 1) : '0';
  return `${totalSeconds}.${firstDecimal}s`;
}

function formatClock(sec: number, withHour = false): string {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  const mm = String(m).padStart(2, '0');
  const ss = String(s).padStart(2, '0');
  if (withHour || h > 0) {
    return `${String(h).padStart(2, '0')}:${mm}:${ss}`;
  }
  return `${mm}:${ss}`;
}

function formatFileSize(bytes: number): string {
  if (!bytes || bytes <= 0) return '未知';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(sizes.length - 1, Math.floor(Math.log(bytes) / Math.log(k)));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))}${sizes[i]}`;
}

export default function SubtitleStep({
  subtitleMode,
  onModeSelect,
  isRecognizing,
  recognitionDone,
  subtitleError,
  onResetFailure,
  onStartRecognition,
  asrOptions = [],
  selectedAsrBackend,
  onAsrBackendChange,
  subtitles,
  onSubtitlesChange,
  onSubtitleFileSelect,
  videoFile,
  videoUrl,
  onReupload,
  onBack,
  onNext,
}: SubtitleStepProps) {
  const srtInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [resolution, setResolution] = useState<string>('');
  const [videoFailed, setVideoFailed] = useState(false);
  const [videoSrc, setVideoSrc] = useState('');
  const [videoReady, setVideoReady] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);

  useEffect(() => {
    setCurrentTime(0);
    setDuration(0);
    setResolution('');
    setVideoFailed(false);
    setVideoReady(false);
    setIsPlaying(false);

    if (!videoUrl) {
      setVideoSrc('');
      return;
    }
    const normalized = resolveAssetUrl(videoUrl);
    setVideoSrc(normalized);
  }, [videoUrl]);

  const onLoadedMetadata = () => {
    const el = videoRef.current;
    if (!el) return;
    setDuration(el.duration || 0);
    if (el.videoWidth && el.videoHeight) {
      setResolution(`${el.videoWidth}×${el.videoHeight}`);
    }
  };

  const onTimeUpdate = () => {
    const el = videoRef.current;
    if (!el) return;
    setCurrentTime(el.currentTime || 0);
  };

  const progressPct = duration > 0 ? Math.min(100, (currentTime / duration) * 100) : 0;

  if (!videoUrl && !isRecognizing) {
    return (
      <div className="h-full flex items-center justify-center px-6">
        <div className="w-full max-w-md text-center rounded-2xl border border-white/[0.06] bg-[#111111] p-8">
          <div className="w-14 h-14 rounded-full bg-white/[0.04] border border-white/10 flex items-center justify-center mx-auto mb-4">
            <Video className="w-6 h-6 text-white/60" />
          </div>
          <h3 className="text-lg font-semibold text-white mb-2">请先上传视频</h3>
          <p className="text-sm text-slate-500 mb-5">当前项目还没有可用于预览和字幕识别的视频文件。</p>
          <Button
            onClick={onReupload || onBack}
            className="bg-[#46ec13] hover:bg-[#37c00c] text-black font-medium"
          >
            返回视频上传
          </Button>
        </div>
      </div>
    );
  }

  const togglePlayback = () => {
    const el = videoRef.current;
    if (!el) return;
    if (el.paused) {
      void el.play().then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
    } else {
      el.pause();
      setIsPlaying(false);
    }
  };

  const retryVideoPreview = () => {
    if (!videoUrl) return;
    const normalized = resolveAssetUrl(videoUrl);
    setVideoFailed(false);
    setVideoReady(false);
    setIsPlaying(false);
    setVideoSrc(normalized);
  };

  const handleSrtUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (ev) => {
      const content = String(ev.target?.result || '');
      const parsed = parseSRT(content);
      onSubtitlesChange(parsed);
      onModeSelect('upload');
      onSubtitleFileSelect?.(file, parsed);
    };
    reader.readAsText(file);
  };

  const handleEditStart = (sub: SubtitleLine) => {
    setEditingId(sub.id);
    setEditText(sub.text);
  };

  const handleEditSave = (id: number) => {
    onSubtitlesChange(subtitles.map((s) => (s.id === id ? { ...s, text: editText } : s)));
    setEditingId(null);
  };

  const handleDelete = (id: number) => {
    onSubtitlesChange(subtitles.filter((s) => s.id !== id));
    if (editingId === id) setEditingId(null);
  };

  const handleExport = () => {
    let srtContent = '';
    subtitles.forEach((sub, index) => {
      const start = sub.start.replace('.', ',');
      const end = sub.end.replace('.', ',');
      srtContent += `${index + 1}\n${start} --> ${end}\n${sub.text}\n\n`;
    });
    const blob = new Blob([srtContent], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `subtitles_${Date.now()}.srt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // 初始状态 - 选择识别方式
  if (!subtitleMode && !recognitionDone) {
    return (
      <div className="h-full flex flex-col min-h-0">
        <div className="flex-1 flex items-center justify-center px-6">
          <div className="w-full max-w-2xl">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-semibold text-white mb-2">字幕识别</h2>
              <p className="text-sm text-slate-400">选择字幕获取方式，支持自动识别或上传已有字幕文件</p>
            </div>
            
            {subtitleError && (
              <div className="mb-5 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-left">
                <p className="text-sm font-medium text-red-200">上一次字幕识别失败</p>
                <p className="mt-1 text-xs leading-5 text-red-100/75 break-words">{subtitleError}</p>
                <p className="mt-2 text-xs text-red-100/60">请切换模型后重新识别，或上传已有字幕文件。</p>
              </div>
            )}

            {asrOptions.length > 0 && (
              <div className="mb-5 rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                <div className="mb-3">
                  <p className="text-sm font-medium text-white">自动识别后端</p>
                  <p className="text-xs text-slate-500 mt-0.5">可随时换模型重新识别；重新识别会覆盖旧字幕和后续脚本</p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {asrOptions.map((option) => {
                    const active = selectedAsrBackend === option.key;
                    return (
                      <button
                        key={option.key}
                        type="button"
                        onClick={() => onAsrBackendChange?.(option.key)}
                        className={`rounded-xl border px-3 py-3 text-left transition ${active ? 'border-[#46ec13]/70 bg-[#46ec13]/10 text-white' : 'border-white/[0.08] bg-white/[0.02] text-white/75 hover:border-[#46ec13]/30 hover:bg-white/[0.04]'}`}
                      >
                        <div className="flex items-center gap-2">
                          <span className={`h-2.5 w-2.5 rounded-full ${active ? 'bg-[#46ec13]' : 'bg-white/20'}`} />
                          <span className="text-sm font-medium">{option.label}</span>
                        </div>
                        <p className="mt-1.5 text-xs leading-5 text-slate-500">{option.desc}</p>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <button
                type="button"
                onClick={onStartRecognition}
                disabled={isRecognizing}
                className="group p-6 rounded-2xl bg-[#1a1a1a] border border-white/[0.06] hover:border-[#46ec13]/30 transition-all text-left disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <div className="w-12 h-12 rounded-xl bg-[#46ec13]/10 border border-[#46ec13]/20 flex items-center justify-center mb-4 group-hover:bg-[#46ec13]/20 transition-colors">
                  {isRecognizing ? (
                    <div className="w-5 h-5 border-2 border-[#46ec13]/30 border-t-[#46ec13] rounded-full animate-spin" />
                  ) : (
                    <Play className="w-5 h-5 text-[#46ec13]" />
                  )}
                </div>
                <h3 className="text-base font-medium text-white mb-1">自动识别</h3>
                <p className="text-xs text-slate-500">按上方选择的后端自动生成字幕</p>
              </button>

              <button
                type="button"
                onClick={() => srtInputRef.current?.click()}
                className="group p-6 rounded-2xl bg-[#1a1a1a] border border-white/[0.06] hover:border-[#46ec13]/30 transition-all text-left"
              >
                <div className="w-12 h-12 rounded-xl bg-[#46ec13]/10 border border-[#46ec13]/20 flex items-center justify-center mb-4 group-hover:bg-[#46ec13]/20 transition-colors">
                  <Upload className="w-5 h-5 text-[#46ec13]" />
                </div>
                <h3 className="text-base font-medium text-white mb-1">上传字幕</h3>
                <p className="text-xs text-slate-500">支持 SRT、VTT 格式字幕文件</p>
              </button>
              <input ref={srtInputRef} type="file" accept=".srt,.vtt,.txt" className="hidden" onChange={handleSrtUpload} />
            </div>
          </div>
        </div>

        <div className="h-16 border-t border-white/[0.06] bg-[#0A0A0F] flex items-center justify-between px-6 shrink-0">
          <div>
            {onResetFailure ? (
              <Button variant="ghost" size="sm" onClick={onResetFailure} className="text-slate-400 hover:text-white gap-1.5">
                <ArrowLeft className="w-4 h-4" />返回字幕识别
              </Button>
            ) : onBack ? (
              <Button variant="ghost" size="sm" onClick={onBack} className="text-slate-400 hover:text-white gap-1.5">
                <ArrowLeft className="w-4 h-4" />返回
              </Button>
            ) : null}
          </div>
          <div className="flex items-center gap-3">
            {onReupload && (
              <Button variant="outline" size="sm" onClick={onReupload} className="border-white/[0.08] text-slate-400 hover:text-white hover:bg-white/[0.04] gap-1.5">
                <CloudUpload className="w-4 h-4" />重新上传
              </Button>
            )}
            {onNext && (
              <Button size="sm" onClick={onNext} disabled className="bg-[#46ec13] hover:bg-[#46ec13]/90 text-black font-medium gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed">
                下一步：配置参数
                <ArrowRight className="w-4 h-4" />
              </Button>
            )}
          </div>
        </div>
      </div>
    );
  }

  // 识别中状态
  if (isRecognizing) {
    return (
      <div className="h-full flex flex-col min-h-0">
        <div className="flex-1 flex items-center justify-center px-6">
          <div className="text-center">
            <div className="w-16 h-16 rounded-2xl bg-[#46ec13]/10 border border-[#46ec13]/20 flex items-center justify-center mx-auto mb-4">
              <div className="w-6 h-6 border-2 border-[#46ec13]/30 border-t-[#46ec13] rounded-full animate-spin" />
            </div>
            <h3 className="text-lg font-medium text-white mb-2">正在识别字幕...</h3>
            <p className="text-sm text-slate-500">当前任务会继续执行。你可以返回其他页面；任务完成后会写回字幕结果。</p>
          </div>
        </div>
        <div className="h-16 border-t border-white/[0.06] bg-[#0A0A0F] flex items-center justify-between px-6 shrink-0">
          <div>
            {onBack && (
              <Button variant="ghost" size="sm" onClick={onBack} className="text-slate-400 hover:text-white gap-1.5">
                <ArrowLeft className="w-4 h-4" />返回
              </Button>
            )}
          </div>
          <div className="flex items-center gap-3">
            {onReupload && (
              <Button variant="outline" size="sm" onClick={onReupload} className="border-white/[0.08] text-slate-400 hover:text-white hover:bg-white/[0.04] gap-1.5">
                <CloudUpload className="w-4 h-4" />重新上传
              </Button>
            )}
          </div>
        </div>
      </div>
    );
  }


  const fileSizeText = formatFileSize(videoFile?.size ?? 0);
  const durationText = duration > 0 ? formatClock(duration, true) : '00:00:00';

  // 字幕编辑状态
  const showPlaceholder = !videoSrc || videoFailed;

  return (
    <div className="h-full flex flex-col min-h-0">
      {/* 主内容区：左视频信息(1) + 右字幕列表(2)，等高各自滚动 */}
      <div className="flex-1 grid grid-cols-1 md:grid-cols-[minmax(520px,1.25fr)_minmax(420px,0.75fr)] overflow-hidden min-h-0">
        {/* 左侧：视频预览(固定) + 元数据(滚动) */}
        <div className="flex flex-col min-h-0 md:border-r border-white/[0.06]">
          <div className="p-5 pb-4 shrink-0 space-y-4">
            <div className="relative w-full rounded-2xl bg-black overflow-auto resize-y flex items-center justify-center" style={{ minHeight: 460, maxHeight: '82vh' }}>
              {!showPlaceholder ? (
                <>
                  <video
                    ref={videoRef}
                    key={videoSrc}
                    src={videoSrc}
                    controls
                    playsInline
                    preload="metadata"
                    onClick={togglePlayback}
                    onPlay={() => setIsPlaying(true)}
                    onPause={() => setIsPlaying(false)}
                    onLoadedMetadata={onLoadedMetadata}
                    onLoadedData={(e) => {
                      const video = e.target as HTMLVideoElement;
                      setVideoReady(true);
                      if (video.currentTime === 0 && (video.duration || 0) > 0.15) {
                        try {
                          video.currentTime = 0.1;
                        } catch {}
                      }
                    }}
                    onCanPlay={() => {
                      setVideoFailed(false);
                      setVideoReady(true);
                    }}
                    onTimeUpdate={onTimeUpdate}
                    onError={() => {
                      setVideoReady(false);
                      setVideoFailed(true);
                    }}
                    className="w-full max-h-[78vh] h-auto object-contain cursor-pointer"
                  />
                  {!isPlaying && videoReady && (
                    <button
                      type="button"
                      onClick={togglePlayback}
                      className="absolute inset-0 m-auto h-14 w-14 rounded-full bg-black/55 text-white flex items-center justify-center border border-white/15 hover:bg-black/70 transition z-10"
                    >
                      <Play className="w-6 h-6 translate-x-[1px]" />
                    </button>
                  )}
                  <button className="absolute top-3 right-3 w-8 h-8 rounded-lg bg-black/60 flex items-center justify-center text-white/70 hover:text-white z-10">
                    <Maximize2 className="w-4 h-4" />
                  </button>
                </>
              ) : (
                <div className="absolute inset-0 flex flex-col items-center justify-center p-6">
                  <button className="absolute top-3 right-3 w-8 h-8 rounded-lg bg-black/60 flex items-center justify-center text-white/70 hover:text-white">
                    <Maximize2 className="w-4 h-4" />
                  </button>
                  <div className="w-14 h-14 rounded-full bg-white/[0.04] border border-white/10 flex items-center justify-center mb-4">
                    <Video className="w-6 h-6 text-white/60" />
                  </div>
                  <p className="text-white font-medium text-base mb-1">视频预览暂时不可用</p>
                  <p className="text-xs text-slate-500 mb-5">请重试加载预览；若仍失败，通常是浏览器对原视频编码兼容性较差</p>
                  <Button
                    onClick={videoUrl ? retryVideoPreview : onReupload}
                    className="bg-[#46ec13] hover:bg-[#37c00c] text-black font-medium gap-1.5"
                  >
                    <RefreshCw className="w-4 h-4" />{videoUrl ? '重新加载预览' : '重新选择视频'}
                  </Button>
                </div>
              )}
            </div>

            {/* 时间轴 */}
            <div>
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span className="font-mono">{formatClock(currentTime)}</span>
                <span className="font-mono">{durationText}</span>
              </div>
              <div className="relative mt-2 h-1 rounded-full bg-white/10">
                <div className="absolute left-0 top-0 h-full rounded-full bg-[#46ec13]/60" style={{ width: `${progressPct}%` }} />
                <div
                  className="absolute top-1/2 w-3 h-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#46ec13] shadow"
                  style={{ left: `${progressPct}%` }}
                />
              </div>
            </div>
          </div>

          {/* 元数据（独立滚动） */}
          <div className="flex-1 overflow-y-auto min-h-0 px-5 pb-5">
            <div className="flex items-center gap-2 mb-3">
              <Info className="w-4 h-4 text-[#46ec13]" />
              <span className="text-sm font-semibold text-white">元数据</span>
            </div>

            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
              <div className="flex items-center gap-2 mb-3">
                <FileVideo className="w-4 h-4 text-[#46ec13]" />
                <span className="text-sm font-medium text-white">视频信息</span>
              </div>
              <dl className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <dt className="text-slate-500">分辨率</dt>
                  <dd className="text-slate-200 font-medium">{resolution || '未知'}</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-slate-500">时长</dt>
                  <dd className="text-slate-200 font-medium font-mono">{durationText}</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-slate-500">文件大小</dt>
                  <dd className="text-slate-200 font-medium">{fileSizeText}</dd>
                </div>
              </dl>
            </div>

            <div className="mt-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
              <div className="flex items-center gap-2 mb-3">
                <Volume2 className="w-4 h-4 text-[#46ec13]" />
                <span className="text-sm font-medium text-white">音频信息</span>
              </div>
              <dl className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <dt className="text-slate-500">采样率</dt>
                  <dd className="text-slate-200 font-medium">48kHz</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-slate-500">声道</dt>
                  <dd className="text-slate-200 font-medium">立体声</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-slate-500">比特率</dt>
                  <dd className="text-slate-200 font-medium">192kbps</dd>
                </div>
              </dl>
            </div>
          </div>
        </div>

        {/* 右侧：字幕列表 */}
        <div className="flex flex-col min-h-0">
          <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06]">
            <div>
              <h3 className="text-base font-semibold text-white">字幕预览与编辑</h3>
              <p className="text-xs text-slate-500 mt-0.5">共 {subtitles.length} 条字幕 · 点击气泡即可编辑</p>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={handleExport}
                className="flex items-center gap-1 px-2 py-1.5 text-xs text-[#46ec13] hover:bg-[#46ec13]/10 rounded-md transition"
              >
                <Download className="w-3.5 h-3.5" />导出
              </button>
              <button
                className="p-1.5 rounded-md text-slate-400 hover:text-white hover:bg-white/5 transition"
                title="设置"
              >
                <Settings className="w-4 h-4" />
              </button>
              <input ref={srtInputRef} type="file" accept=".srt,.vtt,.txt" className="hidden" onChange={handleSrtUpload} />
            </div>
          </div>

          {subtitleError && (
            <div className="px-5 py-3 border-b border-red-500/20 bg-red-500/10">
              <p className="text-xs font-medium text-red-200">字幕识别失败提示</p>
              <p className="mt-1 text-xs leading-5 text-red-100/75 break-words">{subtitleError}</p>
              <p className="mt-1 text-[11px] text-red-100/60">当前页面不会跳转；请重新点击“重新识别”或返回上一步。</p>
            </div>
          )}

          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
            {subtitles.length === 0 ? (
              <div className="h-full flex items-center justify-center">
                <div className="text-center">
                  <div className="w-14 h-14 rounded-2xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mx-auto mb-3">
                    <FileText className="w-7 h-7 text-slate-600" />
                  </div>
                  <p className="text-sm text-slate-500">暂无字幕数据</p>
                </div>
              </div>
            ) : (
              subtitles.map((sub) => (
                <div key={sub.id} className="group flex items-center gap-2">
                  <span className="shrink-0 px-3 py-1.5 rounded-full bg-[#46ec13]/12 border border-[#46ec13]/30 text-[#46ec13] text-xs font-medium font-mono whitespace-nowrap">
                    {formatTimeDisplay(sub.start)} · {formatTimeDisplay(sub.end)}
                  </span>
                  <div className="flex-1 min-w-0">
                    {editingId === sub.id ? (
                      <input
                        type="text"
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        onBlur={() => handleEditSave(sub.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleEditSave(sub.id);
                          if (e.key === 'Escape') setEditingId(null);
                        }}
                        autoFocus
                        className="w-full h-12 rounded-xl bg-white/[0.04] border border-[#46ec13]/40 px-4 text-sm text-white outline-none focus:border-[#46ec13]"
                      />
                    ) : (
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={() => handleEditStart(sub)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            handleEditStart(sub);
                          }
                        }}
                        title={sub.text}
                        className="w-full min-h-12 rounded-xl bg-white/[0.03] border border-white/[0.05] hover:border-[#46ec13]/30 px-4 py-3 text-sm leading-6 text-slate-200 transition cursor-text overflow-hidden whitespace-normal break-words"
                      >
                        {sub.text}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => handleDelete(sub.id)}
                    title="删除此条字幕"
                    className="shrink-0 w-9 h-9 flex items-center justify-center rounded-lg border border-white/[0.06] text-slate-500 hover:text-red-400 hover:bg-red-500/10 hover:border-red-500/30 opacity-0 group-hover:opacity-100 transition"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* 底部操作栏 */}
      <div className="h-16 border-t border-white/[0.06] bg-[#0A0A0F] flex items-center justify-between px-6 shrink-0">
        <div>
          {onBack && (
            <Button variant="ghost" size="sm" onClick={onBack} className="text-slate-400 hover:text-white gap-1.5">
              <ArrowLeft className="w-4 h-4" />返回
            </Button>
          )}
        </div>
        <div className="flex items-center gap-3">
          {onReupload && (
            <Button
              variant="outline"
              size="sm"
              onClick={onReupload}
              className="border-white/[0.08] text-slate-400 hover:text-white hover:bg-white/[0.04] gap-1.5"
            >
              <CloudUpload className="w-4 h-4" />重新上传
            </Button>
          )}
          {onNext && (
            <Button
              size="sm"
              onClick={onNext}
              disabled={subtitles.length === 0}
              className="bg-[#46ec13] hover:bg-[#46ec13]/90 text-black font-medium gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              下一步：配置参数
              <ArrowRight className="w-4 h-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
